; Patch the MBC1 launch stub in HRAM for the game in SEL: its quarter, the MBC1
; mode and its entry point, from the builder's games table (4 bytes a game).

set_launch:
    ld a,(SEL)              ; games + 4 * SEL
    add a,a
    add a,a
    ld e,a
    ld d,0
    ld hl,games
    add hl,de
    ld a,(hl+)
    ld (P_QUARTER),a
    ld a,(hl+)
    ld (P_MODE),a
    ld a,(hl+)
    ld (P_TARGET),a
    ld a,(hl+)
    ld (P_TARGET_HI),a
    ret
