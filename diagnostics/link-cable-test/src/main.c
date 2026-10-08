#include <gb/gb.h>
#include <gb/cgb.h>
#include <gbdk/font.h>
#include <stdio.h>
#include <string.h>
#include "protocol.h"
#include "stress.h"

#define TX_BUFFERS 8u
#define TX_MASK (TX_BUFFERS - 1u)

/* No send_byte()/receive_byte(): their default ISR owns SB/SC. */
volatile uint8_t running, host = 1, fast, done;
volatile uint8_t tx[TX_BUFFERS][PACKET_SIZE], ready[TX_BUFFERS], active, txpos;
volatile uint8_t ring[128], wr, rd;
volatile uint16_t overflow, underrun;
uint8_t rate_mode = 1, frozen, lost, have_seq, window[16], candidate[16], window_len, window_pos;
uint32_t next_tx, expected, good, crc_errors, seq_errors, data_errors;
uint32_t timeouts, first_sec, first_seq, first_wanted_seq, elapsed_seconds, second_phase;
uint16_t old_time, last_good, last_draw, first_expected_crc, first_received_crc;
uint8_t first_code, first_kind, first_got_kind, first_test_mismatch;
uint16_t first_wanted_epoch, first_got_epoch, first_wanted_hash, first_got_hash;
uint8_t profile, double_cpu, page, waiting, deadline_latched, scene_pending;
uint8_t pending_payload[6], outgoing_payload[6];
stress_state simulation;
uint16_t wait_started, scene_started, last_load, max_reply, max_gap, max_recovery;
uint32_t pending_sequence;
uint32_t updates, barriers, state_errors, barrier_errors, epoch_errors, deadlines, stale_replies;
volatile uint16_t busy_checksum;
const uint8_t ball_tiles[16] = {0,0,0x18,0x18,0x3c,0x3c,0x3c,0x3c,0x18,0x18,0,0,0,0,0,0};
const uint8_t frame_tiles[96] = {
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xff, 0xff, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x10,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x1f, 0x1f, 0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x10,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xf0, 0xf0, 0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x10,
    0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1f, 0x1f, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x10, 0x10, 0x10, 0x10, 0x10, 0x10, 0xf0, 0xf0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
};
const uint8_t punctuation_tiles[96] = {
    0x00, 0x00, 0x08, 0x08, 0x08, 0x08, 0x3e, 0x3e, 0x08, 0x08, 0x08, 0x08, 0x00, 0x00, 0x00, 0x00,
    0x02, 0x02, 0x04, 0x04, 0x08, 0x08, 0x10, 0x10, 0x20, 0x20, 0x40, 0x40, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x20, 0x20, 0x10, 0x10, 0x08, 0x08, 0x10, 0x10, 0x20, 0x20, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x3e, 0x3e, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x18, 0x18, 0x18, 0x18,
    0x00, 0x00, 0x00, 0x00, 0x18, 0x18, 0x18, 0x18, 0x00, 0x00, 0x18, 0x18, 0x18, 0x18, 0x00, 0x00
};
const char *modes[] = {"1 BYTE/FRAME", "4 BYTE BURST", "CONTINUOUS"};
const char *profiles[] = {"SUSTAIN", "SCENE BARRIERS", "UNEQUAL LOAD", "SHARED BALL", "ALL STRESS"};
const char *failures[] = {"NONE", "CRC/FRAME", "ROLE", "PAYLOAD", "SEQUENCE", "NO SYNC", "RX OVERRUN", "TX UNDERRUN", "SERIAL HANG", "STATE MISMATCH", "BAD BARRIER", "UPDATE ORDER"};

/* A VBlank must not split the two-byte timer read. */
uint16_t frame_now(void) {
    uint16_t result;
    CRITICAL { result = sys_time; }
    return result;
}

void serial_isr(void) {
    uint8_t n;
    if (!running) return;
    n = (wr + 1u) & 127u;
    if (n == rd) ++overflow;
    else { ring[wr] = SB_REG; wr = n; }
    if (++txpos == PACKET_SIZE) {
        txpos = 0;
        n = (active + 1u) & TX_MASK;
        if (ready[n]) {
            ready[active] = 0;
            active = n;
        } else ++underrun;
    }
    SB_REG = tx[active][txpos];
    if (!host) SC_REG = 0x80u | (fast ? 2u : 0u);
    done = 1;
}

void latch(uint8_t code, uint32_t seq) {
    if (!first_code) {
        first_code = code;
        first_sec = elapsed_seconds;
        first_wanted_seq = expected;
        first_seq = seq;
    }
}

void make_packet(uint8_t *p, uint32_t sequence) {
    if (!profile) packet_make(p, sequence, host ? 1u : 2u);
    else {
        stress_payload(&simulation, profile, !host, outgoing_payload);
        stress_packet(p, sequence, host ? 1u : 2u, outgoing_payload);
    }
}

void accept_update(const uint8_t *payload, uint32_t sequence) {
    uint8_t result;
    uint16_t duration;
    stress_state wanted;
    if (host && !waiting) return;
    result = stress_accept(&simulation, profile, host, payload);
    if (result == STRESS_ACCEPT) {
        if (simulation.command == STRESS_SCENE) ++barriers; else ++updates;
        if (host) {
            duration = frame_now() - wait_started;
            if (duration > max_reply) max_reply = duration;
            waiting = 0;
        }
    } else if (result == STRESS_STALE) {
        if (host) ++stale_replies;
    } else {
        if (!first_code) {
            wanted = simulation;
            if (!host && (payload[1] | ((uint16_t)payload[2] << 8)) != simulation.epoch)
                stress_next(&wanted, profile);
            first_wanted_epoch = wanted.epoch;
            first_got_epoch = payload[1] | ((uint16_t)payload[2] << 8);
            first_wanted_hash = stress_hash(&wanted);
            first_got_hash = payload[3] | ((uint16_t)payload[4] << 8);
            first_test_mismatch = payload[5] != profile;
            first_kind = first_test_mismatch ? profile : (wanted.command | (host ? STRESS_ACK : 0));
            first_got_kind = first_test_mismatch ? payload[5] : payload[0];
        }
        if (result == STRESS_STATE_ERROR) { ++state_errors; latch(9, sequence); }
        else if (result == STRESS_COMMAND_ERROR) { ++barrier_errors; latch(10, sequence); }
        else { ++epoch_errors; latch(11, sequence); }
    }
}

void stress_receive(const uint8_t *payload, uint32_t sequence) {
    uint16_t epoch = payload[1] | ((uint16_t)payload[2] << 8);
    uint8_t i;
    /* A loading peer keeps sending its old reply until this barrier is ready. */
    if (!host && payload[0] == STRESS_SCENE && payload[5] == profile
        && epoch == (uint16_t)(simulation.epoch + 1u)) {
        if (!scene_pending) {
            for (i = 0; i != 6; ++i) pending_payload[i] = payload[i];
            scene_started = frame_now(); pending_sequence = sequence; scene_pending = 1;
        }
        return;
    }
    accept_update(payload, sequence);
}

void stress_service(void) {
    uint16_t now = frame_now();
    uint16_t budget = rate_mode == 0 ? 360u : (rate_mode == 1 ? 120u : 60u);
    if (scene_pending && (uint16_t)(now - scene_started) >= 6u) {
        scene_pending = 0; accept_update(pending_payload, pending_sequence);
    }
    if (host && waiting && !deadline_latched && (uint16_t)(now - wait_started) > budget) {
        ++deadlines; deadline_latched = 1;
    }
}

void begin_update(void) {
    if (!profile || !host || waiting) return;
    stress_next(&simulation, profile);
    waiting = 1; deadline_latched = 0; wait_started = frame_now();
}

void refill(void) {
    uint8_t b, i;
    /* Keep seven packets ahead so a redraw or bad-frame scan has headroom. */
    for (i = 1; i != TX_BUFFERS; ++i) {
        b = (active + i) & TX_MASK;
        if (!ready[b]) {
            make_packet((uint8_t *)tx[b], next_tx++);
            ready[b] = 1;
            return;
        }
    }
}

void workload(void) {
    uint16_t started;
    uint8_t i;
    if ((profile != 2 && profile != 4) || (simulation.epoch & 7u)
        || simulation.epoch == last_load || (!!(simulation.epoch & 8u) != !!host)) return;
    last_load = simulation.epoch;
    for (i = 0; i != TX_BUFFERS - 1u; ++i) refill();
    started = frame_now();
    /* Interrupts stay enabled while main-thread work occupies three frames. */
    while ((uint16_t)(frame_now() - started) < 3u)
        busy_checksum = busy_checksum * 33u + 17u;
}

void receive(void) {
    uint8_t b, code, i;
    uint32_t seq;
    while (rd != wr) {
        b = ring[rd]; rd = (rd + 1u) & 127u;
        /* O(1) work for non-frames, including a floating/all-FF cable. */
        window[window_pos] = b; window_pos = (window_pos + 1u) & 15u;
        if (window_len < 16) ++window_len;
        if (window_len != 16 || window[window_pos] != 0xd3
            || window[(window_pos + 1u) & 15u] != 0x91) continue;
        for (i = 0; i != 16; ++i) candidate[i] = window[(window_pos + i) & 15u];
        seq = 0;
        code = profile ? stress_packet_check(candidate, host ? 2u : 1u, &seq)
            : packet_check(candidate, host ? 2u : 1u, &seq);
        if (code) {
            if (code == 1) ++crc_errors; else ++data_errors;
            if (!first_code) {
                first_expected_crc = packet_crc(candidate, 13);
                first_received_crc = candidate[13] | ((uint16_t)candidate[14] << 8);
                seq = (uint32_t)candidate[3] | ((uint32_t)candidate[4] << 8)
                    | ((uint32_t)candidate[5] << 16) | ((uint32_t)candidate[6] << 24);
            }
            latch(code, seq);
            /* Slide after a failure; insertion/deletion can recover framing. */
        } else {
            if (have_seq && seq != expected) { ++seq_errors; latch(4, seq); }
            expected = seq + 1u; have_seq = 1;
            {
                uint16_t now = frame_now(), gap = now - last_good;
                if (good && gap > max_gap) max_gap = gap;
                if (lost && gap > max_recovery) max_recovery = gap;
                ++good; last_good = now; lost = 0;
            }
            if (profile) stress_receive(candidate + 7, seq);
            window_len = window_pos = 0;
        }
    }
}

void service(void) {
    uint16_t now = frame_now();
    /* 70224 CPU cycles per frame; divide both clock constants by 16. */
    second_phase += (uint32_t)(uint16_t)(now - old_time) * 4389u;
    old_time = now;
    while (second_phase >= 262144ul) { second_phase -= 262144ul; ++elapsed_seconds; }
    refill(); receive();
    if (profile) stress_service();
    now = frame_now();
    if (overflow) latch(6, expected);
    if (underrun) latch(7, expected);
    if ((uint16_t)(now - last_good) >= 120u && !lost) {
        lost = 1; ++timeouts; latch(5, expected);
    }
}

/* Direct tile rows keep UI work out of the serial re-arm path. */
char line[32], digits[11];
uint8_t tiles[20], font_base;
void row(uint8_t y, const char *s) {
    uint8_t i;
    for (i = 0; i < 20; ++i) {
        uint8_t c = *s ? *s++ : ' ';
        if (c == '+') tiles[i] = 246;
        else if (c == '/') tiles[i] = 247;
        else if (c == '>') tiles[i] = 248;
        else if (c == '-') tiles[i] = 249;
        else if (c == '.') tiles[i] = 250;
        else if (c == ':') tiles[i] = 251;
        else tiles[i] = font_min[2u + c] + font_base;
    }
    set_bkg_tiles(0, y, 20, 1, tiles);
    if (running) service();
}
void clear_screen(void) {
    uint8_t y;
    for (y = 0; y != 18; ++y) row(y, "");
}

void draw_arena(void) {
    uint8_t i, y;
    for (i = 0; i != 20; ++i) tiles[i] = i == 0 ? 242u : (i == 19 ? 243u : 240u);
    set_bkg_tiles(0, 5, 20, 1, tiles);
    tiles[0] = 244u; tiles[19] = 245u;
    set_bkg_tiles(0, 14, 20, 1, tiles);
    tiles[0] = 241u;
    for (y = 6; y != 14; ++y) {
        set_bkg_tiles(0, y, 1, 1, tiles); set_bkg_tiles(19, y, 1, 1, tiles);
    }
}

char *number(uint32_t n, uint8_t base) {
    uint8_t i = 10, d;
    digits[10] = 0;
    do { d = n % base; n /= base; digits[--i] = d < 10 ? '0'+d : 'A'+d-10; } while (n);
    return &digits[i];
}
void value(uint8_t y, const char *label, uint32_t n) {
    strcpy(line, label); strcat(line, number(n, 10)); row(y, line);
}
void draw(void) {
    uint16_t ov, un;
    stress_state shown = simulation;
    CRITICAL { ov = overflow; un = underrun; }
    row(0, "LINK SUSTAIN v1.1+");
    strcpy(line, host ? "HOST " : "PEER ");
    strcat(line, fast ? "FAST " : "NORM ");
    strcat(line, double_cpu ? "2X " : "1X ");
    strcat(line, frozen ? "HOLD" : "LIVE"); row(1, line);
    if (page != 3 || !profile) HIDE_SPRITES;
    if (page == 3) {
        uint8_t y;
        row(2, profiles[profile]); value(3, "STEP ", shown.epoch);
        row(4, profile ? "ONE UPDATE AT A TIME" : "CHOOSE A STRESS TEST");
        row(5, "");
        for (y = 6; y != 14; ++y) row(y, "");
        row(14, ""); draw_arena();
        if (profile) SHOW_SPRITES;
    } else if (page == 1) {
        row(2, profiles[profile]);
        value(3, "UPDATES ", updates); value(4, "SCENES  ", barriers);
        value(5, "STATE   ", state_errors); value(6, "BARRIER ", barrier_errors);
        value(7, "ORDER   ", epoch_errors); value(8, "OLD ACK ", stale_replies);
        value(9, "STEP    ", shown.epoch);
        value(10, "BALL X  ", shown.x); value(11, "BALL Y  ", shown.y);
        row(12, scene_pending ? "LOADING: HOLD REPLY" : (waiting ? "WAITING FOR ACK" : "UPDATE ACCEPTED"));
        row(13, (profile == 1 || profile == 4) ? "SCENE WAIT 6 FRAMES" : "SCENE WAIT: OFF");
        row(14, (profile == 2 || profile == 4) ? "LOAD BUSY 3 FRAMES" : "CPU LOAD: OFF");
    } else if (page == 2) {
        row(2, double_cpu ? "CPU DOUBLE" : "CPU NORMAL");
        row(3, !host ? "HOST SETS WIRE RATE" : (fast ? (double_cpu ? "WIRE 524288 BIT/S" : "WIRE 262144 BIT/S")
            : (double_cpu ? "WIRE 16384 BIT/S" : "WIRE 8192 BIT/S")));
        value(4, "MAX ACK F ", max_reply); value(5, "MAX GAP F ", max_gap);
        value(6, "RECOVER F ", max_recovery); value(7, "LATE UPD  ", deadlines);
        if (host) value(8, "BUDGET F  ", rate_mode == 0 ? 360u : (rate_mode == 1 ? 120u : 60u));
        else row(8, "HOST SETS BUDGET");
        row(9, "F = DISPLAY FRAMES");
        row(10, "ACK TIMING: HOST ONLY"); row(11, "RECOVER: LAST GOOD");
        row(12, "CPU MAY DIFFER"); row(13, "MATCH LINK CLOCK");
        row(14, "OLD ACK IS EXPECTED");
    } else {
        row(2, modes[rate_mode]);
        row(3, lost ? "NO SYNC / RETRYING" : (good ? "SYNC - TESTING" : "WAITING FOR PEER"));
        value(4, "SEC  ", elapsed_seconds);
        value(5, "GOOD ", good);
        value(6, "CRC  ", crc_errors);
        value(7, "SEQ  ", seq_errors);
        value(8, "DATA ", data_errors);
        value(9, "GAPS ", timeouts);
        strcpy(line, "OV "); strcat(line, number(ov, 10)); strcat(line, " UN ");
        strcat(line, number(un, 10)); row(10, line);
        strcpy(line, "FIRST "); strcat(line, failures[first_code]); row(11, line);
        value(12, "AT SEC ", first_sec);
        strcpy(line, "PKT "); strcat(line, number(first_seq, 16)); row(13, line);
        if (first_code == 4) {
            strcpy(line, "WANT "); strcat(line, number(first_wanted_seq, 16)); row(14, line);
        } else if (first_code >= 9) {
            strcpy(line, first_code == 9 ? "HASH " : (first_code == 10 ? (first_test_mismatch ? "TEST " : "CMD ") : "STEP "));
            strcat(line, number(first_code == 9 ? first_wanted_hash : (first_code == 10 ? first_kind : first_wanted_epoch), 16));
            strcat(line, ">");
            strcat(line, number(first_code == 9 ? first_got_hash : (first_code == 10 ? first_got_kind : first_got_epoch), 16));
            row(14, line);
        } else {
            strcpy(line, "CRC "); strcat(line, number(first_expected_crc, 16));
            strcat(line, ">"); strcat(line, number(first_received_crc, 16)); row(14, line);
        }
    }
    strcpy(line, "L R PAGE "); strcat(line, number(page + 1u, 10));
    strcat(line, " OF 4"); row(15, line);
    row(16, "B STOP / START MENU");
    row(17, "SELECT: HOLD DISPLAY");
}

void set_cpu_speed(void) {
    uint8_t mask;
    if (!!(KEY1_REG & 0x80u) == !!double_cpu) return;
    mask = IE_REG;
    disable_interrupts(); IE_REG = 0; IF_REG = 0; P1_REG = 0x30u;
    /* Preserve the read-only speed bit when requesting the STOP switch. */
    KEY1_REG |= 1u;
    __asm
        .db 0x10, 0x00
    __endasm;
    IE_REG = mask; enable_interrupts();
}

void start_test(void) {
    uint8_t b;
    running = 0; SC_REG = 0;
    good = crc_errors = seq_errors = data_errors = timeouts = 0;
    elapsed_seconds = second_phase = first_sec = first_seq = first_wanted_seq = 0;
    overflow = underrun = first_expected_crc = first_received_crc = 0;
    wr = rd = active = txpos = done = 0;
    have_seq = window_len = window_pos = first_code = lost = frozen = page = 0;
    first_kind = first_got_kind = first_test_mismatch = 0;
    first_wanted_epoch = first_got_epoch = first_wanted_hash = first_got_hash = 0;
    waiting = deadline_latched = scene_pending = 0;
    updates = barriers = state_errors = barrier_errors = epoch_errors = deadlines = stale_replies = 0;
    max_reply = max_gap = max_recovery = busy_checksum = 0; last_load = 0xffffu;
    stress_init(&simulation);
    set_cpu_speed();
    begin_update();
    for (b = 0; b != TX_BUFFERS; ++b) {
        make_packet((uint8_t *)tx[b], b);
        ready[b] = 1;
    }
    next_tx = TX_BUFFERS;
    old_time = last_good = last_draw = frame_now();
    IF_REG &= (uint8_t)~SIO_IFLAG;
    SB_REG = tx[0][0]; running = 1;
    if (!host) SC_REG = 0x80u | (fast ? 2u : 0u);
}

uint8_t transfer(void) {
    uint16_t started = frame_now();
    done = 0;
    SC_REG = 0x81u | (fast ? 2u : 0u);
    while (!done) {
        service();
        if ((uint16_t)(frame_now() - started) >= 6u) {
            latch(8, expected); ++timeouts; SC_REG = 0; running = 0;
            return 0;
        }
    }
    service();
    /* Allow the external-clock peer ISR to load the next byte. */
    delay(double_cpu ? 4u : 2u);
    return 1;
}

void menu(void) {
    uint8_t previous = 0, keys, pressed;
    HIDE_SPRITES;
    clear_screen();
    row(0, "LINK SUSTAIN v1.1+");
    row(2, "2 CONSOLES, SAME ROM");
    row(3, "ONE HOST + ONE PEER");
    row(4, "START PEER FIRST");
    row(5, "THEN START HOST");
    row(12, "LEFT/RIGHT: ROLE");
    row(13, "UP/DOWN: HOST RATE");
    row(14, "SELECT: LINK CLOCK");
    row(15, "A: CPU  B: TEST");
    row(16, "MATCH TEST + CLOCK");
    row(17, "START: NEW TEST");
    while (joypad() & J_START) vsync();
    for (;;) {
        row(7, host ? "ROLE  HOST" : "ROLE  PEER");
        strcpy(line, "RATE  "); strcat(line, modes[rate_mode]); row(8, line);
        row(9, fast ? "CLOCK CGB FAST" : "CLOCK NORMAL");
        row(10, double_cpu ? "CPU   DOUBLE" : "CPU   NORMAL");
        strcpy(line, "TEST  "); strcat(line, profiles[profile]); row(11, line);
        vsync(); keys = joypad(); pressed = keys & ~previous; previous = keys;
        if (pressed & (J_LEFT | J_RIGHT)) host ^= 1u;
        if (pressed & J_UP) rate_mode = (rate_mode + 1u) % 3u;
        if (pressed & J_DOWN) rate_mode = (rate_mode + 2u) % 3u;
        if ((pressed & J_SELECT) && _cpu == CGB_TYPE) fast ^= 1u;
        if ((pressed & J_A) && _cpu == CGB_TYPE) double_cpu ^= 1u;
        if (pressed & J_B) profile = (profile + 1u) % 5u;
        if (pressed & J_START) break;
    }
    clear_screen(); start_test();
}

void main(void) {
    uint8_t keys, pressed, previous = 0, i;
    font_t handle;
    const palette_color_t colors[4] = {RGB(31,31,27), RGB(21,24,19), RGB(10,14,10), RGB(1,3,2)};
    font_init(); handle = font_load(font_min);
    font_base = ((pmfont_handle)handle)->first_tile;
    if (_cpu == CGB_TYPE) { set_bkg_palette(0, 1, colors); set_sprite_palette(0, 1, colors); }
    set_bkg_data(240, 6, frame_tiles);
    set_bkg_data(246, 6, punctuation_tiles);
    set_sprite_data(0, 1, ball_tiles); set_sprite_tile(0, 0);
    SHOW_BKG; DISPLAY_ON;
    add_SIO(serial_isr); add_SIO(nowait_int_handler);
    set_interrupts(VBL_IFLAG | SIO_IFLAG);
    menu(); draw();
    for (;;) {
        if (running) {
            workload(); begin_update();
            if (host) {
                for (i = 0; i != (rate_mode == 0 ? 1u : 4u) && running; ++i)
                    if (!transfer()) break;
                if (rate_mode != 2) vsync();
            } else vsync();
            service();
        } else vsync();
        if (page == 3 && profile && !frozen) {
            move_sprite(0, 16u + ((uint16_t)(simulation.x - 8u) * 136u) / 143u,
                64u + ((uint16_t)(simulation.y - 16u) * 56u) / 111u);
        }
        keys = joypad(); pressed = keys & ~previous; previous = keys;
        if (pressed & (J_LEFT | J_RIGHT)) {
            page = (page + ((pressed & J_RIGHT) ? 1u : 3u)) % 4u; draw();
        }
        if (pressed & J_SELECT) { frozen ^= 1u; if (!frozen) draw(); }
        if (pressed & J_B) {
            running = 0; SC_REG = 0; frozen = 0; draw();
            row(3, "STOPPED - DATA KEPT");
        }
        if (!running && (pressed & J_START)) { menu(); previous = J_START; draw(); }
        if (running && !frozen && (uint16_t)(frame_now() - last_draw) >= 30u) {
            last_draw = frame_now(); draw();
        }
    }
}
