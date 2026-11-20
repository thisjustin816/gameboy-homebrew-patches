#!/usr/bin/env python3
import argparse, json
from emulator import emulator, load_state
STATE = None
BASE = None
FRAMES = 300
BUTTONS = ('left', 'right', 'up', 'down', 'a', 'b', 'start', 'select')

def s8(v):
    return v - 256 if v >= 128 else v

def run(rom, buttons, pulse):
    with emulator(rom) as p:
        load_state(p, STATE)
        for b in BUTTONS:
            try:
                p.button_release(b)
            except Exception:
                pass
        rows = []
        for fr in range(FRAMES):
            if fr == 0:
                for b in buttons:
                    p.button_press(b)
            if fr == pulse:
                for b in buttons:
                    p.button_release(b)
            p.tick(render=False, sound=False)
            rows.append((int(p.memory[0xc005]), int(p.memory[0xc004]), s8(int(p.memory[0xd9d9])), s8(int(p.memory[0xd9da])), int(p.memory[0xd9dd]), int(p.memory[0xd9e3])))
        longest = hold = 0
        start = end = None
        curstart = None
        for i, (a, b) in enumerate(zip(rows, rows[1:]), start=1):
            if a[:2] == b[:2] and (a[2] or a[3]):
                if hold == 0:
                    curstart = i
                hold += 1
                if hold > longest:
                    longest = hold
                    start = curstart
                    end = i + 1
            else:
                hold = 0
                curstart = None
        pos_changes = sum((a[:2] != b[:2] for a, b in zip(rows, rows[1:])))
        return dict(longest_hold=longest, hold_range=[start, end], pos_changes=pos_changes, x_min=min((r[0] for r in rows)), x_max=max((r[0] for r in rows)), y_min=min((r[1] for r in rows)), y_max=max((r[1] for r in rows)), mode_values=sorted(set((r[5] for r in rows))), end=list(rows[-1]))

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
    cases = []
    for name, buttons in [('left', ('left',)), ('a', ('a',)), ('left-a', ('left', 'a')), ('legacy-right', ('right',)), ('legacy-left-right', ('left', 'right'))]:
        for pulse in range(1, 17):
            cases.append((name, pulse, buttons))
    result = []
    for variant, rom in [('base', BASE), ('candidate', args.candidate)]:
        for name, pulse, buttons in cases:
            r = run(rom, buttons, pulse)
            r.update(variant=variant, input=name, pulse=pulse)
            result.append(r)
    with open(args.out, 'w') as f:
        json.dump(result, f, indent=2)
    for variant in ('base', 'candidate'):
        rr = [r for r in result if r['variant'] == variant]
        worst = max(rr, key=lambda r: r['longest_hold'])
        over = [r for r in rr if r['longest_hold'] > 60]
        print(variant, 'cases', len(rr), 'worst_hold', worst['longest_hold'], worst['input'], worst['pulse'], 'range', worst['hold_range'], 'over60', len(over))
        print('  hold_minmax', min((r['longest_hold'] for r in rr)), max((r['longest_hold'] for r in rr)), 'pos_changes_minmax', min((r['pos_changes'] for r in rr)), max((r['pos_changes'] for r in rr)))
    if any((r['longest_hold'] > 60 for r in result if r['variant'] == 'candidate')):
        raise SystemExit(1)
if __name__ == '__main__':
    main()
