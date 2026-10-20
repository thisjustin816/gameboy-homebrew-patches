#!/usr/bin/env python3
"""Check native and hosted round transitions by clearing the enemy counter.

This exercises the native round loader with forced clears, not normal victories.
It checks progress and stable round state independently of emulator-frame phase.
"""
import argparse
import hashlib
import json
from pathlib import Path
from shutil import copyfile
import subprocess
import sys
import tempfile

from kll1 import Replay
from test_real_title_vram_parity import make_ref


def worker(args):
    replay = Replay(args.rom)
    replay.start_round_three()
    replay.step(frames=2300 - replay.frame)
    assert replay.read(0xC200) == 2
    records = []
    for expected in range(3, args.last_index + 1):
        replay.data.memory.assign(0xFFC3, "|u1", 0)
        deadline = replay.frame + 900
        while replay.read(0xC200) != expected and replay.frame < deadline:
            replay.step()
        actual = replay.read(0xC200)
        assert actual == expected, f"frame {replay.frame}: expected round index {expected}, got {actual}"
        entered = replay.frame
        replay.step(frames=300)
        assert replay.read(0xC200) == expected, f"round index {expected} did not persist"
        records.append({"round_index": expected, "entered_frame": entered,
                        "stable_through_frame": replay.frame})
    print(json.dumps(records))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--last-index", type=int, default=8)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 3 <= args.last_index <= 20:
        parser.error("--last-index must be 3-20")
    if args.worker:
        return worker(args)
    if not args.source or hashlib.md5(args.source.read_bytes()).hexdigest() != "b093fd9aa903453c1b30703738159a49":
        parser.error("--source must identify the exact patched BB1 input")
    with tempfile.TemporaryDirectory() as directory:
        native, host = Path(directory) / "native.gbc", Path(directory) / "host.gbc"
        make_ref(native, args.source)
        copyfile(args.rom, host)
        for name, rom in (("native", native), ("host", host)):
            command = [sys.executable, str(Path(__file__).resolve()), str(rom), "--worker",
                       "--last-index", str(args.last_index)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            if result.returncode:
                raise RuntimeError(f"{name} worker failed:\n{result.stderr}")
            print(json.dumps({"worker": name, "forced_clear_progress": json.loads(result.stdout)}, indent=2))


if __name__ == "__main__":
    main()
