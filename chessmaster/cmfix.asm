; Two fixes for crashes in Chessmaster's search. The names below come from the
; ROM profile in patch.py.

; ==== org TICK_ORG ====

; The thinking clock, in the VBlank handler. Every 30 frames while the computer
; thinks, the stock code adds the side (0 or 2) to the clock's address with
; "ld c,a / ld hl,CLOCK / add hl,bc" and never sets B, so the tick lands
; 256*B bytes past the clock whenever the interrupted code had B nonzero. This
; block replaces those 14 bytes, from the load of the side flag up to the add,
; with code that forms the address from A alone. It takes the same number of
; cycles on both paths as the stock code (60 and 64), and leaves B and C alone;
; the handler reads neither again before it pops them.
tick:
    ld a,(SIDE_FLAGS)
    and $08                 ; zero: the first clock; $08: the second
    jr nz,tick_even         ; 12 cycles when taken, 8 when not, as the stock jr z
tick_even:
    rrca
    rrca                    ; 0 or 2, the stock side offset
    add a,CLOCK_LO          ; no carry: CLOCK_LO + 2 < $100
    ld l,a
    ld h,CLOCK_HI           ; HL = the clock, for the stock "inc (hl)" that follows
tick_end:

; ==== org ORDER_ORG ====

; Called in place of "call ITER_LINE" at the start of each search iteration.
; ITER_LINE loads the principal variation as the first line to search, and the
; iteration files what it learns about that line under the first entry of the
; root move list, so the two must name the same move. The stock search breaks
; that when a root move fails high and its re-search does not beat the raised
; bound: the variation already starts with the new move, but the list is only
; reordered after a re-search that improves. This puts the root node whose move
; is the variation's first move at the front of the list, the way the stock
; reorder does, and then runs ITER_LINE. When they already agree it changes
; nothing. Keeps B, C, D, E, H and L; ITER_LINE sets A and the flags itself.
fix_root_order:
    push bc
    push de
    push hl
    ld a,(PV_LEN)
    or a
    jr z,order_done         ; no variation yet
    ld a,(ROOT_COUNT)
    or a
    jr z,order_done         ; no root list yet
    ld c,a                  ; entries left to look at
    ld b,0                  ; index into the list
order_find:
    ld hl,ROOT_ORDER
    ld e,b
    ld d,0
    add hl,de
    ld e,(hl)               ; E = the node at this index
    ld hl,NODE_FROM
    add hl,de
    ld a,(PV_FROM)
    cp (hl)
    jr nz,order_next
    ld hl,NODE_TO
    add hl,de
    ld a,(PV_TO)
    cp (hl)
    jr z,order_found
order_next:
    inc b
    dec c
    jr nz,order_find
    jr order_done           ; the variation's move is not a root move
order_found:
    ld a,b
    or a
    jr z,order_done         ; already first
    ld c,b
    ld b,0
order_shift:                ; move entries 0 .. index-1 up one, as the stock reorder does
    ld hl,ROOT_ORDER-1
    add hl,bc
    ld a,(hl+)
    ld (hl),a
    dec c
    jr nz,order_shift
    ld a,e
    ld (ROOT_ORDER),a
order_done:
    pop hl
    pop de
    pop bc
    jp ITER_LINE
order_end:
