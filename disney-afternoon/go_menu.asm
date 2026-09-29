; Leave the game for the menu. The stub that remaps the ROM runs from HRAM,
; since it moves $0000 out from under itself; it overwrites the game's own HRAM
; routine, so interrupts go off first. The builder appends menu_stub.

go_menu:
    di
    ld hl,menu_stub
    ld de,$FF80
    ld b,MENU_STUB_LEN
copy_stub:
    ld a,(hl+)
    ld (de),a
    inc de
    dec b
    jr nz,copy_stub
    jp $FF80
