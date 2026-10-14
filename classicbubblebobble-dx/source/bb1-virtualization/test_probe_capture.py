#!/usr/bin/env python3
"""Check the edgeprobe18b fallback's first captured word against live RAM."""
import argparse
import json
import tempfile
from pathlib import Path
from shutil import copyfile

from kll1 import Replay


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        rom = Path(directory) / args.rom.name
        copyfile(args.rom, rom)
        replay = Replay(rom)
        replay.start_round_three()
        replay.data.memory.assign(0xFFF9, "|u1", 0x5A)
        for _ in range(100):
            if replay.read(0xFFEB) == 0xC4:
                break
            replay.step()
        assert replay.read(0xFFEB) == 0xC4, "fallback trap did not fire"
        stack = replay.read(0xFFE3) | replay.read(0xFFE4) << 8
        captured = replay.read(0xFFE6) | replay.read(0xFFE7) << 8
        actual = replay.read(stack) | replay.read((stack + 1) & 0xFFFF) << 8
        print(json.dumps({"frame": replay.frame, "stack": hex(stack),
                          "captured": hex(captured), "actual": hex(actual)}, indent=2))
        assert captured == actual, "stack capture lost or misplaced a byte"


if __name__ == "__main__":
    main()
