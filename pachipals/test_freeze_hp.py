"""Patch safety tests using synthetic bytes, without a game ROM or emulator."""

import json
import unittest

import freeze_hp as patch


class PatchSafetyTests(unittest.TestCase):
    def setUp(self):
        self.sites = json.loads(patch.PROFILES_PATH.read_text())["sites"]
        self.image = bytearray(0xC0000)
        for site in self.sites:
            start = patch.file_offset(int(site["bank"], 16), int(site["context_address"], 16))
            context = bytes.fromhex(site["context_before"])
            self.image[start:start + len(context)] = context
        patch.fix_global_checksum(self.image)

    def test_physical_offsets(self):
        self.assertEqual(patch.file_offset(0x15, 0x47BA), 0x547BA)
        self.assertEqual(patch.file_offset(0x2F, 0x6B51), 0xBEB51)

    def test_only_four_operand_bytes_and_checksum_change(self):
        before = bytes(self.image)
        after = patch.apply_edits(before, self.sites)
        changed = {i for i, (a, b) in enumerate(zip(before, after)) if a != b}
        self.assertEqual(changed - {0x14E, 0x14F},
                         {0x547BA, 0x547BB, 0xBEB51, 0xBEB52})
        self.assertEqual(len(after), len(before))
        self.assertEqual(bytes(self.image), before)
        for site in self.sites:
            offset = patch.file_offset(int(site["bank"], 16), int(site["address"], 16))
            self.assertEqual(after[offset:offset + 3], bytes.fromhex("FE0000"))
        expected = (sum(after[:0x14E]) + sum(after[0x150:])) & 0xFFFF
        self.assertEqual(int.from_bytes(after[0x14E:0x150], "big"), expected)

    def test_each_context_byte_is_asserted(self):
        for site in self.sites:
            start = patch.file_offset(int(site["bank"], 16), int(site["context_address"], 16))
            for relative in range(len(bytes.fromhex(site["context_before"]))):
                with self.subTest(site=site["name"], relative=relative):
                    damaged = self.image.copy()
                    damaged[start + relative] ^= 1
                    with self.assertRaisesRegex(ValueError, "Original-byte assertion"):
                        patch.apply_edits(damaged, self.sites)

    def test_unknown_rom_rejected_even_with_matching_contexts(self):
        with self.assertRaisesRegex(ValueError, "Unsupported ROM"):
            patch.freeze_hp(bytes(self.image))

    def test_second_application_rejected(self):
        patched = patch.apply_edits(self.image, self.sites)
        with self.assertRaisesRegex(ValueError, "Original-byte assertion"):
            patch.apply_edits(patched, self.sites)

    def test_failure_does_not_modify_input(self):
        self.image[0xBEB51] ^= 1
        before = bytes(self.image)
        with self.assertRaises(ValueError):
            patch.apply_edits(self.image, self.sites)
        self.assertEqual(bytes(self.image), before)

    def test_bad_bank_addresses_rejected(self):
        for bank, address in ((0, 0x4000), (0x200, 0x4000), (1, 0x3FFF), (1, 0x8000)):
            with self.subTest(bank=bank, address=address):
                with self.assertRaises(ValueError):
                    patch.file_offset(bank, address)

    def test_overlapping_edits_rejected(self):
        with self.assertRaisesRegex(ValueError, "Overlapping"):
            patch.apply_edits(self.image, self.sites + self.sites)

    def test_truncated_image_rejected(self):
        with self.assertRaisesRegex(ValueError, "Truncated"):
            patch.apply_edits(bytes(0x100), self.sites)


if __name__ == "__main__":
    unittest.main()
