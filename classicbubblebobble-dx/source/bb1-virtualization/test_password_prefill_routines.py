#!/usr/bin/env python3
from pathlib import Path
from tempfile import TemporaryDirectory
from shutil import copy2
from pyboy import PyBoy
import argparse

PF_INIT = 0x7800
PF_STEP = 0x783D
H_PHYS = 0xFFD3
H_LOG = 0xFFD6
SLOT = 0xC913
BUFFER = 0xC914
SHOWN = 0xC918
PW_FLAGS = 0xC91C
MENU = 0xC911
PF_PENDING = 0xD780
MARK_X = 0xC109
MARK_X2 = 0xC10D
HAND_COL = 0xC912
HAND_Y = 0xC110
HAND_X = 0xC111
HAND_Y2 = 0xC114
HAND_X2 = 0xC115
SAVE = bytes.fromhex('b0 b1 00 00 a5')
PASSWORD_TILES = bytes((31, 21, 21, 1))  # VLL1


def call_upper(pb, addr, regs, sentinel):
    rf = pb.register_file
    pb.memory[0x2100] = 0x43
    pb.memory[H_PHYS] = 0x43
    pb.memory[H_LOG] = 3
    for k, v in regs.items():
        setattr(rf, k, v)
    saved = {k: getattr(rf, k) for k in ('A','F','B','C','D','E','HL','SP','PC')}
    result = {}
    done = {'value': False}

    def leave(_):
        if done['value']:
            return
        result.update({k: getattr(rf, k) for k in ('A','F','B','C','D','E','HL','SP')})
        rf.PC = saved['PC']
        rf.SP = saved['SP']
        done['value'] = True

    pb.hook_register(0, sentinel, leave, None)
    rf.SP = (saved['SP'] - 2) & 0xFFFF
    pb.memory[rf.SP] = sentinel & 0xFF
    pb.memory[(rf.SP + 1) & 0xFFFF] = sentinel >> 8
    rf.PC = addr
    for _ in range(20):
        pb.tick(1, True)
        if done['value']:
            break
    assert done['value'], f'${addr:04X} did not return to sentinel'
    assert result['SP'] == saved['SP'], f'${addr:04X} unbalanced SP'
    return result


def open_copy(src, path, ram=None):
    copy2(src, path)
    if ram is not None:
        Path(str(path) + '.ram').write_bytes(ram)
    pb = PyBoy(str(path), window='null', sound_emulated=False)
    pb.tick(700, True)
    return pb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom', type=Path)
    args = ap.parse_args()
    with TemporaryDirectory() as td:
        td = Path(td)

        # Phase 1: a power-cycle-loaded save in BB1's MBC5 SRAM bank 1 is read
        # by pf_init and encoded with the game's own encoder as VLL1.
        ram = bytearray(0x8000)
        ram[0x2000:0x2005] = SAVE
        pb = open_copy(args.rom, td / 'pf-init.gbc', ram)
        known = dict(A=0, F=0xB0, B=0x11, C=0x22, D=0x33, E=0x44, HL=0x5566)
        pb.memory[SLOT] = 0x77
        pb.memory[PF_PENDING] = 0x55
        for i in range(4):
            pb.memory[SHOWN + i] = 0xEE
        init = call_upper(pb, PF_INIT, known, 0x00F0)
        shown = bytes(pb.memory[SHOWN:SHOWN + 4])
        print('pf_init shown=' + shown.hex() + f' slot={pb.memory[SLOT]} pending={pb.memory[PF_PENDING]}')
        assert shown == PASSWORD_TILES, f'pf_init shown={shown.hex()}, expected VLL1={PASSWORD_TILES.hex()}'
        assert pb.memory[SLOT] == 0 and pb.memory[PF_PENDING] == 1
        assert init['A'] == 0
        for k in ('B','C','D','E','HL'):
            assert init[k] == known[k], f'pf_init changed {k}'
        pb.stop(save=False)

        # Phase 2: from exactly the prefill state produced above, pf_step copies
        # VLL1 into the entry buffer and puts the hand/menu on END.
        pb = open_copy(args.rom, td / 'pf-step.gbc')
        pb.memory[PF_PENDING] = 1
        pb.memory[PW_FLAGS] = 0x42
        for i, value in enumerate(PASSWORD_TILES):
            pb.memory[SHOWN + i] = value
            pb.memory[BUFFER + i] = 0
        pb.memory[SLOT] = 0
        pb.memory[MENU] = 0
        pb.memory[MARK_X] = 0x20
        pb.memory[MARK_X2] = 0x28
        pb.memory[HAND_X] = 0x34
        pb.memory[HAND_X2] = 0x3C
        pb.memory[HAND_Y] = 0x40
        pb.memory[HAND_Y2] = 0x40
        pb.memory[HAND_COL] = 0
        step_regs = dict(A=0x5A, F=0xB0, B=0x11, C=0x22, D=0x33, E=0x44, HL=0x5566)
        step = call_upper(pb, PF_STEP, step_regs, 0x00F1)
        buffer = bytes(pb.memory[BUFFER:BUFFER + 4])
        print('pf_step buffer=' + buffer.hex() +
              f' slot={pb.memory[SLOT]} pending={pb.memory[PF_PENDING]} menu={pb.memory[MENU]}' +
              f' hand=({pb.memory[HAND_X]},{pb.memory[HAND_Y]})')
        assert buffer == PASSWORD_TILES
        assert pb.memory[SLOT] == 3 and pb.memory[PF_PENDING] == 0 and pb.memory[MENU] == 24
        assert (pb.memory[HAND_Y], pb.memory[HAND_X], pb.memory[HAND_X2]) == (124, 68, 76)
        assert pb.memory[HAND_COL] == 0x34
        assert (pb.memory[MARK_X], pb.memory[MARK_X2]) == (0x50, 0x58)
        assert step['A'] == 0x42
        for k in ('B','C','D','E','HL'):
            assert step[k] == step_regs[k], f'pf_step changed {k}'
        pb.stop(save=False)

if __name__ == '__main__':
    main()
