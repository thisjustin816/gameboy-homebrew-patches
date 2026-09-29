; Launch stub, copied to HRAM at $FF80 because it remaps both ROM windows.
; The menu patches the quarter, mode and entry operands before jumping here.
;
; MBC1 on a 2 MiB ROM: $4000 holds the upper two bank bits, and in mode 1
; they also pick which 512 KiB quarter appears at $0000. So a game in quarter
; k gets its own bank 0 at $0000 and its banks 1-7 at $4000, as on its own cart.

launch:
    ld a,0                  ; patched: quarter
    ld ($4000),a
    ld a,0                  ; patched: mode (0 for quarter 0, else 1)
    ld ($6000),a
    ld a,1
    ld ($2000),a
    ld hl,$C000             ; clear WRAM, as a cold emulator start leaves it
    xor a
clear_wram:
    ld (hl+),a
    ld b,a
    ld a,h
    cp $E0
    ld a,b
    jr nz,clear_wram
wait_line0:                 ; the boot ROM hands over at the top of a frame
    ldh a,($44)
    and a
    jr nz,wait_line0
    ld sp,SAVED_REGS
    pop af
    pop bc
    pop de
    pop hl                  ; SP back to $FFFE
jump:
    jp $0100                ; patched: game entry
