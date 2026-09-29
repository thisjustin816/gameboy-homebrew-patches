; Screen loader, copied to WRAM because it switches the $4000 bank it reads from.
; In: A = bank holding a screen. The LCD must be off.
; A screen is: word tile_bytes, tile_bytes of 2bpp tiles (loaded from $8000),
; then an 18x20 tile map (loaded into the top-left of $9800).

load_screen:
    ld ($2000),a
    ld hl,$4000
    ld a,(hl+)
    ld c,a
    ld a,(hl+)
    ld b,a
    ld de,$8000
copy_tiles:
    ld a,(hl+)
    ld (de),a
    inc de
    dec bc
    ld a,b
    or c
    jr nz,copy_tiles
    ld de,$9800
    ld b,18
map_row:
    ld c,20
map_col:
    ld a,(hl+)
    ld (de),a
    inc de
    dec c
    jr nz,map_col
    push hl
    ld hl,12                ; skip the 12 off-screen columns of the 32-wide map
    add hl,de
    ld d,h
    ld e,l
    pop hl
    dec b
    jr nz,map_row
    ld a,MENU_BANK
    ld ($2000),a
    ret
