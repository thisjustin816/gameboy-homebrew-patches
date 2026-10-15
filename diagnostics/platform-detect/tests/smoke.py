#!/usr/bin/env python3
from pathlib import Path
import sys

from pyboy import PyBoy

ROM = Path(__file__).resolve().parents[1] / "platform-detect.gbc"


def boot_mode(cgb: bool) -> tuple[int, int]:
    pyboy = PyBoy(str(ROM), window="null", sound_emulated=False, cgb=cgb)
    try:
        pyboy.tick(240, True)
        image = pyboy.screen.image.convert("RGB")
        if image.getbbox() is None:
            raise AssertionError(f"{'CGB' if cgb else 'DMG'} screen is blank")
        return pyboy.memory[0xFF72], pyboy.memory[0xFF73]
    finally:
        pyboy.stop(save=False)


def main() -> int:
    if not ROM.exists():
        print(f"missing ROM: {ROM}", file=sys.stderr)
        return 2

    try:
        cgb72, cgb73 = boot_mode(True)
        dmg72, dmg73 = boot_mode(False)
    except AssertionError as exc:
        print(f"FAIL: {exc}")
        return 1

    print(f"PASS: CGB boot rendered; restored FF72={cgb72:02X} FF73={cgb73:02X}")
    print(f"PASS: DMG boot rendered; CGB-only reads FF72={dmg72:02X} FF73={dmg73:02X}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
