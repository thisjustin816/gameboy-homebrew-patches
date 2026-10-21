#!/usr/bin/env python3
"""Resume real menu-created saves in fresh Gambatte processes.

Only cartridge SRAM crosses the restart, through a temporary battery file.
Gambatte exposes no battery-file API here, so the reader inserts those bytes
into its untouched, pre-boot state. CPU, WRAM, VRAM, and mapper state stay cold.
This checks the emulator's SRAM contract, not physical cartridge persistence.
"""
import argparse
import hashlib
import json
from pathlib import Path
from shutil import copyfile
import subprocess
import sys
import tempfile

from generate_password_fixtures import letters
from gameplay import chunks
from kll1 import Replay
from test_real_title_vram_parity import make_ref


def load_battery(replay, battery):
    state = replay.emulator.get_state()
    original = chunks(state)["sram"]
    assert len(battery) == len(original), "battery capacity differs from cartridge"
    marker = b"sram\0" + len(original).to_bytes(3, "big")
    assert state.count(marker) == 1, "ambiguous SRAM state field"
    offset = state.index(marker) + len(marker)
    replay.emulator.set_state(state[:offset] + battery + state[offset + len(original):])


def worker(args):
    replay = Replay(args.rom)
    bank = 0 if args.worker.startswith("native") else 1
    capacity = len(chunks(replay.emulator.get_state())["sram"])
    if args.worker.endswith("write"):
        # Non-save banks carry distinct fingerprints throughout actual gameplay.
        initial = bytearray(b"\xff" * capacity)
        for index in range(capacity // 0x2000):
            if index != bank:
                initial[index * 0x2000:(index + 1) * 0x2000] = bytes([0x30 + index]) * 0x2000
        load_battery(replay, initial)
        replay.start_password(args.password)
        replay.step(frames=300)
        # The round-one password returns to the title before START is ready.
        if args.round == 0:
            replay.press("START")
            replay.step(frames=300)
        assert replay.read(0xC200) == args.round
        saved = chunks(replay.emulator.get_state())["sram"]
        offset = bank * 0x2000
        expected = bytes((0xB0, 0xB1, args.round, 0, args.round ^ 0xA5))
        assert saved[offset:offset + 5] == expected, "game did not write the expected save"
        assert saved[:offset] == initial[:offset], "earlier SRAM bank changed"
        assert saved[offset + 5:] == initial[offset + 5:], "unrelated SRAM bytes changed"
        args.battery.write_bytes(saved)
        print(json.dumps({"save": expected.hex(), "capacity": capacity,
                          "sha256": hashlib.sha256(saved).hexdigest()}))
    else:
        saved = args.battery.read_bytes()
        if bank == 1 and args.resume_bank == 0:
            # Failure control: put the valid BB1 save in the collection's bank 0.
            saved = saved[0x2000:0x4000] + b"\xff" * 0x2000 + saved[0x4000:]
        load_battery(replay, saved)
        replay.open_password_menu()
        actual = bytes(replay.read(0xC914 + index) for index in range(4))
        assert letters(actual) == args.password, f"prefill {actual.hex()} != {args.password}"
        assert replay.read(0xC911) == 24 and replay.read(0xC913) == 3, "END is not selected"
        replay.step(frames=400)
        replay.press("A", after=150)
        replay.step("START", frames=5)
        replay.step(frames=300)
        assert replay.read(0xC200) == args.round, "accepted save resumed the wrong round"
        assert replay.read(0xC400) != 0, "resume did not start the player"
        assert replay.read(0xC4B5) == 0, "resume changed prior-win flags"
        assert chunks(replay.emulator.get_state())["sram"] == saved, "resume altered unrelated battery data"
        print(json.dumps({"round_index": args.round, "prefill": actual.hex(), "menu_accepted": True}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--cases", nargs="+", type=int, default=[0, 2, 24, 49, 99])
    parser.add_argument("--resume-bank", type=int, choices=(0, 1), default=1,
                        help="bank 0 is an intentional host failure control")
    parser.add_argument("--worker", choices=("native-write", "native-read", "host-write", "host-read"), help=argparse.SUPPRESS)
    parser.add_argument("--battery", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--password", help=argparse.SUPPRESS)
    parser.add_argument("--round", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        return worker(args)
    if not args.source or hashlib.md5(args.source.read_bytes()).hexdigest() != "b093fd9aa903453c1b30703738159a49":
        parser.error("--source must be the exact supported patched BB1 ROM")
    if not args.cases or any(index not in range(100) for index in args.cases):
        parser.error("--cases must contain round indices 0 through 99")
    fixtures = json.loads(Path(__file__).with_name("password-fixtures.json").read_text())
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        native = root / "native.gbc"
        make_ref(native, args.source)
        host = root / "host.gbc"
        copyfile(args.rom, host)
        results = []
        for index in args.cases:
            case = {"round_index": index}
            for name, rom in (("native", native), ("host", host)):
                battery = root / f"{name}-{index}.sav"
                case[name] = {}
                for phase in ("write", "read"):
                    command = [sys.executable, str(Path(__file__).resolve()), str(rom),
                               "--worker", f"{name}-{phase}", "--battery", str(battery),
                               "--round", str(index), "--password", fixtures["passwords"][str(index)],
                               "--resume-bank", str(args.resume_bank)]
                    result = subprocess.run(command, capture_output=True, text=True, timeout=30)
                    if result.returncode:
                        raise RuntimeError(f"round {index} {name}-{phase}:\n{result.stderr}")
                    case[name][phase] = json.loads(result.stdout)
            assert case["native"]["write"]["save"] == case["host"]["write"]["save"]
            assert case["native"]["read"] == case["host"]["read"]
            results.append(case)
        print(json.dumps({"cases": results, "method": "fresh processes, battery bytes only"}, indent=2))


if __name__ == "__main__":
    main()
