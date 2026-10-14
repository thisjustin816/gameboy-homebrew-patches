#!/usr/bin/env python3
from pathlib import Path
from tempfile import TemporaryDirectory
from shutil import copy2
from pyboy import PyBoy
import argparse

SAVE_ROUND = 0x4061
SENTINEL = 0x00F0
ROUND = 0xC200
FLAGS_A = 0xC4B5
FLAGS_B = 0xC202
H_PHYS = 0xFFD3
H_LOG = 0xFFD6
EXPECTED = bytes.fromhex('b0 b1 00 00 a5')


def read_bank(pb, bank):
    pb.memory[0x0000] = 0x0A
    pb.memory[0x4000] = bank
    data = bytes(pb.memory[0xA000:0xA005])
    pb.memory[0x0000] = 0x00
    return data


def call_save_round(pb):
    pb.memory[0x4000] = 1
    pb.memory[0x2100] = 0x40
    pb.memory[H_PHYS] = 0x40
    pb.memory[H_LOG] = 1
    pb.memory[ROUND] = 0
    pb.memory[FLAGS_A] = 0
    pb.memory[FLAGS_B] = 0
    rf = pb.register_file
    saved = {k: getattr(rf, k) for k in ('A','F','B','C','D','E','HL','SP','PC')}
    result = {}
    done = {'value': False}

    def leave(_):
        if done['value']:
            return
        result.update({k: getattr(rf, k) for k in ('A','F','B','C','D','E','HL','SP')})
        for k, value in saved.items():
            setattr(rf, k, value)
        done['value'] = True

    pb.hook_register(0, SENTINEL, leave, None)
    rf.SP = (saved['SP'] - 2) & 0xFFFF
    pb.memory[rf.SP] = SENTINEL & 0xFF
    pb.memory[(rf.SP + 1) & 0xFFFF] = SENTINEL >> 8
    rf.PC = SAVE_ROUND
    for _ in range(10):
        pb.tick(1, True)
        if done['value']:
            break
    assert done['value'], 'save_round did not return to sentinel'
    assert result['HL'] == 0xDC80, f"save_round HL=${result['HL']:04X}, expected $DC80"
    assert result['SP'] == saved['SP'], f"save_round SP=${result['SP']:04X}, expected ${saved['SP']:04X}"
    for k in ('A','F','B','C','D','E'):
        assert result[k] == saved[k], f"save_round changed {k}: ${saved[k]:04X} -> ${result[k]:04X}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom', type=Path)
    args = ap.parse_args()
    with TemporaryDirectory() as td:
        p = Path(td) / 'bbdx.gbc'
        copy2(args.rom, p)
        pb = PyBoy(str(p), window='null', sound_emulated=False)
        pb.tick(700, True)
        before = [read_bank(pb, b) for b in range(4)]
        call_save_round(pb)
        after = [read_bank(pb, b) for b in range(4)]
        pb.memory[0x4000] = 1
        pb.stop(save=True)

        ram = Path(str(p) + '.ram')
        assert ram.exists(), 'PyBoy did not write cartridge RAM'
        raw = ram.read_bytes()
        assert len(raw) == 0x8000, f'RAM size={len(raw)}, expected 32768'
        raw_heads = [raw[b*0x2000:b*0x2000+5] for b in range(4)]

        pb2 = PyBoy(str(p), window='null', sound_emulated=False)
        pb2.tick(20, True)
        persisted = [read_bank(pb2, b) for b in range(4)]
        pb2.stop(save=False)

        print('before=' + ','.join(x.hex() for x in before))
        print('after=' + ','.join(x.hex() for x in after))
        print('ram=' + ','.join(x.hex() for x in raw_heads))
        print('powercycle=' + ','.join(x.hex() for x in persisted))

        assert after[1] == EXPECTED, f'bank1={after[1].hex()}, expected={EXPECTED.hex()}'
        for bank in (0, 2, 3):
            assert after[bank] == before[bank], f'bank {bank} changed: {before[bank].hex()} -> {after[bank].hex()}'
        assert raw_heads == after, 'battery-file bank heads differ from live SRAM'
        assert persisted == after, 'power-cycle SRAM differs from saved SRAM'

if __name__ == '__main__':
    main()
