"""Round trips through make_ips and apply_ips.

    python3 common/test_ips.py
"""
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ips import MAX_IPS_RECORD, apply_ips, make_ips  # noqa: E402

EOF_OFFSET = int.from_bytes(b"EOF", "big")    # a record here reads as the end of the patch


def record_offsets(ips):
    offsets, i = [], 5
    while ips[i:i + 3] != b"EOF":
        offsets.append(int.from_bytes(ips[i:i + 3], "big"))
        size = int.from_bytes(ips[i + 3:i + 5], "big")
        i += 5 + (3 if size == 0 else size)
    return offsets


def edited(size, edits):
    original = bytes(size)
    patched = bytearray(original)
    for at, data in edits:
        patched[at:at + len(data)] = data
    return original, bytes(patched)


class RoundTrip(unittest.TestCase):
    def check(self, original, patched):
        for rle in (True, False):
            ips = make_ips(original, patched, rle=rle)
            self.assertEqual(apply_ips(original, ips), patched, f"rle={rle}")
            self.assertNotIn(EOF_OFFSET, record_offsets(ips), f"rle={rle}")

    def test_small_images(self):
        rng = random.Random(1)
        for _ in range(200):
            original = rng.randbytes(rng.choice([0x150, 0x1000, 0x8000]))
            patched = bytearray(original)
            for _ in range(rng.randrange(1, 20)):
                at, n = rng.randrange(len(patched)), rng.choice([1, 9, 12, 13, 300])
                chunk = rng.choice([rng.randbytes(n), bytes([rng.randrange(256)]) * n])
                patched[at:at + n] = chunk[:len(patched[at:at + n])]
            self.check(original, bytes(patched))

    def test_records_around_the_eof_offset(self):
        eof = EOF_OFFSET
        size = eof + 0x40
        data = bytes(range(1, 41))
        cases = {
            "one byte at the offset": [(eof, b"\x01")],
            "data from the offset": [(eof, data)],
            "RLE run ending at the offset, then data": [(eof - 12, b"\x33" * 12), (eof, data[:5])],
            "data, then an RLE run from the offset": [(eof - 6, data[:6]), (eof, b"\x77" * 20)],
            "a full-size record ending at the offset":
                [(eof - MAX_IPS_RECORD, bytes(k % 251 + 1 for k in range(MAX_IPS_RECORD + 10)))],
        }
        for name, edits in cases.items():
            with self.subTest(name):
                self.check(*edited(size, edits))
        with self.subTest("an image grown past the offset"):
            self.check(bytes(eof), bytes(eof) + b"\x01\x02\x03")


if __name__ == "__main__":
    unittest.main()
