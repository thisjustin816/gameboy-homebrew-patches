; Remember the last round started, and offer its password on the PASSWORD
; screen.
;
; A round is two bytes: ROUTE, which of the game's three routes it is on, and
; ROUND. Each round load saves them to battery-backed SRAM. When the PASSWORD
; screen sets itself up, the saved round goes through the game's own encoder
; (ENCODE, bank 0), and the four letters it makes are put in the entry buffer
; and drawn in the four slots, with the cursor on END, as they are after the
; fourth letter is typed. A then continues through the game's own password
; check, and BACK still clears letters to retype.
;
; SRAM at $A000 holds: signature SIG_1 SIG_2, ROUTE, ROUND, and a checksum.
; Anything else there is ignored, which is what a fresh cartridge looks like.
;
; The names below come from the ROM profile in patch.py.

; ==== org SAVE_ORG ====

; Called in place of "ld a,(ROUND)" in the round load (bank 1 $419B). Returns
; with A = ROUND, as that instruction did, and B, C, D, E and HL kept. The flags
; change, and the next instruction sets them again.
save_round:
    push bc
    push hl
    call sram_on
    ld hl,SRAM
    ld a,SIG_1
    ld (hl+),a
    ld a,SIG_2
    ld (hl+),a
    ld a,(ROUTE)
    ld (hl+),a
    ld b,a
    ld a,(ROUND)
    ld (hl+),a
    add a,b
    xor SUM_XOR
    ld (hl),a
    call sram_off
    pop hl
    pop bc
    ld a,(ROUND)
    ret

; Called in place of "ld (SLOT),a" (A = 0) in the PASSWORD screen's setup,
; which runs with interrupts off, so the encoder's HRAM scratch is safe.
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
    ld d,a                      ; saved route
    cp ROUTES
    jr nc,pf_off
    ld a,(hl+)
    ld e,a                      ; saved round
    cp ROUNDS
    jr nc,pf_off
    add a,d
    xor SUM_XOR
    cp (hl)
    jr nz,pf_off
    call sram_off
    ld a,(ROUTE)                ; the encoder reads the live round; put it back after
    ld b,a
    ld a,(ROUND)
    ld c,a
    push bc
    ld a,d
    ld (ROUTE),a
    ld a,e
    ld (ROUND),a
    call ENCODE                 ; the four letter tiles -> BUFFER
    pop bc
    ld a,b
    ld (ROUTE),a
    ld a,c
    ld (ROUND),a
    ld a,3                      ; as the game leaves them after the fourth letter
    ld (SLOT),a
    ld a,ROW_END
    ld (ROW),a
    ld a,1
    ld (PF_PENDING),a
    jr pf_done
pf_off:
    call sram_off
    xor a                       ; WRAM is random at power-on on a console
    ld (PF_PENDING),a
pf_done:
    pop hl
    pop de
    pop bc
    ret

; Called in place of "ld a,(SLOT)" in the PASSWORD screen's per-frame code.
; Once after pf_init, queues the four letters for VBlank the way typing one
; does. Returns with A = SLOT and B, C, D, E and HL kept. The flags change, and
; the next instruction sets them again.
pf_step:
    ld a,(PF_PENDING)
    and a
    jr z,ps_done
    xor a
    ld (PF_PENDING),a
    push bc
    push de
    push hl
    ld de,BUFFER
    ld hl,SLOT_VRAM
    ld b,4
ps_loop:
    push bc
    push de
    push hl
    ld bc,1
    ld a,(BANK_NOW)
    call QUEUE_COPY             ; DE = source, HL = destination, BC = length, A = ROM bank
    pop hl
    pop de
    pop bc
    inc de
    inc hl
    inc hl
    dec b
    jr nz,ps_loop
    pop hl
    pop de
    pop bc
ps_done:
    ld a,(SLOT)
    ret

sram_on:
    ld a,$0A
    ld (SRAM_ENABLE),a
    xor a
    ld (SRAM_BANK),a
    ret

sram_off:
    xor a
    ld (SRAM_ENABLE),a
    ret
save_end:
