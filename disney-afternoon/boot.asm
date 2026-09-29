; Boot hook, in DuckTales bank 0 at $0061 (free padding after the joypad vector).
; The header's entry point jumps here instead of to DuckTales' own start.
;
; The boot ROM hands over with the console's identity in AF/BC (A=$01 on DMG,
; $11 on CGB, B bit 0 set on GBA). Save all four pairs on the boot stack at
; $FFF6-$FFFD so the launcher can hand them to whichever game is picked.

entry:
    push hl
    push de
    push bc
    push af                 ; SP is now SAVED_REGS
    ld sp,MENU_STACK
    ld a,MENU_BANK
    ld ($2000),a
    jp $4000
