; =====================================================================
; Roguecraft GB - resume-a-run patch
;
; The game already carries everything a run save needs. It is a GB
; Studio game, and GB Studio's save system gives it slots of the whole
; game state: slot 0 is the run (variable 75 is the floor number) and
; slot 1 the achievements. START GAME offers RESUME GAME when slot 0
; holds a run past the first floor, and resuming restarts that floor
; with the hero carried over. What the stock game never does is write
; slot 0 on the way into a floor, so there is never a run to resume.
;
; This adds that one write. Every floor's script opens with a native
; call to the floor setup at bank 2 $401B, which loads the hero back
; out of the game variables - health from v76 and so on, as the last
; floor's exit left them. patch.py repoints those calls here. These run
; the stock setup exactly as the VM would have, and then, from the
; second floor on, ask the game's own data_save to write slot 0 - the
; floor just reached, with the hero as he arrived on it.
;
; Death needs nothing added: the game-over script already sets the floor
; back to nought and saves slot 0, which takes RESUME GAME off the menu.
; =====================================================================

; Everything that differs between releases - the trampoline, the stock
; setup and data_save, the floor variable - is emitted ahead of this by
; patch.py from the matching ROM profile.

; Both entries are reached through the $3E01 banked-call trampoline,
; from the VM's native call handler, with one stack argument, the
; script context:
;   SP+0  return into the trampoline      SP+2  the caller's bank
;   SP+4  return to the VM                SP+6  THIS

; ---- run_start: the first floor's script ----
; The floors come in a fixed order and the first is always The
; Wilderness, reached only by starting a new game. The game relies on
; the floor counter being nought here, which it always was, because
; nothing ever put a later floor into slot 0 for START GAME's resume
; check to load. Now that something does, choosing NEW GAME from that
; menu would carry the old run's floor number into the new run. Put it
; back to nought, as it has always been on this floor, and save nothing:
; there is nothing to resume on the first floor, and a run saved earlier
; is kept until the new one reaches floor two.
run_start:
        xor a
        ld (FLOOR),a
        ld (FLOOR+1),a
        ld c,a                  ; c = 0: do not save
        jr enter

; ---- floor_start: every later floor's script ----
floor_start:
        ld c,1                  ; c = 1: save once the setup is done

enter:
        xor a
        ld (CHESTS_OPENED),a
        ld (CHESTS_OPENED+1),a
        ld (CHESTS_OPENED+2),a
        ld (CHESTS_OPENED+3),a  ; a new floor: no chest opened on it yet
        ld hl,sp+6
        ld a,(hl+)
        ld h,(hl)
        ld l,a                  ; hl = THIS
        push bc                 ; keep the save flag
        push hl                 ; the stock setup reads THIS at SP+6, as before
        ld b,h
        ld c,l                  ; and finds it in bc, as the VM happened to leave it
        ld e,SETUP_BANK
        ld hl,SETUP_FN
        call BANKED_CALL        ; stock floor setup
        add sp,2
        pop bc
        ld a,c
        or a
        ret z                   ; the first floor
        ld a,(FLOOR)
        ld hl,FLOOR+1
        or (hl)
        ret z                   ; (belt and braces: never save a floor-0 run)
        xor a
        push af
        inc sp                  ; one-byte argument: slot 0
        ld e,SAVE_BANK
        ld hl,SAVE_FN
        call BANKED_CALL        ; the game's own data_save(0)
        inc sp
        ret

; =====================================================================
; Chest bookkeeping fixes
;
; Each floor is a 5x5 grid of rooms, and each room carries a word of
; item bits saying what is still in it - bit 1 is its chest. Taking an
; item clears its bit, so the item does not come back when you return.
; The chest total counts, as each floor is generated, the rooms whose
; chest bit is set; the chests-found count goes up as each one opens.
; =====================================================================

; ---- count_chest: replaces the generator's `chests_total += 1` ----
; (bank 4 $56CE, reached through the trampoline.) The last floor is a
; single boss arena, but the generator still lays out an ordinary floor
; behind it that nobody can ever walk into, and counted its chests. Every
; run's total came up those chests short of what could be found.
count_chest:
        ld a,(FLOOR)
        cp FINAL_FLOOR
        ret z                   ; the arena's phantom floor: nothing to count
        ld hl,CHESTS_TOTAL
        inc (hl)
        ret nz
        inc hl
        inc (hl)
        ret

; ---- chest_opened: replaces the open-chest handler's `chests_found += 1` ----
; (bank 2 $644A, reached through the trampoline.) An opened chest turns
; into its gold, in the same entity slot, and the room's chest bit stays
; set until that gold is picked up. But entering a room spawns whatever
; has its bit set afresh, and the stock game spawned the chest shut. Walk
; away from the gold and back, and the chest stood there shut again:
; opening it counted a second time and paid out again. Note the room's
; chest as opened, for chest_spawn.
chest_opened:
        ld hl,CHESTS_FOUND
        inc (hl)
        jr nz,co_mark
        inc hl
        inc (hl)
co_mark:
        call room_bit
        or (hl)
        ld (hl),a               ; this room's chest is open; its gold may wait
        ret

; ---- chest_spawn: the room entry's `chest hp = 2` (bank 2 $4503) ----
; Reached only when the room's chest bit is set. A chest opened earlier on
; this floor comes back as the gold that was left (hp 1), not shut (hp 2).
; The game's own animation refresh draws hp 1 as gold.
chest_spawn:
        call room_bit
        and (hl)
        ld a,CHEST_SHUT
        jr z,cs_set
        dec a                   ; the gold that was left
cs_set:
        ld (CHEST_HP),a
        ret

; -> hl = the current room's byte in CHESTS_OPENED, a = its bit
; (a bit per room, 5 * row + column; floor_start and run_start clear it)
room_bit:
        ld a,(ROOM_ROW)
        ld c,a
        add a,a
        add a,a
        add a,c
        ld c,a
        ld a,(ROOM_COL)
        add a,c
        ld hl,CHESTS_OPENED
rb_byte:
        cp 8
        jr c,rb_bit
        sub 8
        inc hl
        jr rb_byte
rb_bit:
        ld b,a
        inc b
        ld a,1
rb_shift:
        dec b
        ret z
        add a,a
        jr rb_shift

; =====================================================================
; Mini-map fix
;
; The engine's own hiding of actors under the window is switched off in
; this game, so holding B for the mini-map hides them itself: the stock
; map-open code gives every living entity in the room cells the map
; covers an animation set whose only frame is empty. Closing the map
; asks the game's per-entity animation refresh to put each one back.
;
; That refresh refuses any enemy for 60 frames after any attack, so
; that an attack or hurt animation can play out. Close the map inside
; that second and every enemy it covered stays on its empty frame until
; the lock runs out: invisible, but still there and still fighting.
;
; These wrap the three pieces of the map code. The open records which
; entities it hid, and the close refreshes those that still have the
; empty set, with the lock lifted for just that call. Everything else,
; the hero included, is left to the stock code.
; =====================================================================

; ---- map_open: the map script's native call to the stock map-open ----
map_open:
        ld hl,MAP_HIDDEN
        ld b,MAX_ENTITIES
        xor a
mo_clear:
        ld (hl+),a
        dec b
        jr nz,mo_clear
        ld e,MAP_BANK
        ld hl,MAP_OPEN_FN
        call BANKED_CALL        ; the stock map-open, which hides via map_hide
        ret

; ---- map_hide: the stock map-open's call to hide one entity ----
; Reached through the trampoline with one argument:
;   SP+6  the entity
map_hide:
        ld hl,sp+6
        ld c,(hl)
        push bc
        ld a,c
        push af
        inc sp                  ; the same one-byte argument
        ld e,MAP_BANK
        ld hl,MAP_HIDE_FN
        call BANKED_CALL        ; the stock hide: the empty animation set
        inc sp
        pop bc
        ld a,c
        cp MAX_ENTITIES
        ret nc
        call entity_actor
        ld de,ACTOR_FRAME_START
        add hl,de
        ld a,(hl)               ; the empty frame it now shows
        inc a                   ; stored + 1, so that 0 means not hidden
        ld hl,MAP_HIDDEN
        ld b,0
        add hl,bc
        ld (hl),a
        ret

; ---- map_close: the map script's native call to the stock map-close ----
map_close:
        ld e,MAP_BANK
        ld hl,MAP_CLOSE_FN
        call BANKED_CALL        ; stock: map flag off, then refresh what it may
        ld c,1                  ; the hero, entity 0, is never held by the lock
mc_loop:
        ld a,c
        cp MAX_ENTITIES
        ret nc
        ld hl,ENTITY_COUNT
        cp (hl)
        ret nc
        ld hl,MAP_HIDDEN
        ld b,0
        add hl,bc
        ld a,(hl)
        ld (hl),b               ; consumed
        or a
        jr z,mc_next            ; the map did not hide this one
        ld e,a                  ; e = its empty frame + 1
        push bc
        push de
        call entity_actor
        pop de
        ld bc,ACTOR_ANIMS
        add hl,bc
        ld a,(hl+)              ; still the empty set? its first animation
        inc a                   ; starts and ends on the empty frame
        cp e
        jr nz,mc_skip
        ld a,(hl)
        inc a
        cp e
        jr nz,mc_skip           ; something gave it a new set: leave it be
        pop bc
        push bc
        ld a,(ATTACK_LOCK)
        ld d,a
        push de                 ; keep the lock's count
        xor a
        ld (ATTACK_LOCK),a
        push af
        inc sp                  ; second argument: 0, as the stock close passes
        ld a,c
        push af
        inc sp                  ; first argument: the entity
        ld e,MAP_BANK
        ld hl,REFRESH_FN
        call BANKED_CALL        ; the game's own refresh, for this one entity
        add sp,2
        pop de
        ld a,d
        ld (ATTACK_LOCK),a      ; the lock runs on for everything else
mc_skip:
        pop bc
mc_next:
        inc c
        jr mc_loop

; c = entity -> hl = its actor
entity_actor:
        ld hl,ENTITY_ACTOR
        ld b,0
        add hl,bc
        ld l,(hl)
        ld h,0
        ld e,l
        ld d,h
        add hl,hl
        add hl,de               ; 3
        add hl,hl
        add hl,hl               ; 12
        add hl,de               ; 13
        add hl,hl
        add hl,hl               ; 52, the size of an actor
        ld de,ACTORS
        add hl,de
        ret
code_end:
