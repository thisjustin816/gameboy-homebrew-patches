; Bub's movement in the air, retuned to match the Master System version.
;
; The game moves Bub once per logic tick, and a tick is two frames. It jumps
; along a table of Y steps indexed by a countdown (JUMP), locks the direction
; held at take-off (LOCK), and applies one pixel of gravity every tick it is
; not jumping. This replaces the jump table and the per-tick sideways movement
; and gravity (the stock code from bank 2 $4AEF to $4BD2):
;
;   jump        the Master System's arc, sampled every other frame: rises
;               42 px in 10 ticks, stays at the top 10 frames, comes back
;               down to its start in 11 ticks, then falls 2.5 px a tick
;   locked      2.25 px a tick holding that way, 1.5 letting go, 0.75
;               pushing against it (it never reverses)
;   straight up 0.625 px a tick of steering, anywhere in the jump
;   walk-off    2.5 px a tick down and 1 px a tick sideways, either way
;   walking     2 px a tick, 3 with the shoes, as stock
;   the shot    6 px a tick for half as long, the Master System's speed over
;               stock's distance; it fires once every 11 ticks, the
;               Master System's rate (stock 14)
;
; Fractions come from an 8-tick pattern: bit (TICK & 7) of a mask says whether
; this tick gets the extra pixel. The names below come from the ROM profile
; in patch.py.

; ==== org PHYS_ORG ====

; Y steps, applied from the last entry to the first. Entry 0 is applied last
; and stays 0, as stock's does: one routine starts a jump at JUMP = 1. The
; steps are the Master System's jump sampled every other frame: up 42 px, 5
; ticks at the top, and back down to where it started. After that Bub falls
; at the ordinary rate, as on the Master System.
jump_table:
    db 0
    db 3,6,6,6,5,4,4,3,2,2,1
    db 0,0,0,0
    db -2,-2,-3,-3,-4,-5,-5,-6,-6,-6
jump_end:

; Jumped to in place of the stock sideways movement and gravity. Continues at
; RESUME, the landing check, which sets every register it uses.
move:
    push bc
    push de
    push hl
    ld hl,TICK
    inc (hl)
    ld hl,COOL                  ; the shot cooldown counts down once a tick
    ld a,(hl)
    and a
    jr z,m_cool
    dec (hl)
m_cool:
    ld a,(WALL_L)
    and a
    jr nz,m_right
    ld b,LOCK_LEFT
    ld c,PAD_LEFT
    ld d,PAD_RIGHT
    ld e,FACE_LEFT
    call speed
    and a
    jr z,m_right
    ld b,a
    ld a,(X)
    sub b
    ld (X),a
    jr gravity
m_right:
    ld a,(WALL_R)
    and a
    jr nz,gravity
    ld b,LOCK_RIGHT
    ld c,PAD_RIGHT
    ld d,PAD_LEFT
    ld e,FACE_RIGHT
    call speed
    and a
    jr z,gravity
    ld b,a
    ld a,(X)
    add a,b
    ld (X),a
gravity:
    ld a,(JUMP)
    and a
    jr nz,m_done
    ld a,(GROUND)
    and a
    ld b,1                      ; standing: stock's one pixel, which the landing check takes back
    jr nz,g_add
    ld a,MASK_FALL
    call cadence
    ld b,2
    jr nc,g_add
    inc b
g_add:
    ld a,(Y)
    add a,b
    ld (Y),a
m_done:
    pop hl
    pop de
    pop bc
    jp RESUME

; Pixels to move one way this tick. B = that way's LOCK value, C its pad bit,
; D the other way's pad bit, E its facing bit. Returns A. Sets the facing where
; the stock code did.
speed:
    ld a,(LOCK)
    and a
    jr z,sp_free
    cp b
    jr nz,sp_zero               ; locked the other way
    ld a,(PAD)
    and c
    jr nz,sp_push
    ld a,(PAD)
    and d
    jr nz,sp_against
    ld a,MASK_COAST
    call cadence
    ld a,2
    ret nc
    dec a
    ret
sp_push:
    ld a,MASK_PUSH
    call cadence
    ld a,2
    ret nc
    inc a
    ret
sp_against:
    ld a,MASK_AGAINST
    call cadence
    ld a,0
    ret nc
    inc a
    ret
sp_zero:
    xor a
    ret
sp_free:
    ld a,(PAD)
    and c
    jr z,sp_zero
    ld a,(JUMP)
    and a
    jr nz,sp_steer
    ld a,e                      ; walking or falling: stock sets the whole state byte
    or FACE_WALK
    ld (FACE),a
    ld a,(GROUND)
    and a
    ld a,1
    jr z,sp_shoes
    inc a
sp_shoes:
    ld b,a
    ld a,(SHOES)
    and a
    ld a,b
    ret z
    inc a
    ret
sp_steer:
    ld a,(FACE)
    and $7F
    or e
    ld (FACE),a
    ld a,MASK_STEER
    call cadence
    ld a,0
    ret nc
    inc a
    ret

; Carry = bit (TICK & 7) of the mask in A. Keeps every register but A.
cadence:
    push bc
    ld b,a
    ld a,(TICK)
    and 7
    inc a
    ld c,a
    ld a,b
cad_loop:
    rrca
    dec c
    jr nz,cad_loop
    pop bc
    ret
; Called in place of "ld hl,SHOT / ld a,(hl)" in the fire check, which has
; already seen B pressed. The shot now travels twice as fast for half as
; long, so it would free its slot, and let Bub fire again, twice as soon. This
; sets the Master System's rate instead: it returns A nonzero (no shot) while the last shot or
; the cooldown is still running, and otherwise starts the cooldown and returns
; A = 0. HL = SHOT either way, as the fire code expects.
fire_gate:
    ld hl,COOL
    ld a,(SHOT)
    or (hl)
    jr nz,fg_done
    ld (hl),COOL_TICKS
fg_done:
    ld hl,SHOT
    ret
; Called in place of "ld a,JUMP_LENGTH / ld (JUMP),a" where Bub bounces on a
; bubble (bank 2 $542A) or on an enemy in one ($5657). Those run after this
; tick's movement, so the stock bounce leaves Bub sinking for another tick.
; This starts the jump with its first step already taken, as a jump from the
; ground now is. Keeps every register but A and F; what follows sets both.
bounce_start:
    push bc
    ld a,(jump_end-1)           ; the first step up
    ld b,a
    ld a,(Y)
    add a,b
    ld (Y),a
    ld a,jump_end-jump_table-1
    ld (JUMP),a
    pop bc
    ret
; Called in place of "ld a,(PAD)" where Bub touches the top of a bubble
; ($5421) or of an enemy in one ($564E). The game then bounces him if bit 0,
; jump, is held, and pops the bubble if not. It counts him as on top while he
; is still rising up through it, and with the jump rising 6 px a tick he can
; get there before the bubble has moved off, and bounce on the way up. On the
; Master System only a landing bounces, and a bubble hit from below pops. So
; while the jump is still rising this returns the pad without jump held.
; Keeps every register but A and F; what follows sets both.
bounce_gate:
    push de
    push hl
    ld a,(JUMP)
    and a
    jr z,bg_pad                 ; not jumping: falling or standing
    ld e,a
    ld d,0
    ld hl,jump_table
    add hl,de
    ld a,(hl)                   ; the step just taken
    and $80
    jr z,bg_pad                 ; at the top or coming down
    ld a,(PAD)
    and $FE                     ; rising: as if jump weren't held
    jr bg_done
bg_pad:
    ld a,(PAD)
bg_done:
    pop hl
    pop de
    ret
code_end:
