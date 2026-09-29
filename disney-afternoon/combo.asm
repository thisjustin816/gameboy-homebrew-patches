; A+B+SELECT+START anywhere goes back to the menu. This replaces the end of the
; game's joypad routine, ld a,$30 / ldh ($00),a / ret, which runs once a frame
; with the held buttons in C. Callers may test the flags the routine returns
; with, so A and the flags come back exactly as the replaced code left them.

combo:
    push af
    ld a,c
    and $0F                 ; A, B, SELECT, START
    cp $0F
    jr z,go_menu
    pop af
    ld a,$30
    ldh ($00),a
    ret
