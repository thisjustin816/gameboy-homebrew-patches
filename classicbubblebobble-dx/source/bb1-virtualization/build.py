#!/usr/bin/env python3
"""Build an explicitly selected BB1 diagnostic from exact patched inputs."""
import argparse
import importlib.util
import shutil
from pathlib import Path

VARIANTS = {
    "baseline-v0.14": "baseline_v014.py",
    "edgeprobe18b": "edgeprobe18b.py",
    "control-fix": "prototype.py",
    "graphics-experiment": "graphics_experiment.py",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("classic", type=Path)
    parser.add_argument("bb1", type=Path)
    parser.add_argument("bb2", type=Path)
    parser.add_argument("--variant", choices=VARIANTS, required=True)
    parser.add_argument("--rgbds", type=Path, help="directory containing rgbasm and rgblink")
    parser.add_argument("-o", "--output", type=Path, required=True)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location("bb1_builder", here / VARIANTS[args.variant])
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    builder.CLASSIC, builder.BB1, builder.BB2 = args.classic, args.bb1, args.bb2
    for attribute, command in (("RGBASM", "rgbasm"), ("RGBLINK", "rgblink")):
        executable = args.rgbds / command if args.rgbds else shutil.which(command)
        if not executable or not Path(executable).is_file():
            parser.error(f"{command} is missing; pass --rgbds or add RGBDS to PATH")
        setattr(builder, attribute, Path(executable))
    builder.OUT = args.output.resolve()
    builder.OUT.parent.mkdir(parents=True, exist_ok=True)
    builder.BUILD = builder.OUT.parent / (builder.OUT.stem + "-build")
    builder.main()
    print(f"variant={args.variant}")


if __name__ == "__main__":
    main()
