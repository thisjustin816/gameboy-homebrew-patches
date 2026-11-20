#!/usr/bin/env python3
import argparse
from pathlib import Path
from emulator import emulator

def s8(v):
    return v - 256 if v >= 128 else v

def verify(rom):
    with emulator(str(rom)) as p:
        for _ in range(850):
            p.tick(render=False, sound=False)
        p.tick(render=True, sound=False)
        o = bytes(p.memory[0xfe00:0xfea0])
        marker0 = o[29]
        vx0 = s8(int(p.memory[0xd9d9]))
        vy0 = s8(int(p.memory[0xd9da]))
        p.button_press('left')
        for _ in range(12):
            p.tick(render=False, sound=False)
        p.button_release('left')
        p.tick(render=False, sound=False)
        o = bytes(p.memory[0xfe00:0xfea0])
        marker1 = o[29]
        p.button('a', delay=2)
        launched = None
        vals = []
        for fr in range(1, 8):
            p.tick(render=False, sound=False)
            vx = s8(int(p.memory[0xd9d9]))
            vy = s8(int(p.memory[0xd9da]))
            vals.append((fr, vx, vy))
            if launched is None and (vx != 0 or vy != 0):
                launched = fr
        return (marker0, marker1, vx0, vy0, launched, vals)
parser = argparse.ArgumentParser(description="Check direct pachinko boot, marker movement, and launch")
parser.add_argument("roms", nargs="+")
for arg in parser.parse_args().roms:
    r = verify(Path(arg))
    print(Path(arg).name, 'marker', r[0], '->', r[1], 'prevel', r[2], r[3], 'launch_frame', r[4], 'vels', r[5])
    if not (r[0] == 88 and r[1] < r[0] and (r[4] is not None)):
        raise SystemExit(1)
