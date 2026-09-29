; A title screen's check, replacing: ld a,(NEW) / and START_MASK in a loop that
; only the title runs. Returns what the replaced code left: A and the flags.

title_check:
    ld a,(NEW)
    and $02                 ; B
    jr nz,go_menu
    ld a,(NEW)
    and START_MASK
    ret
