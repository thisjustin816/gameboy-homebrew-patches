#!/usr/bin/env python3
import argparse, json
from emulator import emulator, load_state
STATE = None
BASE = None
FRAMES = 480

def s8(v):
    return v - 256 if v >= 128 else v

def run(rom, move, hold):
    with emulator(rom) as p:
        load_state(p, STATE)
        if move and hold:
            p.button_press(move)
            for _ in range(hold):
                p.tick(render=False, sound=False)
            p.button_release(move)
            for _ in range(5):
                p.tick(render=False, sound=False)
        o = bytes(p.memory[0xfe00:0xfea0])
        marker_x = o[29]
        p.button('a', delay=2)
        started = False
        first = None
        reset = None
        rows = []
        for fr in range(1, FRAMES + 1):
            p.tick(render=False, sound=False)
            o = bytes(p.memory[0xfe00:0xfea0])
            y, x = (o[0], o[1])
            vx = s8(int(p.memory[0xd9d9]))
            vy = s8(int(p.memory[0xd9da]))
            if (x, y) != (40, 96):
                started = True
                if first is None:
                    first = fr
            if started and (x, y) == (40, 96) and (fr > 20) and (reset is None):
                reset = fr
            rows.append((fr, x, y, vx, vy))
        active = [r for r in rows if first is not None and r[0] >= first and (reset is None or r[0] < reset)]
        return dict(marker_x=marker_x, launch_frame=first, reset_frame=reset, active_frames=None if first is None else (reset or FRAMES + 1) - first, x_min=min((r[1] for r in active), default=None), x_max=max((r[1] for r in active), default=None), y_min=min((r[2] for r in active), default=None), y_max=max((r[2] for r in active), default=None), vx_changes=sum((a[3] != b[3] for a, b in zip(active, active[1:]))), vy_changes=sum((a[4] != b[4] for a, b in zip(active, active[1:]))))

def main():
    global STATE, BASE
    ap = argparse.ArgumentParser()
    ap.add_argument('candidate')
    ap.add_argument('--out', required=True)
    ap.add_argument('--stock', required=True)
    ap.add_argument('--state', required=True)
    args = ap.parse_args()
    BASE = args.stock
    STATE = args.state
    cases = [('center', None, 0)]
    for move in ('left', 'right'):
        for hold in (5, 10, 15, 20, 25, 30):
            cases.append((f'{move}{hold}', move, hold))
    result = []
    for variant, rom in [('base', BASE), ('candidate', args.candidate)]:
        for name, move, hold in cases:
            r = run(rom, move, hold)
            r.update(variant=variant, case=name, move=move, hold=hold)
            result.append(r)
    with open(args.out, 'w') as f:
        json.dump(result, f, indent=2)
    for variant in ('base', 'candidate'):
        rr = [r for r in result if r['variant'] == variant]
        missing = [r for r in rr if r['reset_frame'] is None]
        print(variant, 'cases', len(rr), 'distinct_marker_x', len(set((r['marker_x'] for r in rr))), 'no_reset', len(missing))
        for r in rr:
            print(' ', r['case'], 'mx', r['marker_x'], 'reset', r['reset_frame'], 'bounds', r['x_min'], r['x_max'], r['y_min'], r['y_max'])
    if any((r['reset_frame'] is None for r in result if r['variant'] == 'candidate')):
        raise SystemExit(1)
if __name__ == '__main__':
    main()
