#!/usr/bin/env python3
from emulator import emulator
import argparse
from pathlib import Path
ap = argparse.ArgumentParser()
ap.add_argument('old')
ap.add_argument('tipfit')
ap.add_argument('--out', required=True)
args = ap.parse_args()
Path(args.out).mkdir(parents=True, exist_ok=True)
CASES = {'old': args.old, 'tipfit': args.tipfit}

def s8(v):
    return v - 256 if v >= 128 else v

def run(name, rom):
    with emulator(rom) as p:
        cur = 0
        mask = []

        def hook(ctx):
            if cur == 517:
                hl = int(p.register_file.HL)
                if 0x54fd <= hl < 0x553d:
                    mask.append((hl, hl - 0x54fd, int(p.memory[6, hl]), int(p.memory[0xc005]), int(p.memory[0xc004]), s8(int(p.memory[0xd9d9])), s8(int(p.memory[0xd9da]))))
        p.hook_register(6, 0x59a3, hook, None)
        for f in range(900):
            p.tick(1, f >= 760)
        rows = {}
        for fr in range(1, 519):
            cur = fr
            ph = fr % 18
            if ph == 1:
                p.button_press('left')
                p.button_press('right')
            elif ph == 7:
                p.button_release('left')
                p.button_release('right')
            p.tick(1, True)
            if fr in (516, 517, 518):
                rows[fr] = (s8(int(p.memory[0xd9d9])), s8(int(p.memory[0xd9da])), int(p.memory[0xc005]), int(p.memory[0xc004]))
                p.screen.image.convert('RGB').save(str(Path(args.out) / f'{name}_tip_reg_{fr}.png'))
        return (mask, rows)
res = {n: run(n, r) for n, r in CASES.items()}
for n, (m, r) in res.items():
    print(n, 'mask', m, 'rows', r)
old = res['old']
new = res['tipfit']
assert any((x[1] == 13 and x[2] & 1 and (x[4] == 139) for x in old[0])), old
assert not any((x[1] == 13 and x[2] & 1 for x in new[0])), new
assert old[1][517][:2] == new[1][517][:2] == (-7, -44), (old[1], new[1])
assert new[1][517][3] >= old[1][517][3] + 1, (old[1], new[1])
print('PASS old buffered tip -> TipFit deeper visual contact with identical bounce')
