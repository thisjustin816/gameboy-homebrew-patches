#!/usr/bin/env python3
from pathlib import Path
from pyboy import PyBoy
from tempfile import TemporaryDirectory
from shutil import copy2
import argparse, hashlib

EXPECTED_SCREEN_MD5 = 'e34db805a4d155f0da472d410fe3e77a'

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom', type=Path)
    args = ap.parse_args()
    with TemporaryDirectory() as td:
        p = Path(td) / args.rom.name
        copy2(args.rom, p)
        pb = PyBoy(str(p), window='null', sound_emulated=False)
        for _ in range(11):
            pb.tick(55, False)
            pb.button_press('start')
            pb.tick(5, False)
            pb.button_release('start')
        pb.tick(55, False)
        img = pb.screen.image.convert('RGB')
        digest = hashlib.md5(img.tobytes()).hexdigest()
        print(f'frame={pb.frame_count} pc=${int(pb.register_file.PC):04X} sp=${int(pb.register_file.SP):04X}')
        print(f'screen_rgb_md5={digest}')
        print(f'expected_screen_rgb_md5={EXPECTED_SCREEN_MD5}')
        pb.stop(save=False)
        if pb.frame_count != 715 or digest != EXPECTED_SCREEN_MD5:
            raise SystemExit(1)

if __name__ == '__main__':
    main()
