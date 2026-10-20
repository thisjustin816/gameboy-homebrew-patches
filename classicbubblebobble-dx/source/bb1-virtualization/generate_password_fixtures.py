#!/usr/bin/env python3
"""Extract zero-flag round passwords using the patched native BB1 encoder."""
import argparse
import hashlib
import json
from pathlib import Path
from shutil import copyfile
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'bubblebobble'))
from verify import Call, letters


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    digest = hashlib.md5(args.source.read_bytes()).hexdigest()
    if digest != 'b093fd9aa903453c1b30703738159a49':
        parser.error('source must be the exact patched BB1 input')
    passwords = {}
    with tempfile.TemporaryDirectory() as directory:
        rom = Path(directory) / 'native.gb'
        copyfile(args.source, rom)
        caller = Call(str(rom))
        try:
            for index in range(100):
                state = caller.run(0x7650, {'D': index, 'E': 0}, bank=3)
                assert state['sp_balanced'], 'native encoder unbalanced the stack'
                passwords[str(index)] = letters([state['mem'][address]
                                                for address in range(0xc918, 0xc91c)])
        finally:
            caller.pb.stop(save=False)
    args.output.write_text(json.dumps({'source_md5': digest,
                                      'encoder': 'bank 3, $7650; D=round index, E=0',
                                      'passwords': passwords}, indent=2) + '\n')


if __name__ == '__main__':
    main()
