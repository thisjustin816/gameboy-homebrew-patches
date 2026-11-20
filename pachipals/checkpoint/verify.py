#!/usr/bin/env python3
"""Rebuild the recovered checkpoint and rerun its emulator regressions."""

import argparse
import importlib.metadata
import json
from pathlib import Path
import re
import subprocess
import sys

from build import PROFILES, build, build_control, identity, restore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stock", type=Path)
    parser.add_argument("battle_state", type=Path)
    parser.add_argument("capture_state", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if importlib.metadata.version("pyboy") != "2.8.1":
        parser.error("This recovered suite requires PyBoy 2.8.1")
    for state, name in ((args.battle_state, "pachipals-battle-phase78.state"),
                        (args.capture_state, "pachipals-capture-scene4E85.state")):
        if identity(state.read_bytes())["sha256"] != PROFILES["states"][name]:
            parser.error(f"Wrong state for {name}")
    stock = args.stock.read_bytes()
    if identity(stock) != PROFILES["input"]:
        parser.error("Wrong pristine ROM")
    # A fresh directory keeps first-run evidence and avoids stale output.
    args.out.mkdir(parents=True, exist_ok=False)
    receipt = {"pyboy": "2.8.1", "roms": {}, "checks": []}
    for name in (*PROFILES["profiles"], *PROFILES["controls"]):
        data = build(stock, name) if name in PROFILES["profiles"] else build_control(stock, name)
        if name in PROFILES["profiles"] and restore(data, name) != stock:
            raise RuntimeError(f"Exact restoration failed: {name}")
        (args.out / f"{name}.gbc").write_bytes(data)
        receipt["roms"][name] = identity(data)

    def rom(name):
        return str((args.out / f"{name}.gbc").resolve())

    def run(name, script, arguments, expected_failure=False):
        command = [sys.executable, str(Path(__file__).with_name(script)), *map(str, arguments)]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        (args.out / f"{name}.txt").write_text(result.stdout)
        passed = (result.returncode == 1 and "AssertionError" in result.stdout
                  if expected_failure else result.returncode == 0)
        receipt["checks"].append({"name": name, "exit_code": result.returncode,
                                  "expected_failure": expected_failure, "passed": passed})
        (args.out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        if not passed:
            raise RuntimeError(f"Check failed: {name}; inspect its log")
        print(f"PASS {name}", flush=True)
        return result.stdout

    run("direct-boot", "verify_direct.py", [rom(f"pachinko-{c}") for c in "def"])
    for candidate in "def":
        run(f"battle-{candidate}", "battle_sweep.py", [rom(f"pachinko-{candidate}"),
            "--stock", args.stock, "--state", args.battle_state,
            "--out", args.out / f"battle-{candidate}.json"])
    tip = rom("pinball-tipfit")
    old = rom("pinball-pre-tipfit")
    run("tip-old-fails", "flipper_tip_gap.py", [old, old, "--out", args.out / "tip-old"], True)
    run("tip-new-passes", "flipper_tip_gap.py", [old, tip, "--out", args.out / "tip-new"])
    run("capture-stall", "capture_stall.py", [tip, "--state", args.capture_state])
    run("capture-pulses", "capture_pulse_sweep.py", [tip, "--stock", rom("capture-stock"),
        "--state", args.capture_state, "--out", args.out / "pulses.json"])
    trace = run("damping-trace", "trace_damping_paths.py", [rom("pachinko-d"), args.battle_state])
    hits = [(int(b, 16), int(a, 16), int(board), int(obj)) for b, a, board, obj in
            re.findall(r"([0-9A-F]{2}):([0-9A-F]{4}) board=(\d+) object=(\d+)", trace)]
    passive = {(bank, addr): board for bank, addr, board, _ in hits if board}
    if passive != {(0x19, 0x665F): 22, (0x19, 0x7A82): 13,
                   (0x19, 0x7BC6): 9, (0x19, 0x7C61): 4} or sum(h[3] for h in hits) != 41:
        raise RuntimeError("Recovered damping classification differs from checkpoint")
    receipt["damping_classification"] = {"passive_hits": 48, "object_hits": 41}
    receipt["exact_pristine_restoration"] = list(PROFILES["profiles"])
    receipt["scope"] = "October 27 checkpoint only; later experiments remain unavailable"
    receipt["passed"] = True
    (args.out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print("PASS recovered checkpoint", flush=True)


if __name__ == "__main__":
    main()
