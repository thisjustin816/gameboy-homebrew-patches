; Remember the last round started, and offer its password on the PASSWORD
; screen.
;
; Each round load saves the round and the flags the game's own password
; carries (FLAGS_A | FLAGS_B, as the game-over password does) to battery-backed
; SRAM. When the PASSWORD screen sets itself up, the saved pair goes through
; the game's own encoder (ENCODE, bank 3), and on the screen's first frame the
; four letters are put in the entry buffer and drawn, with the slot marker and
; the hand where they are after typing four letters and moving to END. A then
; continues through the game's own password check, and BACK still clears
; letters to retype.
;
; SRAM at $A000 holds: signature SIG_1 SIG_2, the round, the flags, and a
; checksum. Anything else there is ignored, which is what a fresh cartridge
; looks like.
;
; save_round and the SRAM switches sit in bank 0, and the PASSWORD screen's two
; routines in bank 3, which is mapped whenever that screen runs. The names
; below come from the ROM profile in patch.py.

; ==== org SAVE_ORG ====

; Called in place of "ld hl,$DC80", the first instruction of the round loader.
; Returns with HL = $DC80, as that instruction did, and every other register
; kept.
save_round:
    push af
    push bc
    call sram_on
    ld hl,SRAM
    ld a,SIG_1
    ld (hl+),a
    ld a,SIG_2
    ld (hl+),a
    ld a,(ROUND)
    ld (hl+),a
    ld b,a
    ld a,(FLAGS_A)
    ld c,a
    ld a,(FLAGS_B)
    or c
    ld (hl+),a
    add a,b
    xor SUM_XOR
    ld (hl),a
    call sram_off
    pop bc
    pop af
    ld hl,LOADER_HL
    ret

sram_on:
    ld a,$0A
    ld (SRAM_ENABLE),a
    ret

sram_off:
    xor a
    ld (SRAM_ENABLE),a
    ret
save_end:


; ==== org PF_ORG ====
; In bank 3, next to the PASSWORD screen's code. sram_on and sram_off above
; are in bank 0.

; Called in place of "ld (SLOT),a" (A = 0) in the PASSWORD screen's setup,
; with bank 3 mapped. Returns with A = 0 for the stores that follow.
pf_init:
    ld (SLOT),a
    push bc
    push de
    push hl
    call sram_on
    ld hl,SRAM
    ld a,(hl+)
    cp SIG_1
    jr nz,pf_off
    ld a,(hl+)
    cp SIG_2
    jr nz,pf_off
    ld a,(hl+)
    ld d,a
    cp ROUNDS
    jr nc,pf_off
    ld a,(hl+)
    ld e,a
    add a,d
    xor SUM_XOR
    cp (hl)
    jr nz,pf_off
    call sram_off
    call ENCODE                 ; D = round, E = flags -> four letter tiles at SHOWN
    ld a,1
    ld (PF_PENDING),a
    jr pf_done
pf_off:
    call sram_off
    xor a
    ld (PF_PENDING),a
pf_done:
    pop hl
    pop de
    pop bc
    xor a
    ret

; Called in place of "ld a,(PW_FLAGS)", the first instruction of the PASSWORD
; screen's per-frame code. Once after pf_init, fills and draws the entry.
; Returns with A = PW_FLAGS.
pf_step:
    ld a,(PF_PENDING)
    and a
    jr z,ps_done
    xor a
    ld (PF_PENDING),a
    push bc
    push de
    push hl
    ld hl,SHOWN
    ld de,BUFFER
    ld b,4
ps_copy:
    ld a,(hl+)
    ld (de),a
    inc de
    dec b
    jr nz,ps_copy
    ld a,3
    ld (SLOT),a
    ld hl,MARK_X
    ld a,(hl)
    add a,$30                   ; three slots to the right, as typing moves it
    ld (hl),a
    ld hl,MARK_X2
    ld a,(hl)
    add a,$30
    ld (hl),a
    ld a,(HAND_X)               ; the grid column to go back to, as the game keeps
    ld (HAND_COL),a             ; it when the hand leaves the grid
    ld a,HAND_END_Y
    ld (HAND_Y),a
    ld (HAND_Y2),a
    ld a,HAND_END_X
    ld (HAND_X),a
    add a,8
    ld (HAND_X2),a
    ld a,MENU_END
    ld (MENU),a
    call DRAW_SLOTS             ; queues the four letters for VBlank
    pop hl
    pop de
    pop bc
ps_done:
    ld a,(PW_FLAGS)
    ret

pf_end:
