; ChisFlash MAX launch stub, copied to HRAM at $FF80: once the cart switches to the
; game's slot the menu ROM is gone, so the rest of the start runs from here. The
; menu patches the slot operand.
;
; The cart's CPLD watches these writes. The sequence and the warm start follow the
; menu ChisFlash ships for the cart (ChisFlash_MBC5_MAX_16in1_MENU.gb, from
; https://github.com/moribaka/ChisFlash-MBC5):
;   $4000 arm bit set ... arm multicart mode. The published MAX v1.22 CPLD arms on
;                         bit 6, the 8M CPLD and the shipped menu on bit 4, so set both;
;                         the other bit lands in an unused RAM bank bit
;   $B000 = slot ........ pick the game slot (0 is the 1 MiB slot at 1 MiB)
;   $A000 = 1 ........... switch to that slot
;   $4000 = 0 ........... disarm. A CPLD that resets the console into the slot does it
;                         here; the shipped menu doesn't wait for that, and nor does this

launch:
    ld a,$50
    ld ($4000),a
    ld a,0                  ; patched: slot
    ld ($B000),a
    ld a,1                  ; bank 1 at $4000, as a game's own cart starts
    ld ($2000),a
    xor a
    ld ($3000),a
    inc a
    ld ($A000),a
    xor a
    ld ($4000),a
    ld hl,$C000             ; start the game as the boot ROM leaves it: WRAM clear,
    xor a                   ; as a cold emulator start leaves it
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
    ld sp,SAVED_REGS        ; the registers the boot ROM left, saved by boot.asm
    pop af
    pop bc
    pop de
    pop hl                  ; SP back to $FFFE
    jp $0100
