; Menu, in bank MENU_BANK at $4000. Entered from the boot hook with
; interrupts off and SP at MENU_STACK.
;
; Every screen is a whole picture in its own bank: the splash, then one per
; game with that game highlighted. Moving the cursor loads the next picture.
;
; The builder defines PROMPT_MAP (the map address of the splash's PRESS START
; row), BLINK_FRAMES and BLINK_CYCLE (twice that). It appends loader_src and
; launch_src (the loader and launch stub, assembled for LOADER and LAUNCH), and
; the cart's set_launch, which patches the stub for the game in SEL, with its
; data (mbc1_launch.asm for the MBC1 collection, chis_launch.asm for ChisFlash).

SEL = $C000
PAD_HELD = $C001            ; buttons in the low nibble, d-pad in the high nibble
PAD_NEW = $C002
BLINK = $C003               ; frames into the PRESS START blink cycle
PROMPT = $C010              ; the splash's PRESS START row, 20 tiles

start:
    ld hl,loader_src
    ld de,LOADER
    ld b,LOADER_LEN
    call copy
    xor a
    ld (SEL),a
    ld (PAD_HELD),a
    ld a,SPLASH_BANK
    call show
    call vblank             ; keep the prompt row, to put back after each blank
    ld hl,PROMPT_MAP
    ld de,PROMPT
    ld b,20
    call copy
    xor a
    ld (BLINK),a
wait_start:
    call frame
    and $09                 ; A or START
    jr nz,menu
    ld hl,BLINK             ; blink PRESS START: shown BLINK_FRAMES, then blank as long
    inc (hl)
    ld a,(hl)
    cp BLINK_FRAMES
    jr z,prompt_off
    cp BLINK_CYCLE
    jr nz,wait_start
    ld (hl),0
    ld hl,PROMPT            ; still in VBlank: frame returns right after it starts
    ld de,PROMPT_MAP
    ld b,20
    call copy
    jr wait_start
prompt_off:
    ld hl,PROMPT_MAP        ; tile 0 of every screen is blank
    ld b,20
    xor a
clear_prompt:
    ld (hl+),a
    dec b
    jr nz,clear_prompt
    jr wait_start

menu:
    ld a,(SEL)
    add a,FIRST_GAME_BANK
    call show
menu_loop:
    call frame
    ld b,a
    and $09                 ; A or START launches
    jr nz,launch_game
    ld a,b
    and $40                 ; up
    jr nz,cursor_up
    ld a,b
    and $80                 ; down
    jr nz,cursor_down
    jr menu_loop
cursor_up:
    ld a,(SEL)
    dec a
    jr cursor_store
cursor_down:
    ld a,(SEL)
    inc a
cursor_store:
    and 3
    ld (SEL),a
    jr menu

; Wait for the next VBlank, read the pad, return newly pressed keys in A
; (bit 0 A, 1 B, 2 SELECT, 3 START, 4 right, 5 left, 6 up, 7 down).
frame:
    call vblank
    ld a,$20                ; d-pad
    ldh ($00),a
    ldh a,($00)
    ldh a,($00)
    cpl
    and $0F
    add a,a                 ; to the high nibble
    add a,a
    add a,a
    add a,a
    ld b,a
    ld a,$10                ; buttons
    ldh ($00),a
    ldh a,($00)
    ldh a,($00)
    ldh a,($00)
    ldh a,($00)
    cpl
    and $0F
    or b
    ld b,a
    ld a,$30
    ldh ($00),a
    ld a,(PAD_HELD)
    cpl
    and b
    ld c,a
    ld a,b
    ld (PAD_HELD),a
    ld a,c
    ret

; Wait until LY enters VBlank (line 144) from outside it.
vblank:
    ldh a,($44)
    cp 144
    jr z,vblank
vblank_in:
    ldh a,($44)
    cp 144
    jr nz,vblank_in
    ret

; Show the screen in bank A: LCD off during VBlank, load, LCD back on.
show:
    push af
    call vblank
    xor a
    ldh ($40),a
    pop af
    call LOADER
    ld a,$E4
    ldh ($47),a
    xor a
    ldh ($42),a
    ldh ($43),a
    ld a,$91                ; LCD on, BG on, tiles at $8000, map at $9800
    ldh ($40),a
    ret

; Copy B bytes from HL to DE.
copy:
    ld a,(hl+)
    ld (de),a
    inc de
    dec b
    jr nz,copy
    ret

; Hand over to the chosen game with the display and interrupt registers as
; the boot ROM leaves them: LCD on with a blank map, BGP $FC, IE 0, IF $E1.
launch_game:
    call vblank
    xor a
    ldh ($40),a
    ld hl,$9800             ; blank the map; tile 0 of every screen is blank
    ld bc,$0400
clear_map:
    xor a
    ld (hl+),a
    dec bc
    ld a,b
    or c
    jr nz,clear_map
    ld hl,$8000             ; and tile 0 itself, in case a screen changes that
    ld b,16
clear_tile0:
    xor a
    ld (hl+),a
    dec b
    jr nz,clear_tile0
    ld a,$FC
    ldh ($47),a
    ld a,$91
    ldh ($40),a
    ld hl,launch_src
    ld de,LAUNCH
    ld b,LAUNCH_LEN
    call copy
    call set_launch         ; patch the stub for the game in SEL
    xor a
    ldh ($FF),a
    ld a,$E1
    ldh ($0F),a
go:
    jp LAUNCH
