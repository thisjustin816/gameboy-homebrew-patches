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
WINBAK      = $D100             ; 1 KB copy of the window map, $D100-$D4FF
PAGEBUF     = $D500             ; the menu page being drawn: 20 x 18 tiles
SHOWN       = $D700             ; what the window map holds now (PAGEBUF + $200)
OAMBUF      = $DA00             ; the sprite table the VBlank DMA copies from
V_ROT       = $D010             ; which enemy pair leads this frame
V_CGB       = $D011             ; 1 on a Game Boy Color
V_PAL       = $D012             ; the chosen color theme, 0-15
PAL_DIRTY   = $D013             ; set when PALBUF holds colors the VBlank hook should load
C_BGP       = $D014             ; the shades and theme PALBUF was built from
C_OBP0      = $D015
C_OBP1      = $D016
C_PAL       = $D017
C_VALID     = $D018
PALBUF      = $D020             ; BG palette 0, then OBJ palettes 0 and 1: 24 bytes
V_KEEP      = $D038             ; three bytes: the game's shades while the screen is dark
V_DARK      = $D03B             ; 1 from CONTINUE or NEW RUN, 2 once the store is asked for
V_BOOT      = $D03C             ; two bytes: $C0A0-$C0A1 kept over a restore
S_PAL       = $A014             ; the theme, and its check byte
THEME_COUNT = 16
V_TPTR      = $D01B             ; two bytes: the theme's palettes
V_HIT       = $D01D             ; frames left in the player's hit pulse (4 = just hit)
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
STAT        = $41
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
; The game's non-fatal hit ($4ACC ld hl,$C7D0), then a new hit pulse unless one
; is running. A is free here: the game loads it again straight after.
t_hit:      ld a,(V_HIT)
            or a
            jr nz,th_on
            ld a,4
            ld (V_HIT),a
th_on:      ld hl,$C7D0
            ret

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

; Video memory is only reachable while the LCD is not drawing a line (STAT mode
; 0 or 1). These wait for that before each access, as the game's own tile
; routine does at $7A9A, so the screen never has to be switched off. Once the
; wait ends there are at least 20 cycles (mode 2) before the next line locks it.
; Copy BC bytes from HL to DE, one side of which is video memory.
vcopy:      ldh a,(STAT)
            and 2
            jr nz,vcopy
vc_ld:      ld a,(hl+)
vc_st:      ld (de),a
            inc de
            dec bc
            ld a,b
            or c
            jr nz,vcopy
            ret

; Fill BC bytes of video memory at HL with D.
vfill:      ldh a,(STAT)
            and 2
            jr nz,vfill
            ld a,d
vf_st:      ld (hl+),a
            dec bc
            ld a,b
            or c
            jr nz,vfill
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
            cp THEME_COUNT
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
            call glyph_setup
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
            ld a,1
            ldh ($4F),a             ; VRAM bank 1 holds the tile attributes
            ld hl,$9800
            ld bc,$0800
            ld d,0
            call vfill
            xor a
            ldh ($4F),a
            jp pal_check            ; the theme's colors from the first frame

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

; ---------------------------------------------------------------- glyphs
; The game's font has no punctuation beyond : - + so six glyphs, drawn in its
; style (a 1-pixel margin, a 6x6 letterform, the same two tones), go into BG
; tiles $F0-$F5 (VRAM $8F00). No screen the game shows uses those tiles.
glyphs:
            db $FF,$FF,$FF,$C3,$FF,$99,$FF,$F9,$FF,$E7,$FF,$FF,$FF,$E7,$FF,$FF        ; ?
            db $FF,$FF,$FF,$E7,$FF,$E7,$FF,$E7,$FF,$E7,$FF,$FF,$FF,$E7,$FF,$FF        ; !
            db $FF,$FF,$FF,$FF,$FF,$FF,$FF,$FF,$FF,$FF,$FF,$9F,$FF,$9F,$FF,$FF        ; .
            db $FF,$FF,$FF,$FF,$FF,$FF,$FF,$FF,$FF,$FF,$FF,$9F,$FF,$9F,$FF,$BF        ; ,
            db $FF,$FF,$FF,$E7,$FF,$E7,$FF,$EF,$FF,$FF,$FF,$FF,$FF,$FF,$FF,$FF        ; '  (the comma's shape, raised)
            db $FF,$FF,$FF,$C7,$FF,$93,$FF,$C7,$FF,$93,$FF,$91,$FF,$C5,$FF,$FF        ; &

glyph_setup:
            ld hl,glyphs
            ld de,$8F00
            ld bc,96
            jp vcopy

; ---------------------------------------------------------------- theme
; SELECT anywhere cycles the color theme (color hardware only) and saves it.
theme_next: ld a,(V_CGB)
            or a
            ret z
            ld a,(V_PAL)
            inc a
            cp THEME_COUNT
            jr c,tn_ok
            xor a
tn_ok:      ld (V_PAL),a
            jp pal_save

; Ten letters, one theme each.
theme_names: db "DMG       POCKET    LIGHT     DK GREEN  GREEN     REVERSE   BROWN     RED       DK BROWN  BLUE      DK BLUE   GRAY      PASTEL    ORANGE    YELLOW    OLIVE     "

; The current theme's name at column 10, row 15 of the window map.
theme_name_draw:
            ld b,10
            ld c,15
            call win_addr
            ld d,h
            ld e,l
            ld a,(V_PAL)
            ld l,a
            ld h,0
            add hl,hl
            ld b,h
            ld c,l
            add hl,hl
            add hl,hl
            add hl,bc               ; theme * 10
            ld bc,theme_names
            add hl,bc
            ld b,10
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
; A full-screen page in the window, over whatever is showing. The LCD stays on
; throughout, as it does when the game changes its own screens: drawing goes to
; PAGEBUF, and page_flush sends the tiles that differ to the window map through
; the waits above. SHOWN mirrors the window map's top-left 20 x 18.
;   ov_open   back up the window map, start a blank page
;   ov_reset  start a blank page over the one showing
;   ov_show   put the page on screen
;   ov_close  put the window map and the screen back
ov_open:    xor a
            ld (V_MHINT),a
            ldh a,(LCDC)
            ld (V_LCDC),a
            ldh a,(WY)
            ld (V_WY),a
            ldh a,(WX)
            ld (V_WX),a
            ld hl,WIN_MAP
            ld de,WINBAK
            ld bc,$0400
            call vcopy
            ld hl,WINBAK            ; SHOWN = the rows now in the window map
            ld de,SHOWN
            ld b,18
ovo_row:    ld c,20
ovo_col:    ld a,(hl+)
            ld (de),a
            inc de
            dec c
            jr nz,ovo_col
            push de
            ld de,12
            add hl,de
            pop de
            dec b
            jr nz,ovo_row

ov_reset:   ld hl,PAGEBUF
            ld bc,360
ovr_loop:   ld a,TILE_BLANK
            ld (hl+),a
            dec bc
            ld a,b
            or c
            jr nz,ovr_loop
            ret

; A first page: rows 2-17 first, since until the window moves to the top only
; rows 0-1 of its map can be on screen (the HUD in a run; the title has no
; window). Then, in VBlank, move the window up and copy rows 0-1.
ov_show:    push bc
            push de
            ldh a,(LCDC)            ; a page already showing: from VBlank, top to
            bit 5,a                 ; bottom, which stays ahead of the LCD
            jr z,ovs_first
            ldh a,(WY)
            or a
            jr nz,ovs_first
            call wait_vbl
            ld b,0
            ld c,18
            call page_flush
            jr ovs_done
ovs_first:  ld b,2
            ld c,16
            call page_flush
            call wait_vbl
            xor a
            ldh (WY),a
            ld a,7
            ldh (WX),a
            ld a,(V_LCDC)
            or $E0                  ; LCD on, window on, window map $9C00
            res 1,a                 ; sprites off
            ldh (LCDC),a
            ld hl,PAGEBUF           ; rows 0-1 in this VBlank, a plain copy (no
            ld de,WIN_MAP           ; mode waits) so it ends before line 0
            ld b,2
ov01_row:   ld c,20
ov01_col:   ld a,(hl+)
ov01_st:    ld (de),a
            inc de
            dec c
            jr nz,ov01_col
            ld a,e
            add a,12
            ld e,a
            dec b
            jr nz,ov01_row
            ld hl,PAGEBUF           ; and SHOWN to match, outside VBlank
            ld de,SHOWN
            ld bc,40
            call cpy
ovs_done:   pop de
            pop bc
            ret

; In VBlank the window goes back where it was, which shows at most its rows 0-1;
; the backup puts those back first, before the LCD reaches them.
ov_close:   call wait_vbl
            ld a,(V_WY)
            ldh (WY),a
            ld a,(V_WX)
            ldh (WX),a
            ld a,(V_LCDC)
            ldh (LCDC),a
ovc_flip:   ld hl,WINBAK
            ld de,WIN_MAP
            ld bc,$0400
            jp vcopy

; Send rows B to B+C-1 of PAGEBUF to the window map, only where they differ
; from SHOWN.
page_flush: push bc
            ld a,b                  ; HL = PAGEBUF + 20 * B
            ld l,a
            ld h,0
            add hl,hl
            add hl,hl
            ld d,h
            ld e,l
            add hl,hl
            add hl,hl
            add hl,de
            ld de,PAGEBUF
            add hl,de
            push hl
            ld l,b                  ; DE = WIN_MAP + 32 * B
            ld h,0
            add hl,hl
            add hl,hl
            add hl,hl
            add hl,hl
            add hl,hl
            ld de,WIN_MAP
            add hl,de
            ld d,h
            ld e,l
            pop hl
            pop bc
            ld b,c                  ; B = rows to go
pf_row:     ld c,20
pf_col:     ld a,(hl)
            inc h                   ; SHOWN is PAGEBUF + $200
            inc h
            cp (hl)
            jr z,pf_same
            ld (hl),a
            push af
pf_wait:    ldh a,(STAT)
            and 2
            jr nz,pf_wait
            pop af
pf_st:      ld (de),a
pf_same:    dec h
            dec h
            inc hl
            inc de
            dec c
            jr nz,pf_col
            push hl
            ld hl,12
            add hl,de
            ld d,h
            ld e,l
            pop hl
            dec b
            jr nz,pf_row
            ret

; HL = PAGEBUF address of column B, row C.
win_addr:   push de
            ld l,c
            ld h,0
            add hl,hl
            add hl,hl
            ld d,h
            ld e,l
            add hl,hl
            add hl,hl
            add hl,de               ; row * 20
            ld c,b
            ld b,0
            add hl,bc
            ld bc,PAGEBUF
            add hl,bc
            pop de
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
to_5:       cp $3F
            jr nz,to_q1
            ld a,$F0                ; ?
            ret
to_q1:      cp $21
            jr nz,to_q2
            ld a,$F1                ; !
            ret
to_q2:      cp $2E
            jr nz,to_q3
            ld a,$F2                ; .
            ret
to_q3:      cp $2C
            jr nz,to_q4
            ld a,$F3                ; ,
            ret
to_q4:      cp $27
            jr nz,to_q5
            ld a,$F4                ; '
            ret
to_q5:      cp $26
            jr nz,to_q6
            ld a,$F5                ; &
            ret
to_q6:      cp $30
            jr nz,to_6
            ld a,$6F
            ret
to_6:       cp $41
            jr nc,to_letter
            add a,$3F               ; 1-9
            ret
to_letter:  add a,$14
            ret

; HL -> column, row, then text ending in 0, drawn into PAGEBUF.
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
            call mr_cursor          ; the page goes on screen with its cursor
            call ov_show
mr_loop:    call wait_vbl
            call mr_theme
            call mr_cursor
            ld b,0
            ld c,18
            call page_flush
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
; Confirm pages: heading in column 3 (where LEGION OF EVIL starts), text in
; column 3, the NO and YES rows like the menu's items (column 4, cursor in 2).
str_e1:     db 3,3,"ERASE SAVE",0
str_e2:     db 3,6,"ARE YOU SURE?",0
str_en:     db 4,9,"NO",0
str_ey:     db 4,11,"YES",0
str_n1:     db 3,3,"NEW RUN",0
str_n2:     db 3,6,"RUN IN PROGRESS",0
str_n3:     db 3,8,"WILL BE LOST.",0
str_n4:     db 3,10,"ARE YOU SURE?",0
str_nn:     db 4,13,"NO",0
str_ny:     db 4,15,"YES",0

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
tm_go:      ld c,7
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
            and F_RUN
            jr z,tm_new_go          ; no saved run: nothing to lose
            call confirm_newrun
            or a
            jr nz,tm_new_yes
            call ov_reset           ; NO: back to the menu, the run still saved
            jr tm_draw
tm_new_yes: call sram_on            ; YES: the saved run is thrown away
            xor a
            ld (S_RUN_OK),a
            call sram_off
            ld a,(V_FLAGS)
            and $FD                 ; drop F_RUN
            ld (V_FLAGS),a
tm_new_go:  ld a,(V_FLAGS)
            or F_PEND_STORE
tm_go_run:  ld (V_FLAGS),a
            call go_dark
            call ov_close
            ld a,(V_JOY)
            or $80
            ld (V_JOY),a
            ret

; Everything in the game's darkest shade from here to the store or the restored
; run, so the title, its wipe and the run's start-up don't show in between.
go_dark:    ldh a,(SH_BGP)
            ld (V_KEEP),a
            ldh a,(SH_OBP0)
            ld (V_KEEP+1),a
            ldh a,(SH_OBP1)
            ld (V_KEEP+2),a
            ld a,$FF
            ldh (SH_BGP),a
            ldh (SH_OBP0),a
            ldh (SH_OBP1),a
            ld a,1
            ld (V_DARK),a
            jp wait_vbl             ; the VBlank hook applies it

; A = 1 if the save was erased.
confirm_erase:
            call ov_reset
            ld hl,str_e1
            call ov_text
            ld hl,str_e2
            call ov_text
            ld hl,str_en
            call ov_text
            ld hl,str_ey
            call ov_text
            ld b,2
            ld c,9
            ld d,2
            call menu_run
            cp 1
            jr nz,ce_no
            call erase_save
            ld a,1
            ret
ce_no:      xor a
            ret

; A = 1 to throw the saved run away and start a new one.
confirm_newrun:
            call ov_reset
            ld hl,str_n1
            call ov_text
            ld hl,str_n2
            call ov_text
            ld hl,str_n3
            call ov_text
            ld hl,str_n4
            call ov_text
            ld hl,str_nn
            call ov_text
            ld hl,str_ny
            call ov_text
            ld b,2
            ld c,13
            ld d,2
            call menu_run
            cp 1
            ld a,0
            ret nz
            inc a
            ret

; ---------------------------------------------------------------- pause
str_paused: db 7,3,"PAUSED",0
str_resume: db 4,7,"RESUME",0
str_squit:  db 4,9,"SAVE & QUIT",0
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
rl_nosel:   ld a,($C5B5)            ; a menu or the store is showing: START is theirs
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
            ld a,(V_JOY)            ; in live play START belongs to the pause menu: the
            and $7F                 ; stock pause, which froze the run with nothing on
            ld (V_JOY),a            ; screen, never sees it, even while held from the title
            bit 7,c
            ret z
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
pm_nohint:  ld b,2
            ld c,7
            ld d,2
            call menu_run
            cp 1
            jr z,pm_save
            jp ov_close
pm_save:    call go_dark            ; the run stays hidden while it is saved
            call ov_close
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
            ld hl,V_KEEP            ; the game's shades, not the dark ones
            ld de,R_HRAM + SH_BGP - $80
            ld bc,3
            call cpy
            ld hl,V_KEEP
            ld de,R_IO + 4
            ld bc,3
            call cpy
            ld hl,$DF00
            ld de,R_STACK
            ld bc,$0100
            call cpy
            ld hl,$C000
            ld de,R_WRAM
            ld bc,WRAM_LEN
            call cpy
            ld hl,$9800
            ld de,R_MAP
            ld bc,$0800
            call vcopy
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
            ld a,(V_DARK)           ; the maps change over a few frames: keep the
            or a                    ; screen dark meanwhile (CONTINUE already is)
            call z,blackout
            xor a
            ld (V_DARK),a           ; the restored shadows bring the shades back
            ld hl,R_MAP
            ld de,$9800
            ld bc,$0800
            call vcopy
            ld hl,$C0A0             ; the registers this console booted with: the
            ld a,(hl+)              ; snapshot may come from the other kind of
            ld (V_BOOT),a           ; console, and the start-up after the next
            ld a,(hl)               ; SAVE & QUIT reads them
            ld (V_BOOT+1),a
            ld hl,R_WRAM
            ld de,$C000
            ld bc,WRAM_LEN
            call cpy
            ld a,(V_BOOT)
            ld ($C0A0),a
            ld a,(V_BOOT+1)
            ld ($C0A1),a
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
            ld a,(V_CGB)            ; the DMA routine's wait came back with HRAM:
            or a                    ; set it for this console's speed
            ld a,$28
            jr z,rr_dma
            ld a,$50
rr_dma:     ldh ($87),a
            xor a
            ld (C_VALID),a          ; the colors are rebuilt from the restored shades
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

; Every palette black until the next rebuild: BGP, OBP0 and OBP1 on the old
; hardware, palette RAM on a Game Boy Color (reachable, like video memory, only
; outside mode 3). The restored HRAM shadows and C_VALID bring the colors back.
blackout:   ld a,$FF
            ldh ($47),a
            ldh ($48),a
            ldh ($49),a
            ld a,(V_CGB)
            or a
            ret z
            ld a,$80
            ldh ($68),a
            ld b,8
bo_bg:      ldh a,(STAT)
            and 2
            jr nz,bo_bg
            xor a
bo_bgst:    ldh ($69),a
            dec b
            jr nz,bo_bg
            ld a,$80
            ldh ($6A),a
            ld b,16
bo_ob:      ldh a,(STAT)
            and 2
            jr nz,bo_ob
            xor a
bo_obst:    ldh ($6B),a
            dec b
            jr nz,bo_ob
            ret

; Start the game over, as if the console had just been switched on.
reset_game: di
            xor a
            ldh ($0F),a
            ldh ($FF),a
            ldh ($26),a
            ldh a,(LCDC)            ; LCD off in VBlank, and video memory cleared as
            bit 7,a                 ; the boot ROM leaves it, so the start-up
            jr z,rg_off             ; shows nothing of the run
rg_vbl:     ldh a,($44)
            cp 144
            jr nz,rg_vbl
            xor a
            ldh (LCDC),a
rg_off:     ld hl,$8000
rg_clr:     xor a
            ld (hl+),a
            ld a,h
            cp $A0
            jr nz,rg_clr
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
            jr nz,ob_cgb            ; to spare, so the table stays as the game builds it
            ld a,$C0                ; and the DMA reads the game's own page, even after
            ldh ($92),a             ; restoring a snapshot made on a color console
            ret
ob_cgb:
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
            ld a,(V_PAL)            ; V_TPTR = themes + theme * 24
            ld l,a
            ld h,0
            add hl,hl
            add hl,hl
            add hl,hl
            ld b,h
            ld c,l
            add hl,hl
            add hl,bc
            ld bc,themes
            add hl,bc
            ld a,l
            ld (V_TPTR),a
            ld a,h
            ld (V_TPTR + 1),a
            ld d,h
            ld e,l
            ld hl,PALBUF
            ld a,(C_BGP)
            call pal_four           ; the background palette
            ld a,(C_OBP0)
            call pal_four           ; sprite palette 0 (DE moved on by 8)
            ld a,(C_OBP1)
            call pal_four
            ld a,1
            ld (PAL_DIRTY),a
            ret

; Four colors from the palette at DE, picked by the four 2-bit shades in A,
; written at HL. DE comes back pointing at the next palette.
pal_four:   ld b,4
            ld c,a
pf_loop:    ld a,c
            and 3
            add a,a                 ; 2 bytes a color
            push de
            add a,e
            ld e,a
            jr nc,pf_nc
            inc d
pf_nc:      ld a,(de)
            ld (hl+),a
            inc de
            ld a,(de)
            ld (hl+),a
            pop de
            srl c
            srl c
            dec b
            jr nz,pf_loop
            ld a,e
            add a,8
            ld e,a
            ret nc
            inc d
            ret

; Each theme is three palettes of four colors, lightest first: the background,
; sprite palette 0 and sprite palette 1, as the Game Boy Color's boot ROM
; stores its compatibility palettes. The console screens are SameBoy's
; measured colors; the twelve boot palettes are the ones the Game Boy Color
; offers by holding a direction with or without A or B at power-on, with its
; names; OLIVE is its palette combination 17.
themes:
            dw $4778,$3290,$1D87,$0861,$4778,$3290,$1D87,$0861,$4778,$3290,$1D87,$0861   ; DMG  (console)
            dw $4B38,$3230,$1D27,$0440,$4B38,$3230,$1D27,$0440,$4B38,$3230,$1D27,$0440   ; POCKET  (console)
            dw $638F,$4ACA,$31E6,$0861,$638F,$4ACA,$31E6,$0861,$638F,$4ACA,$31E6,$0861   ; LIGHT  (console)
            dw $7FFF,$1BEF,$6180,$0000,$7FFF,$421F,$1CF2,$0000,$7FFF,$421F,$1CF2,$0000   ; DK GREEN  (Right+A)
            dw $7FFF,$03EA,$011F,$0000,$7FFF,$03EA,$011F,$0000,$7FFF,$03EA,$011F,$0000   ; GREEN  (Right)
            dw $0000,$4200,$037F,$7FFF,$0000,$4200,$037F,$7FFF,$0000,$4200,$037F,$7FFF   ; REVERSE  (Right+B)
            dw $7FFF,$32BF,$00D0,$0000,$7FFF,$32BF,$00D0,$0000,$7FFF,$32BF,$00D0,$0000   ; BROWN  (Up)
            dw $7FFF,$421F,$1CF2,$0000,$7FFF,$1BEF,$0200,$0000,$7FFF,$7E8C,$7C00,$0000   ; RED  (Up+A)
            dw $639F,$4279,$15B0,$04CB,$7FFF,$32BF,$00D0,$0000,$7FFF,$32BF,$00D0,$0000   ; DK BROWN  (Up+B)
            dw $7FFF,$7E8C,$7C00,$0000,$7FFF,$421F,$1CF2,$0000,$7FFF,$1BEF,$0200,$0000   ; BLUE  (Left)
            dw $7FFF,$6E31,$454A,$0000,$7FFF,$421F,$1CF2,$0000,$7FFF,$32BF,$00D0,$0000   ; DK BLUE  (Left+A)
            dw $7FFF,$5294,$294A,$0000,$7FFF,$5294,$294A,$0000,$7FFF,$5294,$294A,$0000   ; GRAY  (Left+B)
            dw $53FF,$4A5F,$7E52,$0000,$53FF,$4A5F,$7E52,$0000,$53FF,$4A5F,$7E52,$0000   ; PASTEL  (Down)
            dw $7FFF,$03FF,$001F,$0000,$7FFF,$03FF,$001F,$0000,$7FFF,$03FF,$001F,$0000   ; ORANGE  (Down+A)
            dw $7FFF,$03FF,$012F,$0000,$7FFF,$7E8C,$7C00,$0000,$7FFF,$1BEF,$0200,$0000   ; YELLOW  (Down+B)
            dw $7FFF,$42B5,$3DC8,$0000,$7FFF,$01DF,$0112,$0000,$7FFF,$01DF,$0112,$0000   ; OLIVE  (game palette 17)

; ---------------------------------------------------------------- hit pulse
; On a hit the game switches the player's four sprites to the second sprite
; palette (attribute bit 4), and its player code puts the first one back on the
; next frame, so the flash showed for one frame at most. Each hit with no pulse
; running now gives 2 frames on the hit palette and 2 frames normal, set in the
; game's sprite table before the frame's DMA; hits during a pulse don't restart
; it, so being hit reads as a steady blink.
hit_pulse:  ld a,(V_HIT)
            or a
            ret z
            dec a
            ld (V_HIT),a
            cp 2                    ; 4 and 3 (now 3 and 2): lit; 2 and 1: normal
            ld hl,$C093
            ld b,4
            jr c,hp_off
hp_on:      set 4,(hl)
            inc l
            inc l
            inc l
            inc l
            dec b
            jr nz,hp_on
            ret
hp_off:     res 4,(hl)
            inc l
            inc l
            inc l
            inc l
            dec b
            jr nz,hp_off
            ret

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
            ld hl,sp+12
            ld a,(hl+)
            ld h,(hl)
            ld l,a
            ld a,h
            cp $58
            jp nz,oam_build         ; not the run loop: just the sprite table
            ld a,l
            cp $B8
            jp nz,oam_build
            ld a,(V_DARK)
            cp 2
            call z,undark
            call hit_pulse          ; before oam_build copies the sprite table
            call oam_build
            ld a,(V_FLAGS)
            bit 2,a
            jr z,wh_cont
            res 2,a
            ld (V_FLAGS),a
            ld a,1
            ld ($C5DC),a            ; open the store, as the game-over flow does
            ld a,2
            ld (V_DARK),a
            xor a
            ld ($C5C0),a
            ld ($C5CD),a
wh_cont:    ld a,(V_FLAGS)
            bit 3,a
            ret z
            jp restore_run

; The run loop's next wait after it asked for the store comes once the store is
; drawn: bring the shades back.
undark:     xor a
            ld (V_DARK),a
            ld a,(V_KEEP)
            ldh (SH_BGP),a
            ld a,(V_KEEP+1)
            ldh (SH_OBP0),a
            ld a,(V_KEEP+2)
            ldh (SH_OBP1),a
            jp pal_check

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
