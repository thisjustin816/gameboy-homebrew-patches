#!/usr/bin/env python3
"""Compare controlled combo pops or later-round play with native CGB BB1.

Combos clone a naturally reached trapped-enemy record, then let gameplay pop it.
Later rounds use forced clears or native passwords, then ordinary scripted input.
Ending fixtures force the final bonus-room goal and prior bonus-win flags.
Temporary ending ROMs also replace divider reads with matching constants.
These fixtures do not establish unassisted victories or exact audio timing.
"""
import argparse
import hashlib
import json
from pathlib import Path
from shutil import copyfile
import subprocess
import sys
import tempfile

from gameplay import buttons, chunks, record_digest
from kll1 import Replay
from test_real_title_vram_parity import make_ref


def snapshot(replay, tick):
    state = chunks(replay.emulator.get_state())
    ram, vram, hram = state['wram'], state['vram'], state['hram']
    return {
        'tick': tick, 'counter': hram[0x193], 'round': ram[0x200], 'lcd': bool(hram[0x140] & 128),
        'actors': record_digest(ram, ((0x400, 1, 0x24), (0x600, 7, 0x24))),
        'objects': record_digest(ram, ((0x500, 15, 0x10),)),
        'bonus': record_digest(ram, ((0x800, 8, 0x10),)),
        'bonus_flags': ram[0x880:0x8a0].hex(),
        'score': ram[0x490:0x493].hex(), 'pending': ram[0x430:0x432].hex(),
        'left': hram[0x1c3], 'chain': hram[0x1a7], 'combo_count': ram[0x234],
        'timer': hram[0x1be:0x1c0].hex(),
        'sprite_streams': hram[0x19f:0x1a3].hex(),
        'collision': hashlib.sha256(ram[0x1800:0x1c00]).hexdigest(),
        'tiles': hashlib.sha256(vram[:0x1800]).hexdigest(),
        'maps': hashlib.sha256(vram[0x1800:0x2000]).hexdigest(),
        # Gambatte's hram chunk covers FE00-FFFF, including OAM.
        'oam': hashlib.sha256(hram[:0xa0]).hexdigest(),
    }


class Clock:
    def __init__(self, replay):
        self.replay = replay
        self.tick = replay.frame
        self.previous = replay.read(0xff93)

    def step(self, held=()):
        self.replay.step(*held)
        current = self.replay.read(0xff93)
        delta = (current - self.previous) & 255
        if delta > 2:
            state = chunks(self.replay.emulator.get_state())
            raise RuntimeError(f'VBlank counter {self.previous}->{current} at tick {self.tick}, '
                               f'frame {self.replay.frame}, PC={state["pc"].hex()}, '
                               f'round={self.replay.read(0xc200)}')
        self.tick += delta
        self.previous = current
        if self.replay.frame > 60000:
            raise RuntimeError('replay exceeded frame budget')


def worker(args):
    replay = Replay(args.rom)
    if args.scene in ('password', 'ending'):
        fixture = json.loads(Path(__file__).with_name('password-fixtures.json').read_text())
        assert fixture['source_md5'] == 'b093fd9aa903453c1b30703738159a49'
        index = 99 if args.scene == 'ending' else args.case
        replay.start_password(fixture['passwords'][str(index)])
    else:
        replay.start_round_three()
    clock = Clock(replay)
    if args.scene == 'combo':
        while clock.tick < 4842:
            clock.step(buttons(clock.tick, True))
        state = chunks(replay.emulator.get_state())
        template = state['wram'][0x66c:0x690]
        assert template[0] == 0x11 and template[2] == 4, 'trapped-enemy fixture changed'
        for index in range(7):
            record = template if index < args.case else bytes(0x24)
            for offset, value in enumerate(record):
                replay.data.memory.assign(0xc600 + index * 0x24 + offset, '|u1', value)
        replay.data.memory.assign(0xffc3, '|u1', args.case)
        start, duration = clock.tick, 180
    elif args.scene in ('password', 'ending'):
        settle = clock.tick + 300
        while clock.tick < settle:
            clock.step()
        assert replay.read(0xc200) == index, 'password entered wrong round'
        if args.scene == 'ending':
            warmup = clock.tick
            while clock.tick < warmup + 1200:
                clock.step(buttons(clock.tick - warmup + 2400, True))
            assert replay.read(0xc0aa) == 0xbe and replay.read(0xc0ab) == 0x3b
            replay.data.memory.assign(0xc4b5, '|u1', args.case)
            replay.data.memory.assign(0xffc3, '|u1', 0)
        start = clock.tick
        duration = 6000 if args.scene == 'ending' else 1200
    else:
        while clock.tick < 2300:
            clock.step()
        for expected in range(3, args.case + 1):
            replay.data.memory.assign(0xffc3, '|u1', 0)
            deadline = clock.tick + 900
            while replay.read(0xc200) != expected and clock.tick < deadline:
                clock.step()
            assert replay.read(0xc200) == expected, f'failed to enter round {expected + 1}'
            settle = clock.tick + 300
            while clock.tick < settle:
                clock.step()
        start, duration = clock.tick, 1200
    records = {}
    while clock.tick <= start + duration:
        relative = clock.tick - start
        if args.scene == 'ending':
            callback = replay.read(0xc0aa) | (replay.read(0xc0ab) << 8)
            if callback == 0x3bbe and relative < 600:
                replay.data.memory.assign(0xc403, '|u1', (replay.read(0xc603) - 16) & 255)
                replay.data.memory.assign(0xc404, '|u1', (replay.read(0xc604) - 16) & 255)
        records[relative] = snapshot(replay, relative)
        if args.scene == 'ending':
            records[relative].update(callback=callback, flags=replay.read(0xc4b5),
                                     ending_state=bytes(replay.read(a) for a in (0xc922, 0xc945, 0xc94e)).hex())
        if args.frames_dir and relative in (0, 2, 20, 60, 180, 600, 1200, 2400, 3600, 4800, 6000):
            from PIL import Image
            args.frames_dir.mkdir(parents=True, exist_ok=True)
            Image.fromarray(replay.emulator.get_screen()).save(
                args.frames_dir / f'{args.worker}-{args.scene}{args.case}-tick{relative}.png')
        policy_tick = clock.tick if args.scene == 'combo' else relative + 2400
        if args.scene == 'ending':
            held = ['A'] if relative % 120 in (16, 17) else []
        else:
            held = buttons(policy_tick, True)
        clock.step(held)
    print(json.dumps(list(records.values())))


def compare(native, hosted, ignore_lcd_off_tiles=False, strict_lcd_off_vram=False):
    assert native and hosted, 'no samples'
    labels = [record['tick'] for record in native]
    assert labels == [record['tick'] for record in hosted], 'different observed tick labels'
    assert labels == sorted(set(labels)), 'unordered or duplicate ticks'
    failures, hidden_maps, hidden_tiles = [], [], []
    for left, right in zip(native, hosted):
        changed = [key for key in left if left[key] != right[key]]
        if not left['lcd'] and not right['lcd'] and 'maps' in changed:
            hidden_maps.append(left['tick'])
            if not strict_lcd_off_vram:
                changed.remove('maps')
        if not left['lcd'] and not right['lcd'] and 'tiles' in changed:
            hidden_tiles.append(left['tick'])
            if ignore_lcd_off_tiles and not strict_lcd_off_vram:
                changed.remove('tiles')
        if changed:
            failures.append({'tick': left['tick'], 'fields': changed})
    return failures, hidden_maps, hidden_tiles


def seed_divider_reads(path, bank):
    # Divider timing changes with relocation overhead. These temporary ROMs
    # give both engines matching decorative RNG inputs without changing the build.
    data = bytearray(path.read_bytes())
    sites = (0x546f, 0x5955, 0x6b32, 0x6c62, 0x6cbe, 0x6d30, 0x6d76, 0x6db4)
    for index, pc in enumerate(sites):
        offset = bank * 0x4000 + pc - 0x4000
        assert data[offset:offset + 2] == bytes.fromhex('f004'), f'divider site changed at ${pc:04X}'
        data[offset:offset + 2] = bytes((0x3e, (0x5a + 17 * index) & 255))
    total = (sum(data[:0x14e]) + sum(data[0x150:])) & 0xffff
    data[0x14e:0x150] = total.to_bytes(2, 'big')
    path.write_bytes(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('rom', type=Path)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--scene', choices=('combo', 'later', 'password', 'ending'), required=True)
    parser.add_argument('--cases', type=int, nargs='+')
    parser.add_argument('--all-rounds', action='store_true',
                        help='check all 100 password entries; only valid for the password scene')
    parser.add_argument('--frames-dir', type=Path)
    parser.add_argument('--include-lcd-off-vram', action='store_true',
                        help='also require raw VRAM parity during LCD-off partial clears')
    parser.add_argument('--worker', choices=('native', 'host'), help=argparse.SUPPRESS)
    parser.add_argument('--case', type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    allowed = {'combo': range(1, 8), 'later': range(3, 9), 'password': range(100), 'ending': (0, 7)}[args.scene]
    if args.worker:
        assert args.case in allowed
        return worker(args)
    defaults = [9, 14, 19, 24, 49, 74, 98, 99] if args.scene == 'password' else list(allowed)
    if args.all_rounds and (args.scene != 'password' or args.cases is not None):
        parser.error('--all-rounds requires --scene password and cannot combine with --cases')
    if args.all_rounds:
        cases = list(allowed)
    else:
        cases = defaults if args.cases is None else args.cases
    if not cases or any(case not in allowed for case in cases):
        parser.error('case outside supported scene range')
    if not args.source or hashlib.md5(args.source.read_bytes()).hexdigest() != 'b093fd9aa903453c1b30703738159a49':
        parser.error('--source must identify the exact patched BB1 input')
    reports = []
    with tempfile.TemporaryDirectory() as directory:
        native, host = Path(directory) / 'native.gbc', Path(directory) / 'host.gbc'
        make_ref(native, args.source)
        copyfile(args.rom, host)
        if args.scene == 'ending':
            for path, bank in ((native, 2), (host, 0x42)):
                seed_divider_reads(path, bank)
        for case in cases:
            runs = []
            for name, rom in (('native', native), ('host', host)):
                command = [sys.executable, str(Path(__file__).resolve()), str(rom),
                           '--worker', name, '--scene', args.scene, '--case', str(case)]
                if args.frames_dir:
                    command.extend(('--frames-dir', str(args.frames_dir.resolve())))
                result = subprocess.run(command, capture_output=True, text=True, timeout=90)
                if result.returncode:
                    raise RuntimeError(f'{name} case {case} failed:\n{result.stderr}')
                runs.append(json.loads(result.stdout))
            failures, hidden_maps, hidden_tiles = compare(
                *runs, ignore_lcd_off_tiles=args.scene == 'ending',
                strict_lcd_off_vram=args.include_lcd_off_vram)
            report = {'case': case, 'samples': len(runs[0]), 'first_mismatches': failures[:8],
                      'mismatch_samples': len(failures), 'lcd_off_map_mismatches': hidden_maps,
                      'lcd_off_tile_mismatches': hidden_tiles,
                      'include_lcd_off_vram': args.include_lcd_off_vram,
                      'missed_ticks': sorted(set(range(runs[0][-1]['tick'] + 1)) -
                                             {record['tick'] for record in runs[0]})}
            if args.scene == 'combo':
                expected = f'{100 * 2 ** (case - 1):06d}'
                for run in runs:
                    award = next(record['score'] for record in run if record['score'] != '000000')
                    assert award == expected, (case, award, expected)
                    assert any(record['left'] == 0 for record in run), 'enemies did not pop'
                    if case > 1:
                        assert any(int(record['bonus_flags'][:2], 16) & 0x40 for record in run)
                report['first_score_bcd'] = expected
            elif args.scene == 'ending':
                for run in runs:
                    assert run[0]['round'] == 99 and run[0]['flags'] == case
                    assert any(record['callback'] == 0x21a1 for record in run), 'bonus goal did not complete'
                    if case == 0:
                        assert run[-1]['callback'] == 0x3bbe, 'missing-win ending did not return to retry'
                    else:
                        assert any(int(record['ending_state'][2:4], 16) & 0x80 for record in run), 'ending did not finish'
                report['prior_bonus_wins'] = case
                report['div_seed'] = 0x5a
                report['round_indices'] = sorted({record['round'] for record in runs[0]})
                report['ending_state_count'] = len({record['ending_state'] for record in runs[0]})
                report['final_ending_state'] = runs[0][-1]['ending_state']
            else:
                assert all(run[0]['round'] == case for run in runs)
                report['round'] = case + 1
                report['round_indices'] = sorted({record['round'] for record in runs[0]})
            reports.append(report)
            print(json.dumps(report), flush=True)
    assert not any(report['mismatch_samples'] for report in reports), 'native/host scene mismatch'


if __name__ == '__main__':
    main()
