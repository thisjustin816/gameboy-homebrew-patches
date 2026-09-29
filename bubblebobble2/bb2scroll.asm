; Scroll writes wait for VBlank.
;
; The game runs its logic right after each VBlank and writes SCX and SCY
; whenever the logic gets to them, which is partway down the visible frame.
; Lines already drawn use the old scroll and the rest use the new one, so a
; moving camera tears.
;
; Every scroll write on the per-frame paths goes through RST $08 (SCY) or
; RST $10 (SCX) instead. The value is kept in HRAM with a pending bit, and
; vblank_scroll copies it to the hardware at the start of VBlank, ahead of
; the OAM DMA. While the LCD is off there is no VBlank to wait for, so the
; write goes straight to the hardware and clears the pending bit.
;
; The register addresses, SHADOW_*, the HRAM bytes and WRAM_CLEAR come from the
; ROM profile in patch.py. HRAM powers up with random contents on a real
; console, so boot_init clears the pending bits before the first VBlank.

; ---- code at ORG_BODY -------------------------------------------------------

; Entered from the RST $08 vector with the new SCY in A and stored at PEND_Y.
; Preserves every register and flag.
defer_y:
    push af
    ldh a,(LCDC)
    rlca                        ; carry = LCD on
    ldh a,(FLAGS)               ; ldh leaves the carry alone
    jr nc,y_lcd_off
    or $01
    ldh (FLAGS),a
    pop af
    ret
y_lcd_off:
    and $FE
    ldh (FLAGS),a
    ldh a,(PEND_Y)
    ldh (SCY),a
    pop af
    ret

; Entered from the RST $10 vector with the new SCX in A and stored at PEND_X.
defer_x:
    push af
    ldh a,(LCDC)
    rlca
    ldh a,(FLAGS)
    jr nc,x_lcd_off
    or $02
    ldh (FLAGS),a
    pop af
    ret
x_lcd_off:
    and $FD
    ldh (FLAGS),a
    ldh a,(PEND_X)
    ldh (SCX),a
    pop af
    ret

; The game's "SCX, SCY <- shadow" routine, which runs every frame. Sets both
; axes at once. Returns with A = the SCY shadow and the flags as they came in.
scroll_copy:
    push af
    ldh a,(LCDC)
    rlca                        ; carry = LCD on
    ld a,(SHADOW_X)
    jr nc,sc_lcd_off
    ldh (PEND_X),a
    ld a,(SHADOW_Y)
    ldh (PEND_Y),a
    ldh a,(FLAGS)
    or $03
    ldh (FLAGS),a
    jr sc_done
sc_lcd_off:
    ldh (SCX),a
    ld a,(SHADOW_Y)
    ldh (SCY),a
    ldh a,(FLAGS)
    and $FC
    ldh (FLAGS),a
sc_done:
    pop af
    ld a,(SHADOW_Y)
    ret

; Called in place of the OAM DMA call at the top of the VBlank handler's full
; update, then runs the DMA itself. Clobbers A only.
vblank_scroll:
    ldh a,(FLAGS)
    and a
    jr z,vs_dma
    rra                         ; carry = SCY pending
    jr nc,vs_x
    push af
    ldh a,(PEND_Y)
    ldh (SCY),a
    pop af
vs_x:
    rra                         ; carry = SCX pending
    jr nc,vs_done
    ldh a,(PEND_X)
    ldh (SCX),a
vs_done:
    xor a
    ldh (FLAGS),a
vs_dma:
    jp OAM_DMA

; Called in place of the boot's call to its WRAM clear, then runs it.
boot_init:
    xor a
    ldh (FLAGS),a
    jp WRAM_CLEAR
code_end:
