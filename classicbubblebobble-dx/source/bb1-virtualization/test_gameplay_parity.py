#!/usr/bin/env python3
"""Compare KLL1 gameplay with native BB1 on CGB, frame by frame.

The native reference changes only the CGB header and checksums. RAM descriptor
pointers are normalized for their documented relocation; gameplay fields,
collision data, timer, tile graphics, and both tile maps must match exactly.
"""
import argparse
from collections import Counter
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from shutil import copyfile

from kll1 import Replay
from test_real_title_vram_parity import make_ref


def chunks(state):
    if state[:5] != b"\x00\x01\x00\x00\x00":
        raise ValueError("unsupported Gambatte state format")
    result = {}
    offset = 5
    while offset < len(state) and state[offset]:
        end = state.index(0, offset)
        key = state[offset:end].decode("ascii")
        size = int.from_bytes(state[end + 1:end + 4], "big")
        offset = end + 4
        result[key] = state[offset:offset + size]
        offset += size
    return result


def actor_digest(ram):
    blocks = []
    for base, count in ((0x400, 1), (0x600, 7)):
        for index in range(count):
            record = bytearray(ram[base + index * 0x24:base + (index + 1) * 0x24])
            for offset in (7, 10):
                pointer = int.from_bytes(record[offset:offset + 2], "little")
                if 0x25AA <= pointer < 0x2990:
                    record[offset:offset + 2] = (pointer + 0x4000).to_bytes(2, "little")
            blocks.append(record)
    return hashlib.sha256(b"".join(blocks)).hexdigest()


def buttons(frame, active):
    if not active or frame < 2400:
        return []
    phase = (frame - 2400) % 240
    held = ["RIGHT"] if phase < 80 else ["LEFT"] if phase < 160 else []
    if phase in (16, 17, 96, 97):
        held.append("A")
    if 40 <= phase < 220:
        held.append("B")
    return held


def worker(args):
    replay = Replay(args.rom)
    replay.start_round_three()
    records = []
    while replay.frame <= args.end:
        if replay.frame >= 2300:
            state = chunks(replay.emulator.get_state())
            ram, vram, hram = state["wram"], state["vram"], state["hram"]
            records.append({
                "frame": replay.frame,
                "round": ram[0x200],
                "timer": hram[0x1BE:0x1C0].hex(),
                "actors": actor_digest(ram),
                "sprite_streams": hram[0x19F:0x1A3].hex(),
                "collision": hashlib.sha256(ram[0x1800:0x1C00]).hexdigest(),
                "tiles": hashlib.sha256(vram[:0x1800]).hexdigest(),
                "maps": hashlib.sha256(vram[0x1800:0x2000]).hexdigest(),
            })
            if args.frames_dir and replay.frame in (2300, 2600, 3243, 3730, 3892, 3962, 4000, 6000):
                from PIL import Image
                args.frames_dir.mkdir(parents=True, exist_ok=True)
                Image.fromarray(replay.emulator.get_screen()).save(
                    args.frames_dir / f"{args.worker}-frame{replay.frame}.png")
                (args.frames_dir / f"{args.worker}-frame{replay.frame}.state").write_bytes(
                    replay.emulator.get_state())
        replay.step(*buttons(replay.frame, args.active))
    print(json.dumps(records))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--end", type=int, default=3600)
    parser.add_argument("--active", action="store_true")
    fields = ("round", "timer", "actors", "sprite_streams", "collision", "tiles", "maps")
    parser.add_argument("--fields", nargs="+", choices=fields, default=fields,
                        help="fields to compare; default: all")
    parser.add_argument("--frames-dir", type=Path)
    parser.add_argument("--worker", choices=("native", "host"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        return worker(args)
    if not args.source:
        parser.error("--source must identify the exact patched BB1 input")
    if hashlib.md5(args.source.read_bytes()).hexdigest() != "b093fd9aa903453c1b30703738159a49":
        parser.error("--source has the wrong MD5")
    if args.end < 2300:
        parser.error("--end must be at least 2300")
    with tempfile.TemporaryDirectory() as directory:
        reference = Path(directory) / "native.gbc"
        host = Path(directory) / "host.gbc"
        make_ref(reference, args.source)
        copyfile(args.rom, host)
        runs = []
        # Stable-Retro permits one emulator per process.
        for name, rom in (("native", reference), ("host", host)):
            command = [sys.executable, str(Path(__file__).resolve()), str(rom),
                       "--worker", name, "--end", str(args.end)]
            if args.active:
                command.append("--active")
            if args.frames_dir:
                command.extend(("--frames-dir", str(args.frames_dir.resolve())))
            result = subprocess.run(command, capture_output=True, text=True, check=True, timeout=60)
            runs.append(json.loads(result.stdout))
        assert len(runs[0]) == len(runs[1]) == args.end - 2299
        failures = []
        unmatched_presentation = []
        state_failures = []
        for native, hosted in zip(*runs):
            assert native["frame"] == hosted["frame"]
            changed = [key for key in args.fields if native[key] != hosted[key]]
            if changed:
                failures.append({"frame": native["frame"], "fields": changed})
            state_changed = [key for key in ("round", "timer", "actors", "collision")
                             if native[key] != hosted[key]]
            if state_changed:
                state_failures.append({"frame": native["frame"], "fields": state_changed})
            index = native["frame"] - 2300
            neighbors = runs[0][max(0, index - 1):index + 2]
            if not any(all(reference[key] == hosted[key] for key in ("tiles", "maps"))
                       for reference in neighbors):
                unmatched_presentation.append(native["frame"])
        counts = Counter(field for failure in failures for field in failure["fields"])
        print(json.dumps({"frames": f"2300-{args.end}", "active": args.active,
                          "compared_fields": args.fields, "mismatch_frames": len(failures), "field_counts": dict(counts),
                          "state_mismatch_frames": len(state_failures),
                          "presentation_unmatched_within_one_frame": unmatched_presentation[:12],
                          "presentation_unmatched_count": len(unmatched_presentation),
                          "first_mismatches": failures[:12], "last_mismatches": failures[-4:]}, indent=2))
        assert not failures, "hosted gameplay differs from native CGB reference"


if __name__ == "__main__":
    main()
