; Legion of Evil save, title menu and pause menu.
;
; Sections are split by "; ==== org NAME ====" lines (see patch.py). Code in
; bank 2 runs with bank 2 mapped at $4000; it reaches the game's own bank 1
; routines through call_b1.
;
; The game's memory, as found by reading its code and tracing it:
;   $C5C1-$C5CC  store upgrades (six stats, six weapon levels)
;   $C5CF        highest difficulty unlocked
;   $C5DF-$C5E0  banked money
;   $C5DC        set to 1 to open the store (the game-over flow sets it)
;   $C5C0,$C5CD  the store's cursor rows; the flow resets them to 0
; New variables live in upper WRAM ($D000+), which a run never touches.

SRAM        = $A000
S_SIG       = $A000             ; "LOE1"
S_UPG       = $A004             ; 15 bytes of upgrade state
S_UPG_SUM   = $A013
S_RUN_OK    = $A016             ; $5A while a run snapshot is stored
S_RUN       = $A100
; The run snapshot, in order: SP, nine IO registers and IE, HRAM, the stack
; page, game WRAM, both tile maps, then a 16-bit sum and the build id.
R_SP        = S_RUN
R_IO        = S_RUN + 2
R_HRAM      = S_RUN + 12
R_STACK     = S_RUN + 139
R_WRAM      = S_RUN + 395
R_MAP       = S_RUN + 2987
R_SUM       = S_RUN + 5035
R_BUILD     = S_RUN + 5037
WRAM_LEN    = $0A20             ; $C000-$CA1F: everything a run changes

V_BASE      = $D000
V_MAGIC1    = $D000             ; $A5,$5A once boot_hook has cleared this page
V_MAGIC2    = $D001
V_FLAGS     = $D002
V_JOY       = $D003
V_PREV      = $D004
V_MPREV     = $D005
V_MSEL      = $D006
V_MCNT      = $D007
V_MROW      = $D008
V_MCOL      = $D009
V_MDRAW     = $D00A
V_LCDC      = $D00B
V_WY        = $D00C
V_WX        = $D00D
V_SAVESP    = $D00E             ; two bytes
V_MHINT     = $D019             ; 1 while the menu shows the theme line
V_MREDRAW   = $D01A             ; the theme changed: redraw its name
WINBAK      = $D100             ; 1 KB copy of the window map
OAMBUF      = $DA00             ; the sprite table the VBlank DMA copies from
V_ROT       = $D010             ; which enemy pair leads this frame
V_CGB       = $D011             ; 1 on a Game Boy Color
V_PAL       = $D012             ; the chosen color theme, 0-7
PAL_DIRTY   = $D013             ; set when PALBUF holds colors the VBlank hook should load
C_BGP       = $D014             ; the shades and theme PALBUF was built from
C_OBP0      = $D015
C_OBP1      = $D016
C_PAL       = $D017
C_VALID     = $D018
PALBUF      = $D200             ; BG palette 0, then OBJ palettes 0 and 1: 24 bytes
S_PAL       = $A014             ; the theme, and its check byte
SH_SCX      = $94               ; HRAM: the game's scroll and palette writes land here,
SH_SCY      = $95               ; and the VBlank hook copies them to the hardware
SH_BGP      = $96
SH_OBP0     = $97
SH_OBP1     = $98
HRAM_CODE   = $FF99             ; the VBlank hook

F_SAVE      = $01               ; an upgrade save exists
F_RUN       = $02               ; a run snapshot exists
F_PEND_STORE = $04              ; open the store when the run loop starts
F_PEND_CONT  = $08              ; restore the snapshot when the run loop starts

LCDC        = $40
LY          = $44
WY          = $4A
WX          = $4B

WIN_MAP     = $9C00
TILE_BLANK  = $7F
TILE_CURSOR = $7E

; ==== org stub_a ====
; Runs HL in the game's bank 1 from bank 2 code, then returns to bank 2. A and
; the flags come back from the routine.
call_b1:    ld a,1
            ld ($2000),a
            call $0020              ; rst $20 is the game's "jp hl"
            push af
            ld a,2
            ld ($2000),a
            pop af
            ret
; The game's call to its WRAM-defaults copy, then the save load.
t_boot:     call $7FEB
            ld a,2
            ld ($2000),a
            call boot_hook
            ld a,1
            ld ($2000),a
            ret
; The game's joypad read, then the hooks that watch it. E carries the buttons
; in and out.
t_joy:      call $7BB2
            push af
            ld a,2
            ld ($2000),a
            pop af
            call joy_hook
            push af
            ld a,1
            ld ($2000),a
            pop af
            ret

; ==== org stub_b ====
; After the store's buy routine or the game-over screen, write the upgrades.
t_buy:      call $22CF
            jr t_sv
t_over:     call $1975
t_sv:       push af
            ld a,2
            ld ($2000),a
            call save_hook
            ld a,1
            ld ($2000),a
            pop af
            ret
; The game's frame wait starts here; the hooks run before it.
t_wait:     push af
            push bc
            push de
            push hl
            ld a,2
            ld ($2000),a
            call wait_hook
            ld a,1
            ld ($2000),a
            pop hl
            pop de
            pop bc
            pop af
            ldh a,(LCDC)
            and $80
            ret

; ==== org stub_c ====
; Bank 2 is mapped while the reset runs, so switch before the game's start.
t_reset:    ld a,1
            ld ($2000),a
            jp $0150

; ==== org bank2 ====
; ---------------------------------------------------------------- helpers
sram_on:    ld a,$0A
            ld ($0000),a
            ret
sram_off:   xor a
            ld ($0000),a
            ret

; A = sum of B bytes at HL, xor $A5.
chk_sum:    xor a
cs_loop:    add a,(hl)
            inc hl
            dec b
            jr nz,cs_loop
            xor $A5
            ret

; Copy BC bytes from HL to DE.
cpy:        ld a,(hl+)
            ld (de),a
            inc de
            dec bc
            ld a,b
            or c
            jr nz,cpy
            ret

; DE = 16-bit sum of the BC bytes at HL.
sum16:      ld de,0
s16_loop:   ld a,(hl+)
            add a,e
            ld e,a
            jr nc,s16_nc
            inc d
s16_nc:     dec bc
            ld a,b
            or c
            jr nz,s16_loop
            ret

wait_vbl:   ld hl,$7AF8
            jp call_b1
music_tick: ld hl,$70F3
            jp call_b1
read_joy:   ld hl,$7BB2
            jp call_b1

; Z if the signature at S_SIG is "LOE1".
sig_check:  ld hl,S_SIG
            ld a,(hl+)
            cp $4C
            ret nz
            ld a,(hl+)
            cp $4F
            ret nz
            ld a,(hl+)
            cp $45
            ret nz
            ld a,(hl)
            cp $31
            ret

; Copies the upgrade state between WRAM and the 15-byte block at DE. C bit 0:
; 1 stores to DE, 0 loads from DE.
; The table is (length, WRAM address); length 0 ends it.
upg_tab:    db 12
            dw $C5C1
            db 1
            dw $C5CF
            db 2
            dw $C5DF
            db 0
upg_def:    db $14,$0E,$00,$01,$14,$14,$01,$00,$00,$00,$00,$00      ; the game's defaults
            db $00
            db $00,$00
upg_xfer:   ld hl,upg_tab
ux_next:    ld a,(hl+)
            or a
            ret z
            ld b,a
            ld a,(hl+)
            push hl
            ld h,(hl)
            ld l,a
ux_byte:    bit 0,c
            jr z,ux_ld
            ld a,(hl+)
            ld (de),a
            inc de
            jr ux_nb
ux_ld:      ld a,(de)
            inc de
            ld (hl+),a
ux_nb:      dec b
            jr nz,ux_byte
            pop hl
            inc hl
            jr ux_next

; ---------------------------------------------------------------- boot
boot_hook:  push af
            push bc
            push de
            push hl
            xor a
            ld hl,V_BASE
            ld b,0
bh_clr:     ld (hl+),a
            dec b
            jr nz,bh_clr
            call sram_on
            ld a,(S_PAL)
            ld b,a
            xor $5A
            ld hl,S_PAL + 1
            cp (hl)
            jr nz,bh_nopal
            ld a,b
            cp 8
            jr nc,bh_nopal
            ld (V_PAL),a
bh_nopal:   call sig_check
            jr nz,bh_done
            ld hl,S_UPG
            ld b,15
            call chk_sum
            ld hl,S_UPG_SUM
            cp (hl)
            jr nz,bh_done
            ld c,0
            ld de,S_UPG
            call upg_xfer
            ld a,F_SAVE
            ld (V_FLAGS),a
            ld a,(S_RUN_OK)
            cp $5A
            jr nz,bh_done
            ld hl,S_RUN
            ld bc,R_SUM - S_RUN
            call sum16
            ld hl,R_SUM
            ld a,(hl+)
            cp e
            jr nz,bh_done
            ld a,(hl+)
            cp d
            jr nz,bh_done
            ld a,(hl+)
            cp BUILD_LO
            jr nz,bh_done
            ld a,(hl)
            cp BUILD_HI
            jr nz,bh_done
            ld a,F_SAVE + F_RUN
            ld (V_FLAGS),a
bh_done:    call sram_off
            call cgb_setup
            ld a,$A5
            ld (V_MAGIC1),a
            ld a,$5A
            ld (V_MAGIC2),a
            pop hl
            pop de
            pop bc
            pop af
            ret

; ---------------------------------------------------------------- hardware
; On a Game Boy Color the boot ROM leaves A = $11, which the game keeps at $C0A0.
; Switch to double speed, clear the tile attribute maps, slow the OAM DMA wait
; to match, and install the VBlank hook. Every console gets the hook.
cgb_setup:  xor a
            ld (V_CGB),a
            ld hl,hram_src
            ld de,HRAM_CODE
            ld bc,hram_len
            call cpy
            ld a,($C0A0)
            cp $11
            ret nz
            ld a,1
            ld (V_CGB),a
            ldh a,($4D)
            bit 7,a
            jr nz,cs_fast           ; already in double speed after a soft reset
            ldh a,($FF)
            ld b,a
            xor a
            ldh ($FF),a
            ldh ($0F),a
            ld a,$30
            ldh ($00),a
            ld a,1
            ldh ($4D),a
            stop
            ld a,b
            ldh ($FF),a
cs_fast:    ld a,$50                ; the DMA wait is counted in CPU cycles, which are
            ldh ($87),a             ; half as long now: $28 became $50
cs_line:    ldh a,(LY)              ; interrupts are still off here, so poll for VBlank
            cp $90
            jr nz,cs_line
            ldh a,(LCDC)
            ld (V_LCDC),a
            res 7,a
            ldh (LCDC),a
            ld a,1
            ldh ($4F),a             ; VRAM bank 1 holds the tile attributes
            ld hl,$9800
            ld bc,$0800
cs_clr:     xor a
            ld (hl+),a
            dec bc
            ld a,b
            or c
            jr nz,cs_clr
            ldh ($4F),a
            ld a,(V_LCDC)
            ldh (LCDC),a
            ret

; ---------------------------------------------------------------- save
; True (Z clear) once boot_hook has cleared the variable page.
ready:      ld a,(V_MAGIC1)
            cp $A5
            ret nz
            ld a,(V_MAGIC2)
            cp $5A
            ret

save_hook:  push af
            push bc
            push de
            push hl
            call ready
            jr nz,sv_out
            call sram_on
            ld hl,S_SIG
            ld a,$4C
            ld (hl+),a
            ld a,$4F
            ld (hl+),a
            ld a,$45
            ld (hl+),a
            ld a,$31
            ld (hl),a
            ld c,1
            ld de,S_UPG
            call upg_xfer
            ld hl,S_UPG
            ld b,15
            call chk_sum
            ld (S_UPG_SUM),a
            call sram_off
            ld a,(V_FLAGS)
            or F_SAVE
            ld (V_FLAGS),a
sv_out:     pop hl
            pop de
            pop bc
            pop af
            ret

; Write the chosen theme and its check byte.
pal_save:   call sram_on
            ld a,(V_PAL)
            ld (S_PAL),a
            xor $5A
            ld (S_PAL + 1),a
            jp sram_off

; Forget the save: clear SRAM's signature and the run snapshot, and put the
; game's default upgrades back.
erase_save: call sram_on
            xor a
            ld hl,S_SIG
            ld b,32
es_clr:     ld (hl+),a
            dec b
            jr nz,es_clr
            call sram_off
            call pal_save           ; the color theme is not part of the save
            xor a
            ld (V_FLAGS),a
            ld c,0
            ld de,upg_def
            jp upg_xfer

; ---------------------------------------------------------------- theme
; SELECT anywhere cycles the color theme (color hardware only) and saves it.
theme_next: ld a,(V_CGB)
            or a
            ret z
            ld a,(V_PAL)
            inc a
            and 7
            ld (V_PAL),a
            jp pal_save

; Six letters, one theme each.
theme_names: db "GREEN GRAY  POCKETAMBER ICE   BLOOD PURPLESEPIA "

; The current theme's name at column 10, row 15 of the window map.
theme_name_draw:
            ld b,10
            ld c,15
            call win_addr
            ld d,h
            ld e,l
            ld a,(V_PAL)
            and 7
            ld l,a
            add a,a
            add a,l
            add a,a                 ; theme * 6
            ld c,a
            ld b,0
            ld hl,theme_names
            add hl,bc
            ld b,6
tn_loop:    ld a,(hl+)
            push hl
            call tile_of
            ld (de),a
            inc de
            pop hl
            dec b
            jr nz,tn_loop
            ret

; Redraw the name if SELECT changed it (called right after a VBlank).
mr_theme:   ld a,(V_MREDRAW)
            or a
            ret z
            xor a
            ld (V_MREDRAW),a
            ld a,(V_MHINT)
            or a
            ret z
            jp theme_name_draw

; ---------------------------------------------------------------- overlay
; A full-screen window over whatever is showing. ov_open backs up the window's
; tile map and leaves the LCD off; draw the screen, then ov_show. ov_reset
; starts another screen the same way. ov_close puts the window map back.
ov_open:    call wait_vbl
            xor a
            ld (V_MHINT),a
            ldh a,(LCDC)
            ld (V_LCDC),a
            res 7,a
            ldh (LCDC),a
            ldh a,(WY)
            ld (V_WY),a
            ldh a,(WX)
            ld (V_WX),a
            ld hl,WIN_MAP
            ld de,WINBAK
            ld bc,$0400
ovo_copy:   ld a,(hl+)
            ld (de),a
            inc de
            dec bc
            ld a,b
            or c
            jr nz,ovo_copy
            jp ov_clear

ov_reset:   call wait_vbl
            ldh a,(LCDC)
            res 7,a
            ldh (LCDC),a

ov_clear:   ld hl,WIN_MAP
            ld bc,$0400
ovc_loop:   ld a,TILE_BLANK
            ld (hl+),a
            dec bc
            ld a,b
            or c
            jr nz,ovc_loop
            ret

ov_show:    xor a
            ldh (WY),a
            ld a,7
            ldh (WX),a
            ld a,(V_LCDC)
            or $E0                  ; LCD on, window on, window map $9C00
            res 1,a                 ; sprites off
            ldh (LCDC),a
            ret

ov_close:   call wait_vbl
            ldh a,(LCDC)
            res 7,a
            ldh (LCDC),a
            ld hl,WINBAK
            ld de,WIN_MAP
            ld bc,$0400
ovx_copy:   ld a,(hl+)
            ld (de),a
            inc de
            dec bc
            ld a,b
            or c
            jr nz,ovx_copy
            ld a,(V_WY)
            ldh (WY),a
            ld a,(V_WX)
            ldh (WX),a
            ld a,(V_LCDC)
            or $80
            ldh (LCDC),a
            ret

; HL = tile map address of column B, row C in the window map.
win_addr:   ld l,c
            ld h,0
            add hl,hl
            add hl,hl
            add hl,hl
            add hl,hl
            add hl,hl
            ld c,b
            ld b,0
            add hl,bc
            ld bc,WIN_MAP
            add hl,bc
            ret

; ASCII in A -> the game's font tile.
tile_of:    cp $20
            jr nz,to_1
            ld a,TILE_BLANK
            ret
to_1:       cp $3A
            jr nz,to_2
            ld a,$79
            ret
to_2:       cp $3E
            jr nz,to_3
            ld a,TILE_CURSOR
            ret
to_3:       cp $2D
            jr nz,to_4
            ld a,$7C
            ret
to_4:       cp $2B
            jr nz,to_5
            ld a,$7D
            ret
to_5:       cp $30
            jr nz,to_6
            ld a,$6F
            ret
to_6:       cp $41
            jr nc,to_letter
            add a,$3F               ; 1-9
            ret
to_letter:  add a,$14
            ret

; HL -> column, row, then text ending in 0. The window map is written while
; the LCD is on, so callers use this right after wait_vbl or with the LCD off.
ov_text:    ld a,(hl+)
            ld b,a
            ld a,(hl+)
            ld c,a
            push hl
            call win_addr
            ld d,h
            ld e,l
            pop hl
ot_loop:    ld a,(hl+)
            or a
            ret z
            push hl
            call tile_of
            ld (de),a
            inc de
            pop hl
            jr ot_loop

; Menu with B items, the first on row C, cursor in column D; items step two
; rows. A = the item chosen, or $FF for B.
menu_run:   ld a,b
            ld (V_MCNT),a
            ld a,c
            ld (V_MROW),a
            ld a,d
            ld (V_MCOL),a
            xor a
            ld (V_MSEL),a
            ld a,$FF
            ld (V_MDRAW),a
            ld (V_MPREV),a
mr_loop:    call wait_vbl
            call mr_theme
            call mr_cursor
            call music_tick
            call read_joy
            ld a,(V_MPREV)
            cpl
            and e
            ld b,a
            ld a,e
            ld (V_MPREV),a
            bit 6,b
            jr z,mr_nosel
            push bc
            call theme_next
            ld a,1
            ld (V_MREDRAW),a
            pop bc
mr_nosel:   bit 3,b
            jr z,mr_up
            ld a,(V_MSEL)
            inc a
            ld hl,V_MCNT
            cp (hl)
            jr c,mr_dn_ok
            xor a
mr_dn_ok:   ld (V_MSEL),a
mr_up:      bit 2,b
            jr z,mr_pick
            ld a,(V_MSEL)
            or a
            jr nz,mr_up_ok
            ld a,(V_MCNT)
mr_up_ok:   dec a
            ld (V_MSEL),a
mr_pick:    bit 4,b
            jr nz,mr_done
            bit 7,b
            jr nz,mr_done
            bit 5,b
            jr z,mr_loop
            ld a,$FF
            ret
mr_done:    ld a,(V_MSEL)
            ret

; Draw the cursor on the chosen row and blank it on the row it left.
mr_cursor:  ld a,(V_MDRAW)
            ld hl,V_MSEL
            cp (hl)
            ret z
            cp $FF
            jr z,mc_draw
            call mc_row
            ld (hl),TILE_BLANK
mc_draw:    ld a,(V_MSEL)
            ld (V_MDRAW),a
            call mc_row
            ld (hl),TILE_CURSOR
            ret
; HL = map address of the cursor cell for row index A.
mc_row:     add a,a
            ld hl,V_MROW
            add a,(hl)
            ld c,a
            ld a,(V_MCOL)
            ld b,a
            jp win_addr

; ---------------------------------------------------------------- title
str_title:  db 3,3,"LEGION OF EVIL",0
str_cont:   db 4,7,"CONTINUE",0
str_new_a:  db 4,7,"NEW RUN",0
str_new_b:  db 4,9,"NEW RUN",0
str_era_a:  db 4,9,"ERASE SAVE",0
str_era_b:  db 4,11,"ERASE SAVE",0
str_sure1:  db 4,6,"ERASE SAVE",0
str_sure2:  db 4,8,"ARE YOU SURE",0
str_no:     db 6,11,"NO",0
str_yes:    db 6,13,"YES",0

; Buttons in V_JOY (bit 7 start, 6 select, 5 b, 4 a, 3 down, 2 up).
title_logic: ld a,(V_JOY)
            ld b,a
            ld a,(V_PREV)
            cpl
            and b
            ld c,a                  ; C = pressed this frame
            ld a,b
            ld (V_PREV),a
            bit 6,c
            jr z,tl_keep
            push bc
            call theme_next
            pop bc
tl_keep:    ld a,(V_FLAGS)
            and F_SAVE + F_RUN
            ret z                   ; no save: the game starts as it always did
            ld a,b
            and $7F                 ; START only counts from the menu
            ld (V_JOY),a
            bit 7,c
            ret z
            call title_menu
            ret

; The menu over the title. Sets START in V_JOY when a run should begin.
title_menu: call ov_open
tm_draw:    ld hl,str_title
            call ov_text
            ld a,(V_FLAGS)
            and F_RUN
            jr z,tm_no_run
            ld hl,str_cont
            call ov_text
            ld hl,str_new_b
            call ov_text
            ld hl,str_era_b
            call ov_text
            ld b,3
            jr tm_go
tm_no_run:  ld hl,str_new_a
            call ov_text
            ld hl,str_era_a
            call ov_text
            ld b,2
tm_go:      call ov_show
            ld c,7
            ld d,2
            call menu_run
            cp $FF
            jr z,tm_leave
            ld b,a
            ld a,(V_FLAGS)
            and F_RUN
            jr nz,tm_with
            inc b                   ; without a run the list starts at NEW RUN
tm_with:    ld a,b
            or a
            jr z,tm_continue
            dec a
            jr z,tm_new
            call confirm_erase
            or a
            jr nz,tm_leave          ; erased: back to the title
            call ov_reset
            jr tm_draw
tm_leave:   call ov_close
            ret
tm_continue: ld a,(V_FLAGS)
            or F_PEND_CONT
            jr tm_go_run
tm_new:     ld a,(V_FLAGS)
            or F_PEND_STORE
tm_go_run:  ld (V_FLAGS),a
            call ov_close
            ld a,(V_JOY)
            or $80
            ld (V_JOY),a
            ret

; A = 1 if the save was erased.
confirm_erase:
            call ov_reset
            ld hl,str_sure1
            call ov_text
            ld hl,str_sure2
            call ov_text
            ld hl,str_no
            call ov_text
            ld hl,str_yes
            call ov_text
            call ov_show
            ld b,2
            ld c,11
            ld d,4
            call menu_run
            cp 1
            jr nz,ce_no
            call erase_save
            ld a,1
            ret
ce_no:      xor a
            ret

; ---------------------------------------------------------------- pause
str_paused: db 7,3,"PAUSED",0
str_resume: db 4,7,"RESUME",0
str_squit:  db 4,9,"SAVE AND QUIT",0
str_theme:  db 2,15,"SELECT: ",0

; START during a live run. The stock game pauses on START; this replaces that
; with a menu, so V_JOY loses the START bit.
run_logic:  ld a,(V_JOY)
            ld b,a
            ld a,(V_PREV)
            cpl
            and b
            ld c,a                  ; C = pressed this frame
            ld a,b
            ld (V_PREV),a
            bit 6,c
            jr z,rl_nosel
            push bc
            call theme_next
            pop bc
rl_nosel:   bit 7,c
            ret z
            ld a,b
            and $7F
            ld (V_JOY),a
            ld a,($C5B5)            ; a menu or the store is showing
            ld b,a
            ld a,($C5B6)            ; the stock pause
            or b
            ret nz
            ld hl,$C5D9             ; the screen-change flags
            ld b,6
rl_flags:   ld a,(hl+)
            or a
            ret nz
            dec b
            jr nz,rl_flags
            jp pause_menu

pause_menu: call ov_open
pm_draw:    ld hl,str_paused
            call ov_text
            ld hl,str_resume
            call ov_text
            ld hl,str_squit
            call ov_text
            ld a,(V_CGB)
            ld (V_MHINT),a          ; the theme line only means something on color hardware
            or a
            jr z,pm_nohint
            ld hl,str_theme
            call ov_text
            call theme_name_draw
pm_nohint:  call ov_show
            ld b,2
            ld c,7
            ld d,2
            call menu_run
            cp 1
            jr z,pm_save
            jp ov_close
pm_save:    call ov_close
            call suspend
pm_saved:   or a
            ret z                   ; 0: the snapshot was just restored
            jp reset_game

; Saves the run, like setjmp: returns 1 after writing the snapshot, and
; returns 0 again when restore_run loads it back.
suspend:    di
            ld hl,sp+0
            ld a,l
            ld (V_SAVESP),a
            ld a,h
            ld (V_SAVESP + 1),a
            cp $DF                  ; the stack must sit inside the saved page
            jr nc,su_ok
            ei
            ld a,1                  ; nothing written; carry on to the reset
            ret
su_ok:      call save_hook          ; a run needs the upgrade save beside it
            call sram_on
            xor a
            ld (S_RUN_OK),a
            ld hl,V_SAVESP
            ld de,R_SP
            ld bc,2
            call cpy
            ld de,R_IO
            ldh a,(LCDC)
            ld (de),a
            inc de
            ldh a,($42)
            ld (de),a
            inc de
            ldh a,($43)
            ld (de),a
            inc de
            ldh a,($45)
            ld (de),a
            inc de
            ldh a,($47)
            ld (de),a
            inc de
            ldh a,($48)
            ld (de),a
            inc de
            ldh a,($49)
            ld (de),a
            inc de
            ldh a,(WY)
            ld (de),a
            inc de
            ldh a,(WX)
            ld (de),a
            inc de
            ldh a,($FF)
            ld (de),a
            ld hl,$FF80
            ld de,R_HRAM
            ld bc,127
            call cpy
            ld hl,$DF00
            ld de,R_STACK
            ld bc,$0100
            call cpy
            ld hl,$C000
            ld de,R_WRAM
            ld bc,WRAM_LEN
            call cpy
            ei                      ; the frame wait needs the VBlank interrupt
            call wait_vbl
            di
            ldh a,(LCDC)
            res 7,a
            ldh (LCDC),a
            ld hl,$9800
            ld de,R_MAP
            ld bc,$0800
            call cpy
            ld hl,S_RUN
            ld bc,R_SUM - S_RUN
            call sum16
            ld hl,R_SUM
            ld a,e
            ld (hl+),a
            ld a,d
            ld (hl+),a
            ld a,BUILD_LO
            ld (hl+),a
            ld a,BUILD_HI
            ld (hl),a
            ld a,$5A
            ld (S_RUN_OK),a
            call sram_off
            ld a,1
            ret

; Loads the snapshot back and returns 0 into suspend's caller. Called from
; wait_hook on the first frame of a new run, where VRAM holds the same tiles.
restore_run:
            call sram_on
            xor a
            ld (S_RUN_OK),a         ; continuing uses the snapshot up
            ld a,(V_FLAGS)
            and $F5                 ; drop F_RUN and F_PEND_CONT
            ld (V_FLAGS),a
            xor a
            ld (V_JOY),a
            di
            ld sp,$DEFE             ; a scratch stack below the page being restored
rr_wait:    ldh a,(LY)
            cp $90
            jr nz,rr_wait
            ldh a,(LCDC)
            res 7,a
            ldh (LCDC),a
            ld hl,R_MAP
            ld de,$9800
            ld bc,$0800
            call cpy
            ld hl,R_WRAM
            ld de,$C000
            ld bc,WRAM_LEN
            call cpy
            ld hl,R_STACK
            ld de,$DF00
            ld bc,$0100
            call cpy
            ld hl,R_HRAM
            ld de,$FF80
            ld bc,127
            call cpy
            ld hl,R_IO + 1
            ld a,(hl+)
            ldh ($42),a
            ld a,(hl+)
            ldh ($43),a
            ld a,(hl+)
            ldh ($45),a
            ld a,(hl+)
            ldh ($47),a
            ld a,(hl+)
            ldh ($48),a
            ld a,(hl+)
            ldh ($49),a
            ld a,(hl+)
            ldh (WY),a
            ld a,(hl+)
            ldh (WX),a
            ld a,(hl)
            ldh ($FF),a
            ld a,(R_IO)
            ldh (LCDC),a
            call oam_build
            ld hl,R_SP
            ld a,(hl+)
            ld h,(hl)
            ld l,a
            ld sp,hl
            call sram_off
            xor a
            ei
            ret

; Start the game over, as if the console had just been switched on.
reset_game: di
            xor a
            ldh ($0F),a
            ldh ($FF),a
            ldh ($26),a
            jp t_reset

; ---------------------------------------------------------------- sprites
; The hardware draws the first ten sprites on a scanline, in table order, and
; the game fills the table enemies first, the player last, so a crowd drops the
; player. On a Game Boy Color each frame this builds the table the DMA reads in a
; better order:
; the player's four sprites, the weapon's four, then the enemies' sixteen pairs
; starting one pair later each frame, so what a crowded line drops changes.
;   $C000-$C07F enemies (pairs of slots)   $C080 weapon   $C090 player
; Two sprites. The attribute bytes also get bit 0 set from bit 4, which picks
; the color palette on a Game Boy Color the way bit 4 picks OBP1 on the old
; one; the old hardware ignores the extra bit.
copy8:      ld a,(de)
            inc e
            ld (hl+),a
            ld a,(de)
            inc e
            ld (hl+),a
            ld a,(de)
            inc e
            ld (hl+),a
            ld a,(de)
            inc e
            ld b,a
            swap a
            and 1
            or b
            ld (hl+),a
            ld a,(de)
            inc e
            ld (hl+),a
            ld a,(de)
            inc e
            ld (hl+),a
            ld a,(de)
            inc e
            ld (hl+),a
            ld a,(de)
            inc e
            ld b,a
            swap a
            and 1
            or b
            ld (hl+),a
            ret

oam_build:  ld a,(V_CGB)            ; only with double speed: on an original Game Boy the
            or a                    ; copy costs more frame time than the stock game has
            ret z                   ; to spare, so the table stays as the game builds it
            ld hl,OAMBUF
            ld de,$C090
            call copy8
            call copy8
            ld de,$C080
            call copy8
            call copy8
            ld c,16
ob_loop:    ld a,(V_ROT)
            add a,16
            sub c
            and $0F
            swap a
            rrca                    ; pair * 8
            ld e,a
            ld d,$C0
            call copy8
            dec c
            jr nz,ob_loop
            ld a,(V_ROT)
            inc a
            and $0F
            ld (V_ROT),a
            ld a,$DA                ; OAMBUF >> 8
            ldh ($92),a             ; the game's OAM DMA reads its source page from HRAM
            ret

; ---------------------------------------------------------------- color
; The game sets its three gray palettes once, at the title. On a Game Boy Color
; those registers do nothing, so the shades it writes (into the HRAM shadows)
; are turned into colors from the chosen theme and handed to the VBlank hook.
pal_check:  ld a,(V_CGB)
            or a
            ret z
            ldh a,(SH_BGP)
            ld hl,C_BGP
            cp (hl)
            jr nz,pc_build
            ldh a,(SH_OBP0)
            inc hl
            cp (hl)
            jr nz,pc_build
            ldh a,(SH_OBP1)
            inc hl
            cp (hl)
            jr nz,pc_build
            ld a,(V_PAL)
            inc hl
            cp (hl)
            jr nz,pc_build
            inc hl
            ld a,(hl)
            or a
            ret nz
pc_build:   ldh a,(SH_BGP)
            ld (C_BGP),a
            ldh a,(SH_OBP0)
            ld (C_OBP0),a
            ldh a,(SH_OBP1)
            ld (C_OBP1),a
            ld a,(V_PAL)
            ld (C_PAL),a
            ld a,1
            ld (C_VALID),a
            ld hl,PALBUF
            ld a,(C_BGP)
            call pal_four
            ld a,(C_OBP0)
            call pal_four
            ld a,(C_OBP1)
            call pal_four
            ld a,1
            ld (PAL_DIRTY),a
            ret

; Four colors of the theme, picked by the four 2-bit shades in A, at HL.
pal_four:   ld b,4
            ld c,a
pf_loop:    ld a,c
            and 3
            add a,a                 ; 2 bytes a color
            ld e,a
            ld a,(V_PAL)
            and 7
            swap a
            rrca                    ; theme * 8
            add a,e
            ld e,a
            ld d,0
            push hl
            ld hl,themes
            add hl,de
            ld a,(hl+)
            ld d,(hl)
            pop hl
            ld (hl+),a
            ld a,d
            ld (hl+),a
            srl c
            srl c
            dec b
            jr nz,pf_loop
            ret

themes:
            dw $6BFC,$3B11,$29A6,$1061            ; GREEN
            dw $7FFF,$56B5,$2D6B,$0421            ; GRAY
            dw $5338,$3651,$1D49,$0C63            ; POCKET
            dw $53BF,$1ABD,$0951,$0044            ; AMBER
            dw $7FFD,$7732,$59C8,$1C61            ; ICE
            dw $73BF,$3A1D,$18B2,$0403            ; BLOOD
            dw $7FBE,$7256,$4D0C,$1823            ; PURPLE
            dw $6FDF,$3EDA,$1D6F,$0444            ; SEPIA

; ---------------------------------------------------------------- frame hooks
; E = buttons from the game's joypad read. The caller's return address shows
; which loop asked: $57C8 is the title, $58BE the run.
joy_hook:   push bc
            push de
            push hl
            call ready
            jr nz,jh_done
            ld a,e
            ld (V_JOY),a
            ld hl,sp+8
            ld a,(hl+)
            ld h,(hl)
            ld l,a
            ld a,h
            cp $57
            jr nz,jh_run
            ld a,l
            cp $C8
            jr nz,jh_done
            call title_logic
            jr jh_out
jh_run:     cp $58
            jr nz,jh_done
            ld a,l
            cp $BE
            jr nz,jh_done
            call run_logic
jh_ran:
jh_out:     pop hl
            pop de
            pop bc
            ld a,(V_JOY)
            ld e,a
            ret
jh_done:    pop hl
            pop de
            pop bc
            ld a,e
            ret

; Runs before the game waits for VBlank. The caller's return address is at
; SP+12 ($58B8 is the run loop's wait).
wait_hook:  call ready
            ret nz
            call pal_check
            call oam_build
            ld hl,sp+12
            ld a,(hl+)
            ld h,(hl)
            ld l,a
            ld a,h
            cp $58
            ret nz
            ld a,l
            cp $B8
            ret nz
            ld a,(V_FLAGS)
            bit 2,a
            jr z,wh_cont
            res 2,a
            ld (V_FLAGS),a
            ld a,1
            ld ($C5DC),a            ; open the store, as the game-over flow does
            xor a
            ld ($C5C0),a
            ld ($C5CD),a
wh_cont:    ld a,(V_FLAGS)
            bit 3,a
            ret z
            jp restore_run

; ==== org hram ====
; The VBlank hook, copied to HRAM at boot. The game's VBlank handler called the
; OAM DMA routine; it calls this instead, which runs that routine and then
; applies what the game wrote to its scroll and palette shadows.
isr_ext:    call $FF80
            ldh a,(SH_SCX)
            ldh ($43),a
            ldh a,(SH_SCY)
            ldh ($42),a
            ldh a,(SH_BGP)
            ldh ($47),a
            ldh a,(SH_OBP0)
            ldh ($48),a
            ldh a,(SH_OBP1)
            ldh ($49),a
            ld a,(PAL_DIRTY)
            or a
            ret z
            xor a
            ld (PAL_DIRTY),a
            ld a,$80
            ldh ($68),a
            ld hl,PALBUF
            ld b,8
isr_bg:     ld a,(hl+)
            ldh ($69),a
            dec b
            jr nz,isr_bg
            ld a,$80
            ldh ($6A),a
            ld b,16
isr_ob:     ld a,(hl+)
            ldh ($6B),a
            dec b
            jr nz,isr_ob
            ret
