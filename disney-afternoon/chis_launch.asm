; Patch the ChisFlash launch stub in HRAM with the slot of the game in SEL, from
; the builder's games table (one byte a game).

set_launch:
    ld a,(SEL)
    ld e,a
    ld d,0
    ld hl,games
    add hl,de
    ld a,(hl)
    ld (P_SLOT),a
    ret
