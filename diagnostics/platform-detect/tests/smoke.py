#!/usr/bin/env python3
from pathlib import Path
import sys

from pyboy import PyBoy

ROM = Path(__file__).resolve().parents[1] / "platform-detect.gbc"

# GBDK's console font puts ASCII 0x20-0x7F in tiles 0x00-0x5F. Anything else,
# such as the section rule tile, reads as '-'.
def screen_text(pyboy: PyBoy) -> list[str]:
    rows = []
    for y in range(18):
        row = ""
        for x in range(20):
            tile = pyboy.memory[0, 0x9800 + y * 32 + x]
            row += chr(tile + 0x20) if tile < 0x60 else "-"
        rows.append(row.rstrip())
    return rows


def expect(rows: list[str], wanted: str, mode: str) -> None:
    if not any(wanted in row for row in rows):
        shown = "\n".join(rows)
        raise AssertionError(f"{mode} screen lacks {wanted!r}:\n{shown}")


def boot_mode(cgb: bool) -> tuple[int, int]:
    pyboy = PyBoy(str(ROM), window="null", sound_emulated=False, cgb=cgb)
    mode = "CGB" if cgb else "DMG"
    try:
        pyboy.tick(240, True)
        image = pyboy.screen.image.convert("RGB")
        colors = sorted(image.getcolors(maxcolors=65536), reverse=True)
        if len(colors) < 2:
            raise AssertionError(f"{mode} screen is a single color")
        background, text = colors[0][1], colors[1][1]
        if abs(sum(background) - sum(text)) < 300:
            raise AssertionError(f"{mode} text does not contrast with the background")

        rows = screen_text(pyboy)
        if cgb:
            # PyBoy is an emulator with known tells, so the ROM must say so.
            expect(rows, "EMU    LIKELY", mode)
            expect(rows, "NAME   PYBOY", mode)
            expect(rows, "HOST   CGB-LIKE", mode)
            expect(rows, "72 5A>5A A5>A5  OK", mode)
            expect(rows, "73 3C>3C C3>C3  OK", mode)
            expect(rows, "OF 12 FAILED", mode)
        else:
            expect(rows, "HW     DMG", mode)
            expect(rows, "HOST   N/A", mode)
            expect(rows, "CGB ONLY", mode)
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

    print(f"PASS: CGB screen reads EMU LIKELY, NAME PYBOY; restored FF72={cgb72:02X} FF73={cgb73:02X}")
    print(f"PASS: DMG screen reads HW DMG, CGB ONLY; CGB-only reads FF72={dmg72:02X} FF73={dmg73:02X}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
