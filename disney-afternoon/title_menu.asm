; A title screen's check, replacing: ldh a,(NEW) / and START_MASK in its loop.
; That loop also runs other menus, which it tells apart by HL, so B counts only
; with HL = TITLE_HL_HI:TITLE_HL_LO. Returns what the replaced code left: A and
; the flags.

title_check:
    ld a,h
    cp TITLE_HL_HI
    jr nz,title_orig
    ld a,l
    cp TITLE_HL_LO
    jr nz,title_orig
    ldh a,(NEW)
    and $02                 ; B
    jr nz,go_menu
title_orig:
    ldh a,(NEW)
    and START_MASK
    ret
