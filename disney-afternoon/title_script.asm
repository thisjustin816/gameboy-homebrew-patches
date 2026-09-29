; A title screen's check, for games whose screens run as scripts. It replaces
; the first two instructions of the script interpreter's button-test op,
; ld c,$92 / ld a,(hl+), with HL at the op's operands: offset, mask, target.
; The op serves every screen, so B counts only at the title's own ops, listed
; in title_ops as HL, then the mask and target the script holds there, which
; tells the title's bank apart from any other bank with an op at that address.
; Returns what the replaced code left: C = $92, A = the offset, HL past it.

title_check:
    ldh a,(NEW)             ; B first: this op runs many times a frame on some
    and $02                 ; screens, and a slower test there costs lag frames
    jr z,title_fast
    push de
    push hl
    ld de,title_ops
title_entry:
    ld a,(de)               ; HL low byte; 0 ends the list
    and a
    jr z,title_orig
    cp l
    jr nz,title_skip
    inc de
    ld a,(de)
    cp h
    jr nz,title_skip1
    inc hl
    inc de
    ld a,(de)
    cp (hl)                 ; mask
    jr nz,title_orig
    inc hl
    inc de
    ld a,(de)
    cp (hl)                 ; target, low byte
    jr nz,title_orig
    inc hl
    inc de
    ld a,(de)
    cp (hl)                 ; target, high byte
    jr nz,title_orig
    jr go_menu
title_skip:
    inc de
title_skip1:
    inc de
    inc de
    inc de
    inc de
    jr title_entry
title_orig:
    pop hl
    pop de
title_fast:
    ld c,$92
    ld a,(hl+)
    ret
