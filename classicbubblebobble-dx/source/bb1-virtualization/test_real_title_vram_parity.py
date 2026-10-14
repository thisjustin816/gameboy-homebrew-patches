#!/usr/bin/env python3
from pathlib import Path
from pyboy import PyBoy
import argparse, hashlib, tempfile, shutil


def make_ref(path, source):
    b=bytearray(source.read_bytes()); b[0x143]=0x80
    x=0
    for i in range(0x134,0x14D): x=(x-b[i]-1)&0xff
    b[0x14D]=x; s=(sum(b[:0x14E])+sum(b[0x150:]))&0xffff
    b[0x14E]=s>>8; b[0x14F]=s&0xff; path.write_bytes(b)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('rom',type=Path); ap.add_argument('--source', type=Path, required=True); ap.add_argument('--end',type=int,default=600); a=ap.parse_args()
    with tempfile.TemporaryDirectory() as td:
        td=Path(td); host=td/'host.gbc'; ref=td/'ref.gb'; shutil.copy2(a.rom,host); make_ref(ref, a.source)
        h=PyBoy(str(host),window='null',sound_emulated=False); r=PyBoy(str(ref),window='null',sound_emulated=False)
        first=None; maxdiff=0; mismatches=0
        for f in range(1,a.end+1):
            h.tick(1,True); r.tick(1,True)
            if f < 400: continue
            hv=bytes(h.memory[0,0x8000:0x9FFF])+bytes([h.memory[0,0x9FFF]]); rv=bytes(r.memory[0,0x8000:0x9FFF])+bytes([r.memory[0,0x9FFF]])
            d=sum(x!=y for x,y in zip(hv,rv))
            if d:
                mismatches+=1; maxdiff=max(maxdiff,d)
                if first is None:
                    idx=next(i for i,(x,y) in enumerate(zip(hv,rv)) if x!=y)
                    first=(f,0x8000+idx,d,hv[idx],rv[idx])
        # settled-title render sample; useful evidence in addition to VRAM
        hi=bytes(h.screen.image.convert('RGB').tobytes()); ri=bytes(r.screen.image.convert('RGB').tobytes())
        pixbytes=sum(x!=y for x,y in zip(hi,ri))
        print(f'rom={a.rom.name}')
        print(f'frames=400-{a.end} vram_mismatch_frames={mismatches} max_vram_diff={maxdiff}')
        print('first='+('none' if first is None else f'frame {first[0]} addr ${first[1]:04X} count {first[2]} host={first[3]:02X} ref={first[4]:02X}'))
        print(f'frame{a.end}_screen_rgb_md5_host={hashlib.md5(hi).hexdigest()} ref={hashlib.md5(ri).hexdigest()} differing_rgb_bytes={pixbytes}')
        print(f'frame{a.end}_scheduler_de00_1f_equal={bytes(h.memory[0xDE00:0xDE20])==bytes(r.memory[0xDE00:0xDE20])}')
        h.stop(save=False); r.stop(save=False)
        raise SystemExit(0 if mismatches==0 else 1)
if __name__=='__main__': main()
