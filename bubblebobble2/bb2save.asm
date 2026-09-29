; Remember the last stage started, and offer it on the PASSWORD screen.
;
; Every stage load saves the password for that stage to battery-backed SRAM.
; When the PASSWORD screen opens, the four saved symbols are put into the
; game's entry buffer and drawn into their slots, one per frame, exactly as if
; they had been typed. START then continues from that stage through the game's
; own password check, and any slot can be retyped first.
;
; The password itself is built by the game's own encoder, copied unchanged to
; the start of bank 8 as `encode` (it reads the world, stage and extra bits and
; writes the four symbols to CE6C-CE6F). Everything else here is new code in
; bank 8, reached through small trampolines in bank 0.
;
; SRAM at $A000 holds: signature $B0 $B2, the four symbols, and a checksum of
; the symbols. Anything else there is ignored, which is what a fresh cartridge
; looks like.
;
; Constants (profile in patch.py): ENCODE is the copied encoder's address.

; ==== org BANK8_CODE ====

; Called from the stage-load trampoline. Preserves every register.
save_stage:
    push af
    push bc
    push hl
    call ENCODE                 ; the current stage's password -> CE6C-CE6F
    ld a,$0A
    ld (SRAM_ENABLE),a
    ld hl,SRAM
    ld a,SIG_1
    ld (hl+),a
    ld a,SIG_2
    ld (hl+),a
    ld a,(PW_0)
    ld (hl+),a
    ld b,a
    ld a,(PW_1)
    ld (hl+),a
    add a,b
    ld b,a
    ld a,(PW_2)
    ld (hl+),a
    add a,b
    ld b,a
    ld a,(PW_3)
    ld (hl+),a
    add a,b
    xor SUM_XOR
    ld (hl),a
    xor a
    ld (SRAM_ENABLE),a
    pop hl
    pop bc
    pop af
    ret

; Called as the PASSWORD screen finishes opening. If SRAM holds a saved
; password, copies it into the entry buffer, puts the cursor after the last
; slot (where it sits after typing four symbols) and asks pf_step to draw it.
; Preserves every register.
pf_begin:
    push af
    push bc
    push de
    push hl
    xor a
    ldh (PF_LEFT),a
    ld a,$0A
    ld (SRAM_ENABLE),a
    ld hl,SRAM
    ld a,(hl+)
    cp SIG_1
    jr nz,pf_none
    ld a,(hl+)
    cp SIG_2
    jr nz,pf_none
    ld de,PW_0
    ld b,4
    ld c,0
pf_copy:
    ld a,(hl+)
    ld (de),a
    inc de
    add a,c
    ld c,a
    dec b
    jr nz,pf_copy
    ld a,(hl)
    xor SUM_XOR
    cp c
    jr z,pf_ok
    xor a                       ; bad checksum: put the empty buffer back
    ld (PW_0),a
    ld (PW_1),a
    ld (PW_2),a
    ld (PW_3),a
    jr pf_none
pf_ok:
    ld a,CURSOR_END
    ld (CURSOR_X),a
    ld a,4
    ldh (PF_LEFT),a
pf_none:
    xor a
    ld (SRAM_ENABLE),a
    pop hl
    pop de
    pop bc
    pop af
    ret

; Called every frame the PASSWORD screen runs its input handler. Draws one
; saved symbol per frame through the game's VBlank tile queue, the same way
; the game draws a typed symbol, and waits while that queue is busy.
; Preserves every register.
pf_step:
    push af
    push bc
    push de
    push hl
    ldh a,(PF_LEFT)
    or a
    jr z,pfs_done
    ld c,a
    ld a,(VBLANK_FLAGS)
    or a
    jr nz,pfs_done
    ld a,4
    sub c
    ld c,a                      ; slot 0-3
    ld hl,PW_0
    ld b,0
    add hl,bc
    ld a,(hl)                   ; the symbol's number, as the game stores it
    cp $1B
    jr c,pfs_low
    sub $0B
    jr pfs_tile
pfs_low:
    add a,$20
pfs_tile:
    ld d,a
    ld a,c
    add a,a
    add a,SLOT_LOW
    ld (Q_LOW),a
    ld a,SLOT_HIGH
    ld (Q_HIGH),a
    xor a
    ld (Q_COUNT),a
    ld a,d
    ld (Q_TILE),a
    ld a,2
    ld (VBLANK_FLAGS),a
    ldh a,(PF_LEFT)
    dec a
    ldh (PF_LEFT),a
pfs_done:
    pop hl
    pop de
    pop bc
    pop af
    ret
bank8_end:

; ==== org FAR8_ORG ====

; Runs the bank 8 routine at HL and puts the bank back, the way the game's own
; code switches banks (CE73 always names the mapped bank).
far8:
    ld a,(BANK_NOW)
    push af
    ld a,SAVE_BANK
    ld (BANK_NOW),a
    ld (MBC_BANK),a
    call jp_hl
    pop af
    ld (BANK_NOW),a
    ld (MBC_BANK),a
    ret
jp_hl:
    jp hl
far8_end:

; ==== org T_SAVE_ORG ====

; Replaces the "ld a,(C10A)" that follows the stage-load routine's derivation
; of the world and stage. Leaves A as that instruction did.
t_save:
    ld hl,save_stage
    call far8
    ld a,(WORLD)
    ret
t_save_end:

; ==== org T_INIT_ORG ====

; Replaces the "call 2E8C" that ends the PASSWORD screen's setup.
t_init:
    call NEXT_SUBSTATE
    ld hl,pf_begin
    jp far8

; Replaces the "ld hl,C171" that starts the PASSWORD screen's input handler.
t_step:
    ld hl,pf_step
    call far8
    ld hl,$C171
    ret
t_end:
