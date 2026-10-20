#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
from collections import deque
import hashlib, subprocess, re, sys

BANK=0x4000
BASE=0x40
V0_PHYS=BASE
HOST_ORG=0x1665
HOST_LIMIT=0x3E00
SHADOW_6FD1=0x7E00
RGBASM=Path('/mnt/data/rgbds/rgbasm')
RGBLINK=Path('/mnt/data/rgbds/rgblink')

CLASSIC=Path('/mnt/data/Classic Bubble Bobble (USA) [SMS physics & save patch by thisJUSTin816 v1.0].gbc')
BB1=Path('/mnt/data/Bubble Bobble (USA, Europe) [Password save patch by thisJUSTin816 v1.0].gb')
BB2=Path('/mnt/data/Bubble Bobble Part 2 (USA, Europe) [Tearing fix & save patch by thisJUSTin816 v1.1].gb')
OUT=Path('/mnt/data/Classic Bubble Bobble DX [BB1 virtualization diagnostic edgeprobe18b].gbc')
HERE=Path(__file__).resolve().parent
BUILD=HERE/'build'

LEN=[1]*256
for op in [0x01,0x08,0x11,0x21,0x31,0xC2,0xC3,0xC4,0xCA,0xCC,0xCD,0xD2,0xD4,0xDA,0xDC,0xEA,0xFA]: LEN[op]=3
for op in [0x06,0x0E,0x10,0x16,0x18,0x1E,0x20,0x26,0x28,0x2E,0x30,0x36,0x38,0x3E,0xC6,0xCB,0xCE,0xD6,0xDE,0xE0,0xE6,0xE8,0xEE,0xF0,0xF6,0xF8,0xFE]: LEN[op]=2
CALLS={0xCD,0xC4,0xCC,0xD4,0xDC}; JPS={0xC3,0xC2,0xCA,0xD2,0xDA}; JRS={0x18,0x20,0x28,0x30,0x38}
RETS={0xC0,0xC8,0xC9,0xD0,0xD8,0xD9}; UNCOND_RET={0xC9,0xD9}; UNDEF={0xD3,0xDB,0xDD,0xE3,0xE4,0xEB,0xEC,0xED,0xF4,0xFC,0xFD}

EXPECTED={
 'classic':'2c4c0b9cc0c106051fb195e4ed3365d9',
 'bb1':'b093fd9aa903453c1b30703738159a49',
 'bb2':'f2ef3b62b6859cc89bbb8494bb4057b2',
}

# Low (<$4000) JP-HL targets observed on the exact patched BB2 ROM while
# exercising title idle, new-game and password flows. collect_indirect_targets.py
# regenerates the evidence. These are code entry points, so seed recursive CFG
# discovery before rewriting absolute references inside them.
OBSERVED_INDIRECT_LOW_TARGETS={
 # PyBoy title/menu/password observations on the exact patched BB1 ROM.
 # $0260 is reached through RST $00 during boot. $170D/$1743/$174C/$17CF are VBlank
 # dispatch leaves reached through the HRAM pointer at $FFAB.
 0x0260,0x170D,0x1743,0x174C,0x17CF,
 # Fixed-bank entries from the object-state dispatcher table at $2C7F.
 0x2DFA,0x2D86,0x2C45,0x2BD4,0x2BA0,0x2E57,0x2E72,
 0x2BBB,0x2D78,0x2CF6,0x2D0D,0x2D20,0x2D61,0x2C9D,
}

# Cooperative task entry PCs initialized by fixed-bank scheduler setup. These
# are resumed from saved stacks rather than reached by a normal CALL/JP, so
# seed them explicitly to discover their fixed->upper edges.
TASK_FIXED_ENTRY_SEEDS={0x054A,0x0D27,0x1C92,0x298A,0x21A1}



# Banked routines reached through BB2's two-level $2E6E dispatcher are not
# visible to a direct-call-only CFG seed pass. These entry points were observed
# from the exact patched ROM's bank-7 title/menu dispatch tables ($7308 root)
# while exercising title idle and the Start/Password transition. Seeding them
# lets banked_edges() discover and rewrite their calls back into fixed bank 0
# (for example $7367 -> $2C53), instead of accidentally calling Classic's
# physical MBC5 bank 0.
OBSERVED_BANKED_ENTRY_POINTS={
 # Direct fixed->upper calls whose preceding mapper selection is statically
 # immediate on the exact patched BB1 ROM. These seed recursive upper-bank CFG.
 (7,0x43C2),(1,0x63B7),(6,0x7B40),(1,0x6235),(1,0x6210),(1,0x6377),
 (2,0x4242),(2,0x41E4),(7,0x441B),(7,0x4000),(1,0x4093),(1,0x4079),
 (1,0x4498),(6,0x5043),(6,0x50C5),(6,0x511C),(6,0x4540),
 (2,0x5201),(2,0x5229),(2,0x6444),(2,0x6425),(1,0x609A),(6,0x4554),
 (6,0x4D80),(6,0x4858),(1,0x5961),(6,0x4BEE),(3,0x6FD1),(3,0x7129),
 (3,0x7650),(2,0x6788),(2,0x6757),(2,0x75D5),(2,0x753D),(6,0x5249),
 (6,0x52E6),(6,0x532B),(6,0x581F),(6,0x5835),(6,0x5387),(6,0x537C),
 (1,0x63F9),(1,0x640A),(1,0x6422),(6,0x56D4),(6,0x56FA),
 # Password-save patch code lives in bank 3 and calls fixed-bank SRAM helpers.
 (3,0x7800),
 # Cooperative task initialized at bank-1 $4669.
 (1,0x4669),
 # Bank-1 special-object and projectile dispatchers used in later rounds.
 (1,0x5CCF),(1,0x55A0),
 # Bank-1 enemy-state handlers from the fixed-ROM table at $29E3.
 (1,0x5278),(1,0x54D7),(1,0x5473),(1,0x48DD),
 (1,0x5356),(1,0x4FD0),(1,0x4D2E),(1,0x4983),
}


def md5(b): return hashlib.md5(b).hexdigest()
def hsum(r):
 x=0
 for i in range(0x134,0x14D): x=(x-r[i]-1)&255
 return x
def gsum(r): return (sum(r[:0x14E])+sum(r[0x150:]))&0xffff

def decode0(b,pc):
 if pc>=0x4000:return None
 op=b[pc]; l=LEN[op]
 if pc+l>0x4000:return None
 arg=None
 if l==3:arg=b[pc+1]|b[pc+2]<<8
 elif op in JRS:
  d=b[pc+1]; d=d-256 if d>=128 else d; arg=(pc+2+d)&0xffff
 return op,l,arg

def discover_bank0(b, extra_seeds=()):
 mapper={i for i in range(0x3ffe) if b[i:i+3]==b'\xea\x00\x21'}
 seeds={0x100,0x150,0x40,0x48,0x50,0x58,0x60,0x61,*mapper,
        *OBSERVED_INDIRECT_LOW_TARGETS,*TASK_FIXED_ENTRY_SEEDS,*extra_seeds}
 q=deque(seeds); seen=set(); branches=[]; upper=[]; jphl=[]; rsts=[]
 while q:
  pc=q.popleft()
  if not 0<=pc<0x4000:continue
  while 0<=pc<0x4000 and pc not in seen:
   d=decode0(b,pc)
   if not d:break
   op,l,arg=d
   if op in UNDEF:break
   seen.add(pc); nxt=pc+l
   if op in CALLS:
    branches.append((pc,op,arg))
    if arg<0x4000:q.append(arg)
    elif arg<0x8000:upper.append((pc,op,arg))
   elif op in JPS:
    branches.append((pc,op,arg))
    if arg<0x4000:q.append(arg)
    elif arg<0x8000:upper.append((pc,op,arg))
    if op==0xC3:break
   elif op in JRS:
    if arg<0x4000:q.append(arg)
    if op==0x18:break
   elif op==0xE9:
    jphl.append(pc); break
   elif op in RETS:
    if op in UNCOND_RET:break
   elif op==0x76:
    q.append(nxt); break
   elif op==0x10:
    break
   elif op in (0xC7,0xCF,0xD7,0xDF,0xE7,0xEF,0xF7,0xFF):
    rsts.append((pc,op))
   pc=nxt
 return mapper,seen,branches,upper,jphl,rsts

def prev_bank_value(b,i):
 if i>=2 and b[i-2]==0x3E:return b[i-1]
 if i>=5 and b[i-5]==0x3E and b[i-3:i]==b'\xea\x73\xce':return b[i-4]
 return None

def decode_bank(b,bank,addr):
 off=bank*BANK+(addr-0x4000); op=b[off]; l=LEN[op]
 arg=None
 if l==3:arg=b[off+1]|b[off+2]<<8
 elif op in JRS:
  d=b[off+1];d=d-256 if d>=128 else d;arg=(addr+2+d)&0xffff
 return op,l,arg

def banked_edges(b):
 seeds=set(OBSERVED_BANKED_ENTRY_POINTS)
 # Add upper entry points that occur soon after an immediate mapper selection.
 sites=[i for i in range(0x3ffe) if b[i:i+3]==b'\xea\x00\x21']
 for idx,i in enumerate(sites):
  bank=prev_bank_value(b,i)
  if bank is None:continue
  bank &= 0x07
  if bank==0:bank=1
  end=sites[idx+1] if idx+1<len(sites) else 0x4000;pc=i+3
  while pc<end and pc<i+120:
   d=decode0(b,pc)
   if not d:break
   op,l,arg=d
   if op in CALLS|JPS and arg is not None and 0x4000<=arg<0x8000:seeds.add((bank,arg))
   if op in UNDEF:break
   pc+=l
 edges=[]; rsts=[]; seen_by={}
 for bank in sorted({x[0] for x in seeds}):
  if bank*BANK>=len(b):continue
  q=deque(a for k,a in seeds if k==bank); seen=set()
  while q:
   pc=q.popleft()
   if not 0x4000<=pc<0x8000:continue
   while 0x4000<=pc<0x8000 and pc not in seen:
    op,l,arg=decode_bank(b,bank,pc); seen.add(pc); nxt=pc+l
    if op in UNDEF:break
    if op in CALLS:
     if arg<0x4000:edges.append((bank,pc,op,arg))
     elif arg<0x8000:q.append(arg)
    elif op in JPS:
     if arg<0x4000:edges.append((bank,pc,op,arg))
     elif arg<0x8000:q.append(arg)
     if op==0xC3:break
    elif op in JRS:
     if 0x4000<=arg<0x8000:q.append(arg)
     if op==0x18:break
    elif op in (0xC7,0xCF,0xD7,0xDF,0xE7,0xEF,0xF7,0xFF):
     rsts.append((bank,pc,op))
    elif op in RETS and op in UNCOND_RET:break
    elif op in (0xE9,0x76,0x10):break
    pc=nxt
  seen_by[bank]=seen
 return seeds,seen_by,edges,rsts

def make_asm(upper_targets,low_targets):
 lines=[r'''
DEF MBC5_ROM EQU $2100
DEF MBC5_HI  EQU $3000
DEF MBC5_RAM EQU $4000
DEF H_PHYS   EQU $FFD3
DEF H_LOG    EQU $FFD6
DEF H_IRQ    EQU $FFF5
DEF H_TMP    EQU $FFF6
DEF V0       EQU $40

SECTION "rst00", ROM0[$0000]
    jp host_rst00
SECTION "rst08", ROM0[$0008]
    jp host_indirect_jp
SECTION "rst10", ROM0[$0010]
    jp host_context_ret
SECTION "rst18", ROM0[$0018]
    jp host_irq_return
SECTION "rst20", ROM0[$0020]
    jp host_palette_bgp
SECTION "rst28", ROM0[$0028]
    jp host_palette_obp0
SECTION "rst30", ROM0[$0030]
    jp host_palette_obp1
SECTION "rst38", ROM0[$0038]
    jp host_rst38
SECTION "vblank", ROM0[$0040]
    jp host_vblank
SECTION "lcdirq", ROM0[$0048]
    reti
SECTION "timerirq", ROM0[$0050]
    reti
SECTION "serialirq", ROM0[$0058]
    reti
SECTION "joyirq", ROM0[$0060]
    reti
SECTION "entry", ROM0[$0100]
    nop
    jp host_launcher

SECTION "host", ROM0[$1665]
host_launcher::
    xor a
    ld [MBC5_HI],a
    ; Collection SRAM partition: Classic=0, BB1=1, BB2=2, bank 3 spare.
    ; BB2's own save patch only toggles SRAM enable at $0000 and never writes
    ; the MBC1 RAM-bank range, so selecting MBC5 RAM bank 2 here isolates all
    ; of its $A000 accesses without changing the save code.
    ld a,$01
    ld [MBC5_RAM],a
    ; Recreate the launcher's previous A/F state before entering BB2.
    xor a
    inc a
    ldh [H_LOG],a
    ld a,V0
    call host_map_physical_a
    jp $4150

host_rst00::
    ; BB1's observed RST $00 targets are fixed-bank logical addresses. Keep the
    ; original A/F result (A = target high byte), relocate only H, and jump.
    ; This hot VBlank path must stay close to the original cycle cost.
    ldh a,[$FFA9]
    ld l,a
    ldh a,[$FFAA]
    ld h,a
    set 6,h
    jp hl

host_rst38::
    ld a,[hl+]
    ld h,[hl]
    ld l,a
    jp host_indirect_jp

host_after_hram_clear::
    ; BB1 clears $FF8A-$FFFC during startup, which includes the host mapper
    ; state bytes. Re-establish host-only state immediately after that clear,
    ; preserving the A/F state that the original CALL $01F2 received.
    push af
    ld a,$01
    ldh [H_LOG],a
    ld a,V0
    call host_map_physical_a
    pop af
    jp $41F2

host_context_ret::
    ; Replaces the scheduler RET at logical $0446. RST $10 contributed a
    ; temporary return address on the selected task stack; discard it. Relocate
    ; saved logical PCs while preserving the exact host_low_0465 continuation
    ; and banked-task entry in ROM0, where they restore the upper-bank mapping.
    inc sp
    inc sp
    push af
    push hl
    ld hl,sp+5
    ld a,[hl]
    bit 6,a
    jr nz,.already_upper
    cp HIGH(host_low_0465_resume)
    jr nz,.check_banked_task
    dec hl
    ld a,[hl]
    cp LOW(host_low_0465_resume)
    jr z,.already_upper
    inc hl
    ld a,[hl]
.check_banked_task:
    cp HIGH(host_task_4669)
    jr nz,.relocate_low
    dec hl
    ld a,[hl]
    cp LOW(host_task_4669)
    jr z,.already_upper
    inc hl
    ld a,[hl]
.relocate_low:
    or $40
    ld [hl],a
.already_upper:
    pop hl
    pop af
    ret

host_irq_return::
    ; Logical $0CB9 uses RST $18 instead of RETI. Remove that RST frame, map
    ; BB1 V0 for the scheduler-selected fixed task, then perform the sole RETI.
    inc sp
    inc sp
    push af
    ld a,V0
    call host_map_physical_a
    pop af
    reti

; A is the value written to the emulated MBC1 ROM-bank register. Keep this
; separate from BB2's own $CE73 bookkeeping: the game makes temporary mapper
; switches (notably in VBlank) without changing $CE73, then uses $CE73 to restore.
; LDH and RET preserve flags.
host_set_bank::
    ldh [H_LOG],a
    ret

; Map physical MBC5 bank A. H_PHYS is updated first so an IRQ between these
; two writes still knows what mapping the interrupted fixed-bank code intends.
host_map_physical_a::
    ld [H_PHYS],a
    ld [MBC5_ROM],a
    ret

; Convert logical MBC1 bank A to the BB1 physical MBC5 bank and map it.
; Caller saves AF when flags/A matter.
host_map_logical_a::
    ; BB2 is a 256 KiB / 16-bank MBC1 image: only the low four ROM-bank
    ; bits are physically decoded. Preserve MBC1's bank-0 -> bank-1 alias.
    and $07
    jr nz,.nonzero
    inc a
.nonzero:
    add V0
    jp host_map_physical_a

; RST $00 replacement for JP HL in relocated bank 0. Logical fixed-bank
; targets (<$4000) can be jumped to directly at +$4000 while V0 remains mapped.
; Logical upper-bank targets need a trampoline: map H_LOG, CALL the target, then
; restore V0 before returning through the JP-HL caller's existing stack frame.
; Preserve the flags that the original JP HL would have left untouched.
host_indirect_jp::
    push af
    bit 6,h
    jr nz,.upper
    push bc
    ld b,h
    ld c,l
    ld hl,sp+4
    ld [hl],c
    inc hl
    ld a,b
    or $40
    ld [hl],a
    ld h,b
    ld l,c
    pop bc
    pop af
    ret
.upper:
    push bc
    ld b,h
    ld c,l
    ld hl,sp+4
    ld [hl],LOW(host_indirect_upper)
    inc hl
    ld [hl],HIGH(host_indirect_upper)
    ld h,b
    ld l,c
    pop bc
    pop af
    ret

host_indirect_upper::
    push af
    ldh a,[H_LOG]
    call host_map_logical_a
    pop af
    call host_jp_hl
    push af
    ld a,V0
    call host_map_physical_a
    pop af
    ret

; BB2's save patch uses CALL $0018 with target in HL to bank 8.
host_far8::
    ldh a,[H_LOG]
    push af
    ld a,8
    ldh [H_LOG],a
    push af
    call host_map_logical_a
    pop af
    call host_jp_hl
    pop af
    ldh [H_LOG],a
    ; far8 is only called from relocated logical fixed-bank code. Restore the
    ; caller's logical mapper state, but physically remap V0 so the return
    ; address in $4000-$7FFF still contains that relocated fixed code.
    push af
    ld a,V0
    call host_map_physical_a
    pop af
    ret
host_jp_hl:
    jp hl

; Map the currently emulated MBC1 upper ROM bank while host code is executing
; from real MBC5 bank 0. Unlike relocated BB2 fixed code, host code can safely
; see the $4000-$7FFF data window while doing so.
host_map_current_logical::
    ldh a,[H_LOG]
    jp host_map_logical_a

; Read one byte from the currently selected logical upper bank at HL, store it
; to BB2's $CBBC state byte, then restore relocated fixed bank V0. This exactly
; replaces logical fixed code at $08D4-$08D7 (`ld a,[hl] / ld [$CBBC],a`).
; Preserve BC/DE/HL and the incoming flags; return A equal to the byte read.
host_read_cbbc_hl::
    push af
    ldh a,[H_LOG]
    call host_map_logical_a
    ld a,[hl]
    ldh [H_TMP],a
    ld a,V0
    call host_map_physical_a
    pop af
    ldh a,[H_TMP]
    ld [$CBBC],a
    ret

; Logical fixed routine $095F reads a 16-bit pointer from bank-3 table
; $75C2 + BC. Reproduce the original final HL/A/flags while doing the ROM read
; from real bank-0 host code, where the selected MBC5 upper bank is visible.
host_read_stage_ptr::
    ld hl,$75C2
    add hl,bc
    push af
    ldh a,[H_LOG]
    call host_map_logical_a
    ld a,[hl+]
    ld [$CBC2],a
    ld a,[hl]
    ld [$CBC3],a
    ld a,V0
    call host_map_physical_a
    pop af
    ld a,[$CBC3]
    ret

; Logical fixed routine $0DA7 reads one byte from the bank-3 stream pointed
; to by HL, increments HL, compares it with $FF, and stores it in $C10E.
host_read_c10e_hl_inc::
    ldh a,[H_LOG]
    call host_map_logical_a
    ld a,[hl+]
    ldh [H_TMP],a
    ld a,V0
    call host_map_physical_a
    ldh a,[H_TMP]
    cp $FF
    ld [$C10E],a
    ret

; Palette hooks used by RST $20/$28/$30. Each preserves the behavior of the
; replaced two-byte `ldh [$FF47/$FF48/$FF49],a`, then mirrors the DMG 2-bit
; shade mapping into native CGB palette RAM. All caller registers and flags are
; restored exactly; only CGB palette RAM is additional state.
host_palette_bgp::
    ldh [$FF47],a
    push af
    push bc
    push de
    push hl
    ld d,a
    ld a,$80
    ldh [$FF68],a
    ld a,d
    call host_write_bg_dmg_palette
    pop hl
    pop de
    pop bc
    pop af
    ret

host_palette_obp0::
    ldh [$FF48],a
    push af
    push bc
    push de
    push hl
    ld d,a
    ld a,$80
    ldh [$FF6A],a
    ld a,d
    call host_write_obj_dmg_palette
    pop hl
    pop de
    pop bc
    pop af
    ret

host_palette_obp1::
    ldh [$FF49],a
    push af
    push bc
    push de
    push hl
    ld d,a
    ld a,$88
    ldh [$FF6A],a
    ld a,d
    call host_write_obj_dmg_palette
    pop hl
    pop de
    pop bc
    pop af
    ret

; A is one DMG palette byte. Translate each 2-bit shade selector into a
; 15-bit neutral gray. The shade table is deliberately tiny; using DE as a
; temporary index avoids any alignment assumption.
host_write_bg_dmg_palette::
    ld d,a
    ld b,$04
.loop:
    push de
    ld a,d
    and $03
    add a
    ld e,a
    ld d,$00
    ld hl,host_gray_colors
    add hl,de
    ld a,[hl+]
    ldh [$FF69],a
    ld a,[hl]
    ldh [$FF69],a
    pop de
    srl d
    srl d
    dec b
    jr nz,.loop
    ret

host_write_obj_dmg_palette::
    ld d,a
    ld b,$04
.loop:
    push de
    ld a,d
    and $03
    add a
    ld e,a
    ld d,$00
    ld hl,host_gray_colors
    add hl,de
    ld a,[hl+]
    ldh [$FF6B],a
    ld a,[hl]
    ldh [$FF6B],a
    pop de
    srl d
    srl d
    dec b
    jr nz,.loop
    ret

host_gray_colors::
    ; 5-bit RGB levels 31, 19, 11, 0.
    dw $7FFF,$4E73,$2D6B,$0000

; Original BB2 routine $0DE2-$0EDE. This parser executes in MBC1 fixed
; bank while consuming a variable-length stream from bank 3 and briefly reading
; a two-byte pointer from bank 1. Run the whole parser in real MBC5 bank 0 so
; the selected upper bank is actually visible. H_LOG/CE73 retain the game's
; logical mapper state; before returning, physically restore V0 because the
; caller is relocated fixed-bank code.
host_parse_stage_stream::
    ld a,$03
    ld [$CE73],a
    ldh [H_LOG],a
    push af
    call host_map_logical_a
    pop af
    xor a
    ld [$CBC4],a
    ld [$CBC5],a
    ld [$CBC6],a
    ld a,[$CBC2]
    ld e,a
    ld a,[$CBC3]
    ld d,a
.loop:
    ld a,[$CBC4]
    ld c,a
    ld b,$00
    ld hl,$C4E5
    add hl,bc
    push bc
    ld a,[de]
    inc de
    ld b,a
    ld a,[$CBC5]
    cp b
    jr z,.same_value
    ld a,$01
    jr .store_run
.same_value:
    ld a,[$CBC6]
    inc a
.store_run:
    ld [$CBC6],a
    ld a,b
    ld [hl],a
    ld [$CBC5],a
    pop bc
    ld a,[$CBC6]
    ld hl,$C4EF
    add hl,bc
    ld [hl],a
    ld a,[$CBC5]
    add a
    ld c,a
    ld b,$00

    ld a,$01
    ld [$CE73],a
    ldh [H_LOG],a
    push af
    call host_map_logical_a
    pop af
    ld hl,$4051
    add hl,bc
    ld a,[hl+]
    ld [$CBCA],a
    ld a,[hl]
    ld [$CBCB],a

    ld a,$03
    ld [$CE73],a
    ldh [H_LOG],a
    push af
    call host_map_logical_a
    pop af
    ld a,[$CBC4]
    add a
    ld c,a
    ld b,$00
    ld hl,$C3C2
    add hl,bc
    ld a,[$CBCA]
    ld [hl+],a
    ld a,[$CBCB]
    ld [hl],a
    ld a,[$CBC4]
    ld c,a
    ld b,$00
    ld a,[de]
    inc de
    ld hl,$C2E3
    add hl,bc
    ld [hl],a
    ld hl,$C35B
    add hl,bc
    xor a
    ld [hl],a
    ld a,[de]
    inc de
    ld hl,$CCE8
    add hl,bc
    ld [hl],a
    ld hl,$C2BB
    add hl,bc
    ld [hl],$20
    ld hl,$C333
    add hl,bc
    ld [hl],$00
    ld a,[$CBC4]
    inc a
    ld [$CBC4],a
    ld a,[de]
    cp $FF
    jp nz,.loop

    inc de
    ld a,[$CBC4]
    ld [$C49C],a
    ld a,[de]
    ld [$CE11],a
    cp $FF
    jr z,.after_metadata
    ld hl,$CE0B
    ld c,$00
    inc de
.meta_loop:
    ld a,[de]
    ld [hl+],a
    inc de
    ld a,[de]
    ld [hl+],a
    inc de
    inc c
    ld a,[de]
    cp $FF
    jr nz,.meta_loop
    ld a,c
    ld [$CE09],a
    xor a
    ld [$CE0A],a
.after_metadata:
    inc de
    ld a,[de]
    ld [$CE14],a
    cp $FF
    jr z,.final_bank
    inc de
    ld a,[de]
    ld [$CE12],a
    inc de
    ld a,[de]
    ld [$CE13],a
.final_bank:
    ; Original exits with logical MBC1 bank 1 selected, A=1 and flags from the
    ; preceding CP. Keep that logical state but restore physical V0 for the
    ; relocated fixed-bank caller without disturbing AF.
    ld a,$01
    ld [$CE73],a
    ldh [H_LOG],a
    push af
    ld a,V0
    call host_map_physical_a
    pop af
    ld hl,$C103
    ld [hl],$30
    inc hl
    ld [hl],$0A
    ret

; BB1 fixed routine $021E copies BC bytes [HL+] -> [DE+] while the
; currently selected MBC1 upper bank supplies the source. Relocated fixed-bank
; code cannot see that bank, so execute the identical loop from real ROM0.
host_bb1_copy_bc::
    call host_map_current_logical
.loop:
    ld a,[hl+]
    ld [de],a
    inc de
    dec bc
    ld a,b
    or c
    jr nz,.loop
    push af
    ld a,V0
    call host_map_physical_a
    pop af
    ret

; BB1 fixed routine $16D7 parses a transfer command stream through DE. The
; stream itself lives in the selected upper ROM bank (title transition uses
; bank 1 $6498: 08 1F 6F), while relocated fixed code normally keeps V0
; physically mapped. Entry replaces logical $16E3-$16E5 with a JP here.
; Reproduce $16E3-$16F1 from real ROM0 so DE sees H_LOG, then restore V0
; and continue at relocated logical $16F2 (or $1705 for the zero terminator).
host_bb1_transfer_stream_entry::
    ; Transfer streams may live either in the selected upper bank (title path)
    ; or in fixed BB1 ROM below $4000 (round-start path). Host ROM0 occupies
    ; low CPU addresses, so fixed-source streams must be read through the
    ; relocated V0 window at DE+$4000 and then have DE restored to logical form.
    bit 6,d
    jr z,.fixed_source
    call host_map_current_logical
.upper_read:
    ld a,[de]
    or a
    jr z,.upper_done
    inc l
    ld b,a
    ld [hl+],a
    inc l
    inc de
    ld a,[de]
    ld [hl+],a
    inc de
    ld a,[de]
    ld [hl],a
    inc de
    push af
    ld a,V0
    call host_map_physical_a
    pop af
    jp $56F2
.upper_done:
    push af
    ld a,V0
    call host_map_physical_a
    pop af
    jp $5705
.fixed_source:
    set 6,d
    ld a,[de]
    or a
    jr z,.fixed_done
    inc l
    ld b,a
    ld [hl+],a
    inc l
    inc de
    ld a,[de]
    ld [hl+],a
    inc de
    ld a,[de]
    ld [hl],a
    inc de
    res 6,d
    jp $56F2
.fixed_done:
    res 6,d
    jp $5705

; BB1 fixed routine $170E performs a VBlank-timed transfer from the currently
; selected logical ROM bank through DE into VRAM through HL, 32 bytes per B
; block. Relocated fixed code keeps V0 physically mapped, so execute each
; 32-byte inner block from real ROM0 while exposing H_LOG, then restore V0.
; The fixed-source branch also supports logical DE<$4000 by reading the same
; bytes from the relocated V0 window at DE+$4000.
host_bb1_copy_vram32::
    ld c,$20
    bit 6,d
    jr z,.fixed_source
    call host_map_current_logical
.copy_upper:
    ld a,[de]
    inc de
    ld [hl+],a
    dec c
    jr nz,.copy_upper
    push af
    ld a,V0
    call host_map_physical_a
    pop af
    ret
.fixed_source:
    set 6,d
.copy_fixed:
    ld a,[de]
    inc de
    ld [hl+],a
    dec c
    jr nz,.copy_fixed
    res 6,d
    ret


; BB1 fixed routine $1B5D copies eight 2-byte records from the currently
; selected upper bank at $5F67 into a sparse WRAM table at $C112. Relocated
; fixed code sees V0 in the switchable window, so perform the source reads from
; real host ROM0 while H_LOG is physically mapped. The following XOR A at
; logical $1B90 overwrites A/F, so only C/DE/HL postconditions matter here.
host_bb1_copy_c112_table::
    ld de,$C112
    ld hl,$5F67
    ld c,$08
    call host_map_current_logical
.loop:
    ld a,[hl+]
    ld [de],a
    inc e
    ld a,[hl+]
    ld [de],a
    inc e
    inc e
    inc e
    dec c
    jr nz,.loop
    ld a,V0
    call host_map_physical_a
    ret

; Original BB2 routine $3FA5: copy BC bytes [HL+] -> [DE+]. The original loop
; executes in MBC1 fixed bank while reading the selected upper ROM bank.
host_copy_bc::
    ; Sole caller $02BB always supplies B=0 and a nonzero C byte count. The
    ; original 16-bit loop is intentionally replaced with a faster C-only loop:
    ; BB2 starts these VRAM copies at LY=146, and MBC5 mapping overhead would
    ; otherwise push the last writes out of VBlank. Final A/F/BC match the
    ; original loop: A=0, B=C=0, Z=1, N=H=C=0.
    ldh a,[H_LOG]
    add V0
    ldh [H_PHYS],a
    ld [MBC5_ROM],a
.loop:
    ld a,[hl+]
    ld [de],a
    inc de
    dec c
    jr nz,.loop
    xor a
    push af
    ld a,V0
    ldh [H_PHYS],a
    ld [MBC5_ROM],a
    pop af
    ret

; Original BB2 routine $2C90: copy B bytes [HL+] -> [DE+]. Preserve the final
; A/F produced by the source loop across restoration of relocated fixed bank 0.
host_copy_b::
    call host_map_current_logical
.loop:
    ld a,[hl+]
    ld [de],a
    inc de
    dec b
    jr nz,.loop
    push af
    ld a,V0
    call host_map_physical_a
    pop af
    ret

; Original BB2 routine $2C88: first byte is a length which is also copied to
; destination, followed by B payload bytes. Run the entire source-reading body
; while the selected logical bank is actually visible.
host_copy_prefixed_b::
    call host_map_current_logical
    ld a,[hl+]
    ld b,a
    ld [de],a
    inc de
.loop:
    ld a,[hl+]
    ld [de],a
    inc de
    dec b
    jr nz,.loop
    push af
    ld a,V0
    call host_map_physical_a
    pop af
    ret

; Original BB2 routine $2DD9-$2E36. It walks a ROM-side descriptor stream and
; copies four bytes per record into two RAM destinations. Keeping this routine
; in real MBC5 bank 0 lets both its DE source pointer and derived HL table
; pointer address the selected upper ROM bank exactly as they do on MBC1.
; Original BB2 routine $2E6E resolves a two-level pointer table in the
; selected upper ROM bank, tail-dispatches through the resulting HL, then calls
; fixed routine $38C3. Execute the ROM lookup in real bank 0 and dispatch either
; to the selected upper bank or to relocated fixed code as appropriate.
; Read a 16-bit pointer from a logical BB2 ROM address in HL. Logical
; <$4000 addresses live in BB2's relocated fixed bank V0 and are translated to
; the MBC5 switchable window; $4000-$7FFF addresses live in H_LOG. Preserve the
; incoming flags, return the word in HL, and leave A equal to the low byte just
; like `ld a,[hl+] / ld h,[hl] / ld l,a`. E is scratch; the dispatcher saves DE.
host_read_logical_word_hl::
    push af
    bit 6,h
    jr nz,.upper
    ld a,V0
    call host_map_physical_a
    set 6,h
    jr .mapped
.upper:
    ldh a,[H_LOG]
    call host_map_logical_a
.mapped:
    ld a,[hl+]
    ld e,a
    ld a,[hl]
    ld h,a
    ld l,e
    pop af
    ld a,e
    ret

host_dispatch_2e6e::
    push de
    ld b,$00
    ld a,[$CE79]
    add a
    ld c,a
    add hl,bc
    call host_read_logical_word_hl
    ld b,$00
    ld a,[$CE78]
    add a
    ld c,a
    add hl,bc
    call host_read_logical_word_hl
    pop de
    push af
    bit 6,h
    jr z,.low_target
    pop af
    ; The second pointer table may have lived in relocated fixed bank 0, so
    ; explicitly map the selected logical upper bank before an upper target.
    push af
    ldh a,[H_LOG]
    call host_map_logical_a
    pop af
    call host_jp_hl
    jr .after_target
.low_target:
    pop af
    push af
    ld a,V0
    call host_map_physical_a
    pop af
    set 6,h
    call host_jp_hl
.after_target:
    push af
    ld a,V0
    call host_map_physical_a
    pop af
    call $78C3
    ret

host_descriptor_step::
    ld bc,$C114
    ld de,$C134
    di
    call host_map_current_logical
.loop:
    push bc
    push de
    ld a,[$C15A]
    ld e,a
    ld a,[$C15B]
    ld d,a
    ld a,[$C158]
    ld c,a
    ld a,[$C159]
    ld b,a
    ld a,[de]
    ld l,a
    ld h,$00
    add hl,hl
    add hl,hl
    add hl,bc
    inc de
    ld a,e
    ld [$C15A],a
    ld a,d
    ld [$C15B],a
    ld a,[$C113]
    inc a
    ld [$C113],a
    pop de
    pop bc
    ld a,[hl+]
    ld [bc],a
    inc bc
    ld a,[hl+]
    ld [bc],a
    inc bc
    ld a,[hl+]
    ld [de],a
    inc de
    ld a,[hl+]
    ld [de],a
    inc de
    ld a,[$C155]
    dec a
    ld [$C155],a
    jr nz,.check_count
    ld a,[$C157]
    jr .finish_count
.check_count:
    ld a,[$C113]
    ld l,a
    ld a,[$C157]
    cp l
    jr nz,.loop
.finish_count:
    add a
    add a
    dec a
    ld [$C113],a
    push af
    ld a,V0
    call host_map_physical_a
    pop af
    ei
    ret

; VBlank may interrupt either virtual bank 0 or a far-called bank. Preserve
; the actual/planned physical mapping, run the relocated BB2 handler, restore,
; then perform the one real RETI.
host_vblank::
    ; BB1's VBlank code contains a stack-switching scheduler. Do not CALL it:
    ; an extra host return frame would be captured as part of the task context.
    push af
    ld a,[H_PHYS]
    ld [H_IRQ],a
    ld a,V0
    call host_map_physical_a
    pop af
    jp $4C6F
''']
 for t in sorted(upper_targets):
  dest=SHADOW_6FD1 if t==0x6FD1 else t
  lines.append(f'''\nhost_upper_{t:04x}::\n    push af\n    ldh a,[H_LOG]\n    call host_map_logical_a\n    pop af\n    call ${dest:04X}\n    push af\n    ld a,V0\n    call host_map_physical_a\n    pop af\n    ret\n''')
 # $021E is special: upper-bank callers rely on their current ROM bank as the
 # copy source. Because this wrapper executes from real ROM0, leave the upper
 # mapping untouched and reproduce $021E directly, then RET to that same bank.
 if 0x021E in low_targets:
  lines.append('''
host_low_021e::
.loop:
    ld a,[hl+]
    ld [de],a
    inc de
    dec bc
    ld a,b
    or c
    jr nz,.loop
    ret
''')
 if 0x0465 in low_targets:
  lines.append('''
host_low_0465::
    push af
    ld a,V0
    call host_map_physical_a
    pop af
    call $4465
host_low_0465_resume::
    push af
    ldh a,[H_LOG]
    call host_map_logical_a
    pop af
    ret
''')
 if 0x0324 in low_targets:
  lines.append(r'''
; Banked queue callers need their selected ROM window to remain visible.
host_low_0324::
    ldh a,[$FF8F]
    or a
    ret z
    ldh a,[$FF8E]
    ld l,a
    ld a,h
    ld h,$DD
    ld [hl+],a
    ld [hl],c
    inc l
    ld [hl],b
    inc l
    ld b,a
    ldh a,[$FF8F]
    ld c,a
.copy:
    ld a,[de]
    ld [hl+],a
    inc de
    dec c
    jr z,.done
    dec b
    jr nz,.copy
.done:
    ld [hl],$00
    ld a,l
    ld hl,$FF8E
    ld [hl+],a
    ld a,c
    ld [hl],a
    ret
''')
 for t in sorted(low_targets):
  if t in (0x021E,0x0324,0x0465): continue
  lines.append(f'''
host_low_{t:04x}::
    push af
    ld a,V0
    call host_map_physical_a
    pop af
    call ${t+0x4000:04X}
    push af
    ldh a,[H_LOG]
    call host_map_logical_a
    pop af
    ret
''')
 lines.append(r'''
; Read a bank-1 round-intro transfer pointer with the native HL/AF result.
host_bb1_intro_pointer::
    push af
    call host_map_current_logical
    ld e,[hl]
    inc hl
    ld d,[hl]
    ld a,V0
    call host_map_physical_a
    pop af
    ret

; Experimental BB1 round-start ROM-data virtualization.
; Original logical $1870-$1889 indexes a word table in H_LOG and copies the
; selected eight-byte round payload to HRAM $FFB5-$FFBC. Execute that block
; from real ROM0 while the logical upper bank is physically visible, then
; restore V0 without changing the original final AF/register state.
host_bb1_round_payload::
    ldh a,[H_LOG]
    call host_map_logical_a
    ld hl,$4000
    add hl,de
    ld a,[hl+]
    ld [$C22B],a
    ld a,[hl-]
    ld [$C22C],a
    ld l,[hl]
    ld h,a
    ld de,$FFB5
    ld b,$08
.copy:
    ld a,[hl+]
    ld [de],a
    inc e
    dec b
    jr nz,.copy
    ld a,b
    push af
    ld a,V0
    call host_map_physical_a
    pop af
    ret
''')
 lines.append(r'''
; Each VBlank tile-pair source can address fixed or selected-upper ROM.
host_bb1_tile_pair::
    ld hl,$FFAB
    ld [hl],$CF
    inc l
    ld [hl],$17
    inc l
    ld a,[hl+]
    ld h,[hl]
    ld l,a
    ld b,$20
    push af
    call host_bb1_tile_source_hl
    pop af
.wait:
    ldh a,[$FF44]
    cp $91
    jr c,.wait
.first:
    ld a,[hl+]
    ld [de],a
    inc e
    dec b
    jr nz,.first
    ld hl,$FFAF
    ld a,[hl+]
    ld h,[hl]
    ld l,a
    ld b,$20
    push af
    call host_bb1_tile_source_hl
    pop af
.second:
    ld a,[hl+]
    ld [de],a
    inc e
    dec b
    jr nz,.second
    push af
    ldh a,[$FFB0]
    bit 6,a
    jr nz,.keep_high
    res 6,h
.keep_high:
    ld a,V0
    call host_map_physical_a
    pop af
    jp $4CB8
host_bb1_tile_source_hl::
    bit 6,h
    jp nz,host_map_current_logical
    set 6,h
    ld a,V0
    jp host_map_physical_a
''')
 lines.append(r'''
; Copy the fixed-ROM layout header while preserving its logical continuation.
host_bb1_layout_header::
    set 6,h
.loop:
    ld a,[hl+]
    ld [de],a
    inc e
    dec b
    jr nz,.loop
    res 6,h
    ret
''')
 lines.append(r'''
; Sprite tile streams use logical bank 3 for both 32-byte blocks.
host_bb1_sprite_pair::
    ld hl,$FF9E
    ld a,[hl]
    or a
    jp z,$4CB8
    ld a,$03
    ldh [H_LOG],a
    call host_map_logical_a
    ld de,$8000
    ld [hl],$00
    inc l
    ld a,[hl+]
    ld h,[hl]
    ld l,a
    ld b,$20
.wait:
    ldh a,[$FF44]
    cp $91
    jr c,.wait
.first:
    ld a,[hl+]
    ld [de],a
    inc e
    dec b
    jr nz,.first
    ld hl,$FFA1
    ld a,[hl+]
    ld h,[hl]
    ld l,a
    ld b,$20
.second:
    ld a,[hl+]
    ld [de],a
    inc e
    dec b
    jr nz,.second
    ld a,$01
    ldh [H_LOG],a
    push af
    ld a,V0
    call host_map_physical_a
    pop af
    jp $4CB8
''')
 lines.append(r'''
; The two 64-byte transfer paths consume bank-3 graphics and descriptors.
host_bb1_graphics64::
    ld a,$03
    ldh [H_LOG],a
    call host_map_logical_a
    ld hl,$FFAB
    ld [hl],$CF
    inc l
    ld [hl],$17
    inc l
    ld e,[hl]
    inc l
    ld d,[hl]
    inc l
    ld a,[hl+]
    ld h,[hl]
    ld l,a
    jr host_bb1_graphics64_copy
host_bb1_graphics64_stream::
    ld a,$03
    ldh [H_LOG],a
    call host_map_logical_a
    ld hl,$FFAD
    ld c,[hl]
    inc l
    ld b,[hl]
    ld a,[bc]
    ld e,a
    inc bc
    ld a,[bc]
    ld d,a
    inc bc
    ld [hl],b
    dec l
    ld [hl],c
    inc l
    inc l
    ld a,[hl]
    ld c,a
    add $40
    ld [hl+],a
    ld a,[hl]
    ld b,a
    adc $00
    ld [hl],a
    ld l,c
    ld h,b
host_bb1_graphics64_copy::
    ld b,$40
.wait:
    ldh a,[$FF44]
    cp $91
    jr c,.wait
.copy:
    ld a,[de]
    ld [hl+],a
    inc de
    dec b
    jr nz,.copy
    ld a,$01
    ldh [H_LOG],a
    push af
    ld a,V0
    call host_map_physical_a
    pop af
    jp $4CB8
''')
 lines.append(r'''
; Read the enemy pointer table and records while bank 3 is physically visible.
host_bb1_enemy_records::
    ld a,$03
    ldh [H_LOG],a
    call host_map_logical_a
    ld a,[$C200]
    add a
    ld e,a
    ld d,$00
    ld hl,$5FC0
    add hl,de
    ld e,[hl]
    inc hl
    ld d,[hl]
    ld hl,$C600
    ld c,l
    xor a
    ldh [$FFC3],a
.next:
    ld l,c
    ld a,[de]
    cp $FF
    jr z,.done
    inc de
    ld [hl],$10
    inc l
    ld b,a
    and $7F
    ld [hl+],a
    ld a,[de]
    inc de
    ld [hl+],a
    ld [hl],$00
    inc l
    ld a,[de]
    inc de
    ld [hl+],a
    ld [hl],$00
    ld a,c
    add $0C
    ld l,a
    ld a,b
    and $80
    ld b,a
    ld [hl+],a
    xor $80
    ld [hl],a
    ld a,c
    add $10
    ld l,a
    xor a
    ld [hl+],a
    ld [hl],a
    ld a,c
    add $1B
    ld l,a
    ld a,b
    or $20
    ld [hl+],a
    xor a
    ld [hl+],a
    ld [hl+],a
    ld [hl+],a
    ld [hl+],a
    inc l
    ld [hl+],a
    dec a
    ld [hl],a
    ldh a,[$FFC3]
    inc a
    ldh [$FFC3],a
    ld a,c
    add $24
    ld c,a
    cp $FC
    jr c,.next
.done:
    ld a,$01
    ldh [H_LOG],a
    push af
    ld a,V0
    call host_map_physical_a
    pop af
    jp $6F35
''')
 lines.append(r'''
; Background rows can use either fixed-ROM descriptors or bank-4 streams.
host_bb1_background_swap::
    call host_bb1_background_read_bc
    swap a
    ret
host_bb1_background_low::
    call host_bb1_background_read_bc
    and $0F
    ret
host_bb1_background_read_bc::
    bit 6,b
    jr nz,.upper
    push hl
    ld h,b
    ld l,c
    set 6,h
    ld a,[hl]
    pop hl
    ret
.upper:
    call host_map_current_logical
    ld a,[bc]
    push af
    ld a,V0
    call host_map_physical_a
    pop af
    ret
''')
 lines.append(r'''
; Fixed queue callers can also enqueue selected-upper-ROM graphics.
host_bb1_queue_copy::
    ldh a,[$FF8F]
    or a
    ret z
    bit 7,d
    jr nz,.ram
    bit 6,d
    jr z,.ram
    push af
    call host_map_current_logical
    pop af
    call host_low_0324
    push af
    ld a,V0
    call host_map_physical_a
    pop af
    ret
.ram:
    jp $4328
''')
 lines.append(r'''
; The banked cooperative task must enter its bank-1 code, not relocated $0669.
host_task_4669::
    push af
    ld a,$01
    ldh [H_LOG],a
    call host_map_logical_a
    pop af
    jp $4669
''')
 lines.append(r'''
; Death animation pointers at bank-1 $5F5F/$5F63 supply both sprite blocks.
host_bb1_death_sprite_pointers::
    call host_map_current_logical
    ld a,[hl+]
    add $00
    ld [de],a
    inc e
    ld a,[hl+]
    adc $40
    ld [de],a
    inc e
    ld a,[hl+]
    add $00
    ld [de],a
    inc e
    ld a,[hl+]
    adc $40
    ld [de],a
    push af
    ld a,V0
    call host_map_physical_a
    pop af
    ret
''')
 lines.append(r'''
; Queue uploads can reach the first visible line after LCD enable.
; At LY 144-147 at least six VBlank lines remain: enough for 64 bytes at
; 36 cycles each. Other phases wait for accessible VRAM before each byte.
; The queue header's OR clears carry; AND preserves that loop postcondition.
host_bb1_queue_vram::
    ld a,b
    cp $41
    jr nc,.guard
    ldh a,[$FF44]
    cp $90
    jr c,.guard
    cp $94
    jr nc,.guard
    or a
.fast:
    ld a,[de]
    ld [hl+],a
    inc e
    dec b
    jr nz,.fast
    ret
.guard:
    ldh a,[$FF41]
    and $02
    jr nz,.guard
    ld a,[de]
    ld [hl+],a
    inc e
    dec b
    jr nz,.guard
    ret
''')
 lines.append(r'''
; Round-object coordinates are stored after the selected bank's layout header.
host_bb1_object_coordinates::
    push af
    call host_map_current_logical
    pop af
    ld a,[de]
    inc de
    ld [hl+],a
    ld a,[de]
    inc de
    ld [hl+],a
    push af
    ld a,V0
    call host_map_physical_a
    pop af
    ret
''')
 lines.append('\nhost_end::\n')
 return ''.join(lines)

def parse_sym(p):
 out={}
 for line in p.read_text().splitlines():
  m=re.match(r'([0-9A-Fa-f]+):([0-9A-Fa-f]+)\s+(.+)',line)
  if m: out[m.group(3).strip()]=int(m.group(2),16)
 return out

def assemble_host(asm):
 BUILD.mkdir(exist_ok=True)
 ap=BUILD/'host.asm'; op=BUILD/'host.o'; rp=BUILD/'host.gb'; sp=BUILD/'host.sym'
 ap.write_text(asm)
 subprocess.run([str(RGBASM),'-o',str(op),str(ap)],check=True)
 subprocess.run([str(RGBLINK),'-p','0xFF','-n',str(sp),'-o',str(rp),str(op)],check=True)
 return rp.read_bytes(),parse_sym(sp)

def put16(buf,off,v):buf[off+1]=v&255;buf[off+2]=v>>8

def main():
 classic=CLASSIC.read_bytes();bb1=BB1.read_bytes();bb2=BB2.read_bytes()
 assert md5(classic)==EXPECTED['classic'];assert md5(bb1)==EXPECTED['bb1'];assert md5(bb2)==EXPECTED['bb2']
 # First pass discovers the normal fixed-bank graph. Banked routines can call
 # additional fixed routines that are not otherwise reachable from bank 0. Discover
 # those edges, then feed every low target back into fixed CFG discovery so the
 # relocated routine subtree is rewritten recursively rather than copied verbatim.
 mapper0,seen0,branches0,upper0,jphl0,rsts0=discover_bank0(bb1)
 seeds,seen_b,back,rsts_b=banked_edges(bb1)
 low_targets={t for *_,t in back}
 mapper,seen,branches,upper,jphl,rsts=discover_bank0(bb1, low_targets)
 assert mapper==mapper0
 palette_regs={0x47:0xE7,0x48:0xEF,0x49:0xF7}  # RST $20/$28/$30
 fixed_palette_sites=[(pc,bb1[pc+1]) for pc in sorted(seen)
                      if bb1[pc]==0xE0 and pc+1<len(bb2) and bb1[pc+1] in palette_regs]
 banked_palette_sites=[]
 for bank,pcs in seen_b.items():
  for pc in sorted(pcs):
   off=bank*BANK+(pc-0x4000)
   if bb1[off]==0xE0 and bb1[off+1] in palette_regs:
    banked_palette_sites.append((bank,pc,bb1[off+1]))
 upper_targets={t for _,_,t in upper}
 print('bank0 decoded',len(seen),'mapper',len(mapper),'upper edges',len(upper),'targets',len(upper_targets),'jp hl',list(map(hex,jphl)))
 print('banked back edges',len(back),'targets',len(low_targets),'rsts',[(b,hex(a),hex(o)) for b,a,o in rsts_b]); print('palette sites fixed/banked',len(fixed_palette_sites),len(banked_palette_sites))
 # CALL/JP (including conditional forms) can share the same host_upper wrapper:
 # CALL returns to the next instruction; JP returns through the caller's existing frame.
 asm=make_asm(upper_targets,low_targets)
 host,sym=assemble_host(asm)
 assert sym['host_end']<HOST_LIMIT,(hex(sym['host_end']),hex(HOST_LIMIT))
 print('host',hex(HOST_ORG),'-',hex(sym['host_end']-1),sym['host_end']-HOST_ORG,'bytes')

 # Phase-0 physical layout.
 out=bytearray([0xFF])*0x200000
 out[:len(classic)]=classic
 out[0x40*BANK:0x48*BANK]=bb1
 out[0x48*BANK:0x58*BANK]=bb2
 out[0x148]=0x06
 out[0x149]=0x03

 # Diagnostic: make accidental execution of Classic fixed code obvious, while
 # retaining the Nintendo logo/header bytes needed by boot ROM.
 out[0x0068:0x0100]=bytes([0xD3])*(0x100-0x68)
 out[0x0150:HOST_ORG]=bytes([0xD3])*(HOST_ORG-0x150)
 # Copy host vectors, entry and fixed host service area only.
 out[0x0000:0x0061]=host[0x0000:0x0061]
 out[0x0100:0x0104]=host[0x0100:0x0104]
 out[HOST_ORG:sym['host_end']]=host[HOST_ORG:sym['host_end']]

 # Rewrite BB1 virtual bank 0 in its embedded physical bank.
 voff=BASE*BANK
 v=bytearray(bb1[:BANK])
 # Every literal MBC1 ROM-bank write becomes a logical-state write in HRAM.
 # LDH [$D6],A + NOP is exactly three bytes and 16 cycles, matching the original
 # LD [$2100],A timing while preserving registers/flags. This avoids injecting a
 # CALL/RET delay into BB2's VBlank-timed graphics paths.
 for i in sorted(mapper):
  assert v[i:i+3]==b'\xea\x00\x21'
  v[i:i+3]=bytes([0xE0,0xD6,0x00])
 # Relocate direct fixed-bank control flow and redirect calls into selected upper banks.
 upper_by_pc={pc:t for pc,op,t in upper}
 for pc,op,t in branches:
  if pc in upper_by_pc:
   lab=f'host_upper_{t:04x}'; put16(v,pc,sym[lab])
  elif t<0x4000:
   put16(v,pc,t+0x4000)
 # JP HL -> RST $08. BB1's original RST $08 is itself a JP HL, so the host
 # vector can route logical low targets to relocated V0 and upper targets through H_LOG.
 for pc in jphl:
  assert v[pc]==0xE9; v[pc]=0xCF
 # Mirror reachable DMG palette writes through unused physical RST vectors.
 # RST + NOP occupies the original two bytes; the host hook performs the
 # original FF47-FF49 write and updates the corresponding CGB palette.
 for pc,reg in fixed_palette_sites:
  assert bytes(v[pc:pc+2])==bytes([0xE0,reg]),(hex(pc),v[pc:pc+2].hex())
  v[pc:pc+2]=bytes([palette_regs[reg],0x00])
 # BB1's VBlank scheduler must see the hardware interrupt stack shape. Tail-entry
 # is handled by host_vblank; replace EI/RETI with NOP + RST $18 so the host can
 # discard the one-byte RST frame, remap V0, and execute the sole real RETI.
 assert bytes(v[0x0CB8:0x0CBA])==bytes.fromhex('fbd9')
 v[0x0CB8:0x0CBA]=bytes([0x00,0xDF])
 # Context switcher $042F eventually loads a new SP and RETs to a logical low PC.
 # Route that RET through RST $10 so the saved PC is relocated in-place.
 assert v[0x0446]==0xC9; v[0x0446]=0xD7
 # BB1 clears most of HRAM during startup, including H_PHYS/H_LOG. Replace
 # the post-clear CALL $01F2 with a host tail-wrapper that restores host state
 # and then runs the original relocated routine.
 assert v[0x0177]==0xCD
 w=sym['host_after_hram_clear']; put16(v,0x0177,w)

 # The enemy dispatcher reads fixed-ROM pointer table $29E3 before JP HL.
 assert bytes(v[0x29DA:0x29DC])==bytes.fromhex('3e29')
 v[0x29DB]=0x69

 # The object dispatcher reads fixed-ROM pointer table $2C7F through HL.
 # Its computed base must reference the relocated table while V0 is mapped.
 assert bytes(v[0x2C76:0x2C78])==bytes.fromhex('3e2c')
 v[0x2C77]=0x6C

 # Enemy-chain awards and bonus graphics use fixed-ROM tables.
 assert bytes(v[0x2AA4:0x2AA6])==bytes.fromhex('3e2a')
 v[0x2AA5]=0x6A
 assert bytes(v[0x2AB3:0x2AB6])==bytes.fromhex('21f62f')
 v[0x2AB5]=0x6F

 # Trapped-enemy state reads fixed lifetime and velocity tables.
 for pc,old,new in [(0x2E0B,0x2F,0x6F),(0x2E36,0x2D,0x6D)]:
  assert bytes(v[pc:pc+2])==bytes([0x3E,old])
  v[pc+1]=new

 # Tile-pair transfers run outside V0 so their upper-ROM sources remain visible.
 assert bytes(v[0x1755:0x1758])==bytes.fromhex('21abff')
 w=sym['host_bb1_tile_pair']; v[0x1755:0x1758]=bytes([0xC3,w&255,w>>8])

 assert bytes(v[0x16A6:0x16AC])==bytes.fromhex('2a121c0520fa')
 w=sym['host_bb1_layout_header']; v[0x16A6:0x16AC]=bytes([0xCD,w&255,w>>8,0,0,0])

 # Fixed-ROM animation descriptor roots stay in the relocated V0 window.
 for pc,old,new in [(0x2301,0x24,0x64),(0x243E,0x24,0x64)]:
  assert bytes(v[pc:pc+2])==bytes([0x3E,old])
  v[pc+1]=new
 assert bytes(v[0x2354:0x2356])==bytes.fromhex('ce25')
 v[0x2355]=0x65
 for off in range(0x2498,0x25AA,2):
  ptr=int.from_bytes(bb1[off:off+2],'little')
  assert 0x25AA<=ptr<0x2990,(hex(off),hex(ptr))
  v[off:off+2]=(ptr+0x4000).to_bytes(2,'little')

 assert bytes(v[0x17CF:0x17D2])==bytes.fromhex('219eff')
 w=sym['host_bb1_sprite_pair']; v[0x17CF:0x17D2]=bytes([0xC3,w&255,w>>8])

 # Background descriptor pointers refer to fixed-ROM data.
 for pc in [0x141E,0x1461]:
  assert bytes(v[pc:pc+2])==bytes.fromhex('3e1b')
  v[pc+1]=0x5B
 assert bytes(v[0x0A04:0x0A07])==bytes.fromhex('212c0a')
 v[0x0A06]=0x4A

 for pc,label in [(0x1780,'host_bb1_graphics64'),(0x1797,'host_bb1_graphics64_stream')]:
  assert bytes(bb1[pc:pc+5])==bytes.fromhex('3e03ea0021')
  w=sym[label]; v[pc:pc+5]=bytes([0xC3,w&255,w>>8,0,0])

 assert bytes(v[0x0310:0x0316])==bytes.fromhex('1a221c0520fa')
 w=sym['host_bb1_queue_vram']; v[0x0310:0x0316]=bytes([0xCD,w&255,w>>8,0,0,0])

 # Both round-object coordinate pairs come from the selected layout bank.
 for pc in (0x1977,0x198A):
  assert bytes(v[pc:pc+6])==bytes.fromhex('1a13221a1322')
  w=sym['host_bb1_object_coordinates']; v[pc:pc+6]=bytes([0xCD,w&255,w>>8,0,0,0])
 assert bytes(v[0x19C8:0x19CB])==bytes.fromhex('21aa31')
 v[0x19CA]=0x71

 # Death animation pointer tables live in the selected logical upper bank.
 assert bytes(v[0x1B49:0x1B4C])==bytes.fromhex('2ac600')
 w=sym['host_bb1_death_sprite_pointers']; v[0x1B49:0x1B4C]=bytes([0xC3,w&255,w>>8])

 # Enemy records must be consumed with their selected upper bank mapped.
 assert bytes(bb1[0x2ECC:0x2ED1])==bytes.fromhex('3e03ea0021')
 w=sym['host_bb1_enemy_records']; v[0x2ECC:0x2ED1]=bytes([0xC3,w&255,w>>8,0,0])

 for pc,label,original in [(0x14AB,'host_bb1_background_swap','0acb37'),(0x14BA,'host_bb1_background_low','0ae60f')]:
  assert bytes(v[pc:pc+3])==bytes.fromhex(original)
  w=sym[label]; v[pc:pc+3]=bytes([0xCD,w&255,w>>8])

 assert bytes(v[0x0324:0x0327])==bytes.fromhex('f08fb7')
 w=sym['host_bb1_queue_copy']; v[0x0324:0x0327]=bytes([0xC3,w&255,w>>8])

 # A raw upper-bank task PC cannot execute while V0 is physically mapped.
 assert bytes(v[0x0489:0x048B])==bytes.fromhex('6946')
 v[0x0489:0x048B]=sym['host_task_4669'].to_bytes(2,'little')

 # Startup $01B3 copies a 10-byte HRAM routine from fixed ROM $01C1. Because
 # relocated fixed code executes with BB1 V0 in the switchable window, point the
 # source at the relocated copy instead of accidentally reading Classic ROM0.
 assert bytes(v[0x01B7:0x01BA])==bytes.fromhex('21c101')
 v[0x01B8]=0xC1; v[0x01B9]=0x41
 # Startup routine $03F4 copies the 12-byte fixed-ROM table at $0481 to $C0A0.
 assert bytes(v[0x0402:0x0405])==bytes.fromhex('218104')
 v[0x0403]=0x81; v[0x0404]=0x44

 # BB1 fixed routine $021E copies BC bytes from selected upper ROM. These four
 # fixed-bank callers all provide upper-ROM source pointers after choosing H_LOG.
 for pc in (0x0507,0x0513,0x0524,0x05B1):
  assert bytes(v[pc:pc+3])==bytes([0xCD,0x1E,0x42]),(hex(pc),v[pc:pc+3].hex())
  w=sym['host_bb1_copy_bc']; put16(v,pc,w)

 # Title transfer command parser $16D7 reads its command stream through DE
 # from the currently selected upper bank. Route the three stream reads
 # ($16E3/$16EC/$16EF) through one host routine by replacing the first
 # LD A,(DE) / OR A / JR Z opcode trio with a tail JP. The host routine
 # reproduces both branches and resumes at relocated $16F2 or $1705.
 assert bytes(v[0x16E3:0x16E6])==bytes.fromhex('1ab728'),v[0x16E3:0x16E6].hex()
 w=sym['host_bb1_transfer_stream_entry']
 v[0x16E3:0x16E6]=bytes([0xC3,w&255,w>>8])

 # Transfer worker $170E consumes the parser's source pointer through DE while
 # copying 32-byte blocks into VRAM. Run the inner block in host ROM0 so the
 # selected H_LOG bank is visible, then resume at DEC B / outer-loop control.
 assert bytes(v[0x1725:0x172D])==bytes.fromhex('0e201a13220d20fa'),v[0x1725:0x172D].hex()
 w=sym['host_bb1_copy_vram32']
 v[0x1725:0x172D]=bytes([0xCD,w&255,w>>8,0,0,0,0,0])

 # Round-intro pointer reads at $134E use the selected upper bank.
 assert bytes(v[0x134E:0x1351])==bytes.fromhex('5e2356')
 w=sym['host_bb1_intro_pointer']
 v[0x134E:0x1351]=bytes([0xCD,w&255,w>>8])

 # Round-start transfer setup $168F indexes a pointer table embedded in fixed
 # BB1 ROM at logical $1A60. Relocated V0 code cannot read that table at the
 # original low address because host/Classic ROM0 occupies $0000-$3FFF. Point
 # the literal at the relocated V0 copy instead.
 assert bytes(v[0x169A:0x169D])==bytes.fromhex('21601a'),v[0x169A:0x169D].hex()
 v[0x169C]=0x5A

 # Round-start setup $1B5D copies a sparse table from selected upper ROM at
 # $5F67. Route the exact $1B7D-$1B8F copy loop through host ROM0 so H_LOG is
 # visible, then resume at the original XOR A at relocated $5B90.
 assert bytes(v[0x1B7D:0x1B90])==bytes.fromhex('1112c121675f0e082a121c2a121c1c1c0d20f5'),v[0x1B7D:0x1B90].hex()
 w=sym['host_bb1_copy_c112_table']
 v[0x1B7D:0x1B90]=bytes([0xCD,w&255,w>>8])+bytes([0x00])*(0x1B90-0x1B80)

 # Additional BB1 fixed-bank ROM-data readers are virtualized incrementally from
 # old-fails/new-passes runtime evidence.
 # Experimental v0.15-recon: $1870-$1889 reads a pointer table and payload from
 # the selected upper bank. With V0 physically mapped those reads are wrong.
 original_round_payload=bytes.fromhex('210040192aea2bc23aea2cc26e6711b5ff06082a121c0520fa78')
 assert bytes(v[0x1870:0x188A])==original_round_payload,v[0x1870:0x188A].hex()
 w=sym['host_bb1_round_payload']
 v[0x1870:0x188A]=bytes([0xCD,w&255,w>>8])+bytes([0x00])*(0x188A-0x1873)
 out[voff:voff+BANK]=v

 # Patch discovered banked->fixed direct control edges to host low wrappers.
 for bank,pc,op,t in back:
  phys=BASE+bank
  off=phys*BANK+(pc-0x4000)
  orig_off=bank*BANK+(pc-0x4000)
  assert out[off]==bb1[orig_off]==op
  w=sym[f'host_low_{t:04x}']; out[off+1]=w&255;out[off+2]=w>>8

 # Banked reachable DMG palette writes use the same physical RST hooks.
 for bank,pc,reg in banked_palette_sites:
  off=(BASE+bank)*BANK+(pc-0x4000)
  orig=bank*BANK+(pc-0x4000)
  assert bytes(out[off:off+2])==bytes(bb1[orig:orig+2])==bytes([0xE0,reg]),(bank,hex(pc),out[off:off+2].hex())
  out[off:off+2]=bytes([palette_regs[reg],0x00])

 # Bank-3 $6FD1-$705B is both executable and copied as title graphics.
 # Keep the original bytes intact for data reads and execute a patched shadow
 # from verified $FF padding at $7E00 instead.
 dual_start,dual_end=0x6FD1,0x705C
 dual_len=dual_end-dual_start
 bank3_orig=3*BANK+(dual_start-0x4000)
 bank3_phys=(BASE+3)*BANK
 dual_phys=bank3_phys+(dual_start-0x4000)
 shadow_phys=bank3_phys+(SHADOW_6FD1-0x4000)
 shadow_orig=3*BANK+(SHADOW_6FD1-0x4000)
 assert bytes(bb1[shadow_orig:shadow_orig+dual_len])==bytes([0xFF])*dual_len
 original_dual=bytes(bb1[bank3_orig:bank3_orig+dual_len])
 out[dual_phys:dual_phys+dual_len]=original_dual
 shadow=bytearray(original_dual)
 for bank,pc,op,t in back:
  if bank==3 and dual_start<=pc<dual_end and t<0x4000:
   rel=pc-dual_start
   assert shadow[rel]==op
   w=sym[f'host_low_{t:04x}']
   shadow[rel+1]=w&255;shadow[rel+2]=w>>8
 out[shadow_phys:shadow_phys+dual_len]=shadow

 # Header/checksums after diagnostic entry/vector changes.
 out[0x14D]=hsum(out);g=gsum(out);out[0x14E]=g>>8;out[0x14F]=g&255
 OUT.write_bytes(out)
 print('wrote',OUT,'md5',md5(out))
 # Manifest for debugging/repro.
 (BUILD/'manifest.txt').write_text('\n'.join([
  f'output_md5={md5(out)}',f'host_end=${sym["host_end"]:04X}',
  f'bank0_decoded={len(seen)}',f'mapper_sites={len(mapper)}',f'upper_edges={len(upper)}',
  f'upper_targets={len(upper_targets)}',f'banked_back_edges={len(back)}',f'low_targets={len(low_targets)}',f'palette_fixed={len(fixed_palette_sites)}',f'palette_banked={len(banked_palette_sites)}',
  'jp_hl='+','.join(f'${x:04X}' for x in jphl),
 ]))

if __name__=='__main__':main()
