; Menu, in bank MENU_BANK at $4000. Entered at start from the boot hook, or at
; back from a game's title screen when B is pressed. Interrupts are off either way.
;
; Every screen is a whole picture in its own bank: the splash, then one per
; game with that game highlighted. Moving the cursor loads the next picture.
;
; The builder appends: loader_src and launch_src (the loader and launch stub,
; assembled for LOADER and LAUNCH), and games (quarter, mode, entry lo, hi).

SEL = $C000
PAD_HELD = $C001            ; buttons in the low nibble, d-pad in the high nibble

; Cart RAM holds what the boot ROM left, so a game started again after B gets
; the same start as the first time: the registers the boot hook saved, then the
; I/O registers the games may change and don't all set themselves.
STASH = $A000
STASH_REGS = 8

start:
    ld sp,MENU_STACK
    ld a,$0A
    ld ($0000),a            ; cart RAM on
    ld hl,SAVED_REGS
    ld de,STASH
    ld b,STASH_REGS
    call copy
    ld h,d
    ld l,e
    ldh a,($06)             ; TMA
    ld (hl+),a
    ldh a,($07)             ; TAC
    ld (hl+),a
    ldh a,($41)             ; STAT
    ld (hl+),a
    ldh a,($45)             ; LYC
    ld (hl+),a
    ldh a,($4A)             ; WY
    ld (hl+),a
    ldh a,($4B)             ; WX
    ld (hl+),a
    ldh a,($48)             ; OBP0
    ld (hl+),a
    ldh a,($49)             ; OBP1
    ld (hl+),a
    ldh a,($24)             ; NR50
    ld (hl+),a
    ldh a,($25)             ; NR51
    ld (hl+),a
    xor a
    ld ($0000),a            ; cart RAM off
    call copy_loader
    xor a
    ld (SEL),a
    ld (PAD_HELD),a
    ld a,SPLASH_BANK
    call show
wait_start:
    call frame
    and $09                 ; A or START
    jr z,wait_start
    jr menu

; From a game: A = its menu index, quarter 0 mapped, bank MENU_BANK at $4000.
back:
    ld sp,MENU_STACK
    ld (SEL),a
    ld a,$FF                ; ignore whatever is still held from the game
    ld (PAD_HELD),a
    xor a
    ldh ($FF),a             ; IE
    ldh ($07),a             ; TAC: stop the game's timer
    ldh ($26),a             ; sound off, which silences every channel
    ld a,$80
    ldh ($26),a             ; and back on, as the boot ROM leaves it
    ld a,$0A
    ld ($0000),a
    ld hl,STASH
    ld de,SAVED_REGS
    ld b,STASH_REGS
    call copy
    xor a
    ld ($0000),a
    call copy_loader        ; the game has had all of WRAM

menu:
    ld a,(SEL)
    add a,FIRST_GAME_BANK
    call show
menu_loop:
    call frame
    ld b,a
    and $09                 ; A or START launches
    jp nz,launch_game
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

copy_loader:
    ld hl,loader_src
    ld de,LOADER
    ld b,LOADER_LEN
    jr copy

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

; Wait until LY enters VBlank (line 144) from outside it. With the LCD off LY
; stays at 0, so return at once.
vblank:
    ldh a,($40)
    and $80
    ret z
vblank_out:
    ldh a,($44)
    cp 144
    jr z,vblank_out
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

; Fill B bytes from HL with zero.
zero:
    xor a
    ld (hl+),a
    dec b
    jr nz,zero
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
    call zero
    ld hl,$FE00             ; OAM, which a game left behind after B
    ld b,$A0
    call zero
    ld hl,$FF80             ; HRAM below the saved registers, likewise
    ld b,SAVED_REGS - $FF80
    call zero
    ld a,$0A
    ld ($0000),a
    ld hl,STASH + STASH_REGS
    ld a,(hl+)
    ldh ($06),a
    ld a,(hl+)
    ldh ($07),a
    ld a,(hl+)
    ldh ($41),a
    ld a,(hl+)
    ldh ($45),a
    ld a,(hl+)
    ldh ($4A),a
    ld a,(hl+)
    ldh ($4B),a
    ld a,(hl+)
    ldh ($48),a
    ld a,(hl+)
    ldh ($49),a
    ld a,(hl+)
    ldh ($24),a
    ld a,(hl+)
    ldh ($25),a
    xor a
    ld ($0000),a
    ld a,$FC
    ldh ($47),a
    ld a,$91
    ldh ($40),a
    ld hl,launch_src
    ld de,LAUNCH
    ld b,LAUNCH_LEN
    call copy
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
    xor a
    ldh ($FF),a
    ld a,$E1
    ldh ($0F),a
go:
    jp LAUNCH
