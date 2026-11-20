#!/usr/bin/env python3
import argparse
from emulator import emulator, load_state
ap = argparse.ArgumentParser()
ap.add_argument('rom')
ap.add_argument('--state', required=True)
ap.add_argument('--max-hold', type=int, default=60)
args = ap.parse_args()
with emulator(args.rom) as p:
    load_state(p, args.state)
    for b in ('left', 'right', 'up', 'down', 'a', 'b', 'start', 'select'):
        try:
            p.button_release(b)
        except Exception:
            pass
    rows = []
    for fr in range(1, 301):
        if fr == 1:
            p.button_press('left')
        if fr == 5:
            p.button_release('left')
        p.tick(render=False, sound=False)
        vx = int(p.memory[0xd9d9])
        vy = int(p.memory[0xd9da])
        rows.append((int(p.memory[0xc005]), int(p.memory[0xc004]), vx, vy))
    longest = hold = 0
    start = best_start = best_end = None
    for i, (a, b) in enumerate(zip(rows, rows[1:]), start=1):
        held = (a[0], a[1]) == (b[0], b[1]) and (a[2] or a[3])
        if held:
            if hold == 0:
                start = i
            hold += 1
            if hold > longest:
                longest = hold
                best_start = start
                best_end = i + 1
        else:
            hold = 0
            start = None
    print(f'longest_visible_hold_with_velocity={longest} frames range={best_start}-{best_end}')
    if longest > args.max_hold:
        raise SystemExit(f'FAIL: capture ball stalls for {longest} frames (limit {args.max_hold})')
    print('PASS')
