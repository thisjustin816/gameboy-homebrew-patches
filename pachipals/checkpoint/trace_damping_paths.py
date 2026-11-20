#!/usr/bin/env python3
from collections import Counter, defaultdict
from emulator import emulator, load_state
import argparse
SITES = {10: [0x4aab, 0x5779, 0x5842, 0x5907, 0x59d1, 0x5a9f, 0x5b68, 0x5c2d, 0x5cf3, 0x5db6, 0x5e7d, 0x5f49, 0x6015, 0x60e1, 0x61ad, 0x6279, 0x6347, 0x6410, 0x64da, 0x65a8, 0x6671, 0x6741, 0x6805, 0x68cc], 20: [0x573d, 0x610a, 0x61d1, 0x6296, 0x6360, 0x6425, 0x64ee, 0x65b9, 0x6687, 0x6753, 0x681d, 0x68e2, 0x69a8, 0x6a72, 0x6b35, 0x6c01, 0x6cc5, 0x6db6, 0x6e81, 0x6f45, 0x700b, 0x70d7, 0x71a0, 0x7264, 0x732d, 0x73fb, 0x74c4, 0x7589, 0x764f, 0x7712, 0x77d9, 0x78a5, 0x796d, 0x7a30, 0x7af7, 0x7bc3, 0x7c8a, 0x7d4f, 0x7e48, 0x7f16], 25: [0x5b0e, 0x62dc, 0x63a5, 0x646a, 0x6520, 0x65c0, 0x665f, 0x69ed, 0x6a8f, 0x6b3b, 0x6bfe, 0x6cc5, 0x6d91, 0x6e58, 0x6f1e, 0x6fe1, 0x70a8, 0x7174, 0x723b, 0x72fd, 0x73c1, 0x7484, 0x754e, 0x7610, 0x76dc, 0x779e, 0x7a82, 0x7b26, 0x7bc6, 0x7c61, 0x7df5, 0x7ec0, 0x7f8e]}
ap = argparse.ArgumentParser()
ap.add_argument('rom')
ap.add_argument('state')
args = ap.parse_args()
with emulator(args.rom) as p:
    hits = Counter()
    ptrs = defaultdict(Counter)
    ctx = {'py': p}

    def mk(bank, addr):

        def cb(c):
            py = c['py']
            ptr = int(py.memory[0xd9d5]) | int(py.memory[0xd9d6]) << 8
            cls = 'object' if 0xc100 <= ptr < 0xd000 else 'board'
            hits[bank, addr, cls] += 1
            ptrs[bank, addr][ptr] += 1
        return cb
    for bank, addrs in SITES.items():
        for addr in addrs:
            p.hook_register(bank, addr, mk(bank, addr), ctx)
    cases = [(None, 0)] + [(m, h) for m in ('left', 'right') for h in (5, 10, 15, 20, 25, 30)]
    for move, hold in cases:
        load_state(p, args.state)
        if move:
            p.button_press(move)
            for _ in range(hold):
                p.tick(render=False, sound=False)
            p.button_release(move)
            for _ in range(5):
                p.tick(render=False, sound=False)
        p.button('a', delay=2)
        for _ in range(480):
            p.tick(render=False, sound=False)
    for bank, addr in sorted(set(((b, a) for b, a, _ in hits))):
        print(f"{bank:02X}:{addr:04X} board={hits[bank, addr, 'board']} object={hits[bank, addr, 'object']} ptrs={{{', '.join((f'{k:04X}:{v}' for k, v in ptrs[bank, addr].most_common()))}}}")
