#!/usr/bin/env python3
"""Compare KLL1 gameplay with native BB1 on CGB, frame by frame.

The native reference changes only the CGB header and checksums. RAM descriptor
pointers are normalized for their documented relocation; gameplay fields,
collision data, score, objects, and tile graphics must match exactly. Tile maps
must match whenever the LCD is enabled; --include-lcd-off-maps also compares
partial map clears while both displays are off. Sound registers and wave RAM
are compared as stored state, without establishing waveform or audible parity.
--clock game drives inputs by
$FF93 VBlank ticks; emulator-frame mode preserves the original wall-time replay.
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

from gameplay import buttons, chunks, record_digest
from kll1 import Replay
from test_real_title_vram_parity import make_ref


def worker(args):
    replay = Replay(args.rom)
    replay.start_round_three()
    records = []
    sample_frame = replay.frame
    previous_tick = replay.read(0xFF93)
    initial_tick = previous_tick
    clock_deltas = Counter()
    while sample_frame <= args.end:
        if replay.frame > args.end * 2 + 5000:
            state = chunks(replay.emulator.get_state())
            if args.frames_dir:
                args.frames_dir.mkdir(parents=True, exist_ok=True)
                (args.frames_dir / f"{args.worker}-stalled.state").write_bytes(replay.emulator.get_state())
            raise RuntimeError(f"game clock stalled at tick {sample_frame}, emulator frame {replay.frame}, "
                               f"PC={state['pc'].hex()}, SP={state['sp'].hex()}")
        if sample_frame >= 2300:
            raw_state = replay.emulator.get_state()
            state = chunks(raw_state)
            ram, vram, hram = state["wram"], state["vram"], state["hram"]
            record = {
                "frame": sample_frame,
                "lcd_enabled": bool(hram[0x140] & 0x80),
                "round": ram[0x200],
                "sound_registers": hram[0x110:0x126].hex(),
                "wave_ram": state["waveram"].hex(),
                "timer": hram[0x1BE:0x1C0].hex(),
                "actors": record_digest(ram, ((0x400, 1, 0x24), (0x600, 7, 0x24))),
                "objects": record_digest(ram, ((0x500, 15, 0x10),)),
                "score": ram[0x490:0x493].hex(),
                "sprite_streams": hram[0x19F:0x1A3].hex(),
                "collision": hashlib.sha256(ram[0x1800:0x1C00]).hexdigest(),
                "tiles": hashlib.sha256(vram[:0x1800]).hexdigest(),
                "maps": hashlib.sha256(vram[0x1800:0x2000]).hexdigest(),
            }
            # LCD changes can make an emulator step span zero or two game ticks.
            # Keep the latest sample for a repeated tick; report skipped ticks.
            if records and records[-1]["frame"] == sample_frame:
                records[-1] = record
            else:
                records.append(record)
            if args.frames_dir and sample_frame in (
                    2300, 2600, 3243, 3730, 3892, 3940, 3962, 4000,
                    5876, 6000, 6036, 6037, 6038, 6100):
                from PIL import Image
                args.frames_dir.mkdir(parents=True, exist_ok=True)
                Image.fromarray(replay.emulator.get_screen()).save(
                    args.frames_dir / f"{args.worker}-frame{sample_frame}.png")
                (args.frames_dir / f"{args.worker}-frame{sample_frame}.state").write_bytes(
                    replay.emulator.get_state())
        replay.step(*buttons(sample_frame, args.active))
        if args.clock == "game":
            tick = replay.read(0xFF93)
            delta = (tick - previous_tick) & 255
            if delta > 2:
                if args.frames_dir:
                    from PIL import Image
                    args.frames_dir.mkdir(parents=True, exist_ok=True)
                    prefix = args.frames_dir / f"{args.worker}-reset-tick{sample_frame}"
                    prefix.with_suffix(".state").write_bytes(replay.emulator.get_state())
                    Image.fromarray(replay.emulator.get_screen()).save(prefix.with_suffix(".png"))
                    if sample_frame >= 2300:
                        Path(str(prefix) + "-before.state").write_bytes(raw_state)
                raise RuntimeError(f"game counter reset or jumped: {previous_tick}->{tick}, "
                                   f"game tick {sample_frame}, emulator frame {replay.frame}")
            clock_deltas[delta] += 1
            sample_frame += delta
            previous_tick = tick
        else:
            sample_frame = replay.frame
    print(json.dumps({"records": records, "emulator_frames": replay.frame,
                      "clock_deltas": dict(clock_deltas), "initial_game_tick": initial_tick}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rom", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--end", type=int, default=6000)
    parser.add_argument("--active", action="store_true")
    parser.add_argument("--clock", choices=("emulator", "game"), default="emulator",
                        help="drive inputs by emulator frames or the game's VBlank counter")
    fields = ("sound_registers", "wave_ram", "lcd_enabled", "round", "timer", "actors",
              "objects", "score", "sprite_streams", "collision", "tiles", "maps")
    parser.add_argument("--fields", nargs="+", choices=fields,
                        help="default: gameplay/graphics; game clock also includes sound state")
    parser.add_argument("--frames-dir", type=Path)
    parser.add_argument("--include-lcd-off-maps", action="store_true")
    parser.add_argument("--worker", choices=("native", "host"), help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.fields is None:
        # Sound writes follow game ticks; wall-frame samples can straddle them.
        args.fields = fields if args.clock == "game" else tuple(
            field for field in fields if field not in ("sound_registers", "wave_ram"))
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
                       "--worker", name, "--end", str(args.end), "--clock", args.clock]
            if args.active:
                command.append("--active")
            if args.frames_dir:
                command.extend(("--frames-dir", str(args.frames_dir.resolve())))
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            if result.returncode:
                raise RuntimeError(f"{name} worker failed:\n{result.stderr}")
            runs.append(json.loads(result.stdout))
        metadata = [{key: value for key, value in run.items() if key != "records"}
                    for run in runs]
        if args.clock == "game":
            assert metadata[0]["initial_game_tick"] == metadata[1]["initial_game_tick"], "game clocks start at different ticks"
        runs = [run["records"] for run in runs]
        assert all(runs), "no comparable samples"
        sample_keys = [[record["frame"] for record in run] for run in runs]
        assert sample_keys[0] == sample_keys[1], "emulators sampled different game ticks"
        assert sample_keys[0] == sorted(set(sample_keys[0])), "unordered or duplicate samples"
        missed_samples = sorted(set(range(2300, args.end + 1)) - set(sample_keys[0]))
        if args.clock == "emulator":
            assert not missed_samples
        failures = []
        lcd_off_map_mismatches = []
        state_failures = []
        for native, hosted in zip(*runs):
            assert native["frame"] == hosted["frame"]
            changed = [key for key in args.fields if native[key] != hosted[key]]
            if not native["lcd_enabled"] and not hosted["lcd_enabled"] and "maps" in changed:
                lcd_off_map_mismatches.append(native["frame"])
                if not args.include_lcd_off_maps:
                    changed.remove("maps")
            if changed:
                failures.append({"frame": native["frame"], "fields": changed})
            state_changed = [key for key in args.fields
                             if key in ("lcd_enabled", "round", "timer", "actors", "objects", "score", "collision")
                             and native[key] != hosted[key]]
            if state_changed:
                state_failures.append({"frame": native["frame"], "fields": state_changed})
        counts = Counter(field for failure in failures for field in failure["fields"])
        print(json.dumps({"frames": f"2300-{args.end}", "clock": args.clock, "active": args.active,
                          "sample_count": len(runs[0]), "missed_samples": missed_samples,
                          "worker_clocks": dict(zip(("native", "host"), metadata)),
                          "round_indices": sorted({record["round"] for record in runs[0]}),
                          "compared_fields": args.fields, "mismatch_frames": len(failures), "field_counts": dict(counts),
                          "state_mismatch_frames": len(state_failures),
                          "include_lcd_off_maps": args.include_lcd_off_maps,
                          "lcd_off_map_mismatch_frames": lcd_off_map_mismatches,
                          "first_mismatches": failures[:12], "last_mismatches": failures[-4:]}, indent=2))
        assert not failures, "hosted gameplay differs from native CGB reference"


if __name__ == "__main__":
    main()
