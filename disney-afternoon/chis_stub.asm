; ChisFlash MAX launch stub, copied to HRAM at $FF80: once the cart switches to the
; game's slot the menu ROM is gone, so the end of the sequence runs from here.
; The menu patches the slot operand.
;
; The cart's CPLD watches these writes, as worked out by the chisflash-max16-menu
; project (https://github.com/dmcclung/chisflash-max16-menu):
;   $4000 bit 6 set ... arm multicart mode
;   $B000 = slot ...... pick the game slot (0 is the 1 MiB slot at 1 MiB)
;   $A000 = 1 ......... switch to that slot
;   $4000 = anything .. reset the console, which then boots the game as its own cart

launch:
    ld a,$40
    ld ($4000),a
    ld a,0                  ; patched: slot
    ld ($B000),a
    ld a,1
    ld ($A000),a
    xor a
    ld ($4000),a
hang:
    jr hang
