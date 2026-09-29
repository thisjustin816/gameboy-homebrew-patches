; Runs in HRAM: quarter 0 and mode 0 bring back DuckTales' bank 0 at $0000,
; then the menu's bank at $4000, and the menu takes over with this game
; highlighted.

    xor a
    ld ($6000),a
    ld ($4000),a
    ld a,MENU_BANK
    ld ($2000),a
    ld a,GAME
    jp BACK
