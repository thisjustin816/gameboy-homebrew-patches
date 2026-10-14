#!/usr/bin/env python3
"""Regression for the hosted reset after accepting the KLL1 password.

This checks round state and scheduler progress. It does not establish graphics
parity or complete gameplay correctness.
"""
import argparse
import json
import tempfile
from pathlib import Path
from shutil import copyfile

from kll1 import Replay


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--end", type=int, default=3243)
    parser.add_argument("--arm-probe", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        rom = Path(directory) / args.rom.name
        copyfile(args.rom, rom)
        replay = Replay(rom)
        replay.start_round_three()
        assert args.end > replay.frame
        assert replay.read(0xC200) == 2, "KLL1 did not select round 3"
        if args.arm_probe:
            replay.data.memory.assign(0xFFF9, "|u1", 0x5A)
        first_failure = None
        observations = []
        scheduler_states = set()
        while replay.frame <= args.end:
            observation = replay.observe()
            scheduler_states.add(tuple(observation["scheduler"]))
            if replay.frame % 100 == 0 or replay.frame == args.end:
                observations.append(observation)
            if observation["round_index"] != 2 or (
                args.arm_probe and observation["marker"] in (0xC1, 0xC2, 0xC4)
            ):
                first_failure = observation
                break
            replay.step()
        result = {
            "rom": args.rom.name,
            "first_failure": first_failure,
            "scheduler_states": len(scheduler_states),
            "samples": observations,
        }
        print(json.dumps(result, indent=2))
        assert first_failure is None, "round-start reset or startup trap reproduced"
        assert len(scheduler_states) > 4, "scheduler stopped advancing"


if __name__ == "__main__":
    main()
