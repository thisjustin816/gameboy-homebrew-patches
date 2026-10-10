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
uint8_t profile = 4, double_cpu, page, waiting, deadline_latched, scene_pending;
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
const uint8_t ui_tiles[128] = {
    0x00, 0x00, 0x20, 0x20, 0x30, 0x30, 0x38, 0x38, 0x3c, 0x3c, 0x38, 0x38, 0x30, 0x30, 0x20, 0x20,
    0x00, 0x00, 0x04, 0x04, 0x0c, 0x0c, 0x1c, 0x1c, 0x3c, 0x3c, 0x1c, 0x1c, 0x0c, 0x0c, 0x04, 0x04,
    0x00, 0x00, 0x01, 0x01, 0x02, 0x02, 0x84, 0x84, 0x48, 0x48, 0x30, 0x30, 0x10, 0x10, 0x00, 0x00,
    0x00, 0x00, 0x42, 0x42, 0x24, 0x24, 0x18, 0x18, 0x18, 0x18, 0x24, 0x24, 0x42, 0x42, 0x00, 0x00,
    0x00, 0x00, 0xff, 0xff, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xff, 0xff, 0x00, 0x00,
    0x00, 0x00, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x3c, 0x3c, 0x7e, 0x7e, 0x7e, 0x7e, 0x3c, 0x3c, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x3c, 0x3c, 0x42, 0x42, 0x42, 0x42, 0x3c, 0x3c, 0x00, 0x00, 0x00, 0x00
};
const char *modes[] = {"1 BYTE/FRAME", "4 BYTE BURST", "CONTINUOUS"};
const char *profiles[] = {"SUSTAIN", "SCENE WAIT", "UNEQUAL LOAD", "SHARED BALL", "ALL STRESS"};
const char *failures[] = {"NONE", "CRC/FRAME", "ROLE", "PAYLOAD", "SEQUENCE", "NO SYNC", "RX OVERRUN", "TX UNDERRUN", "SERIAL HANG", "BAD STATE", "BAD BARRIER", "UPDATE ORDER"};

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

/* The NO SYNC before the first packet is the wait for the other console; a real error replaces it. */
uint8_t first_error_open(void) { return !first_code || (first_code == 5 && !good); }

void latch(uint8_t code, uint32_t seq) {
    if (first_error_open() && code != first_code) {
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

uint16_t reply_budget(void) { return rate_mode == 0 ? 360u : (rate_mode == 1 ? 120u : 60u); }

void stress_service(void) {
    uint16_t now = frame_now();
    uint16_t budget = reply_budget();
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
            if (first_error_open()) {
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
#define PASS_SECONDS 600u
#define T_CURSOR 230u
#define T_LARROW 231u
#define T_CHECK 232u
#define T_CROSS 233u
#define T_BAR_OFF 234u
#define T_BAR_ON 235u
#define T_DOT_ON 236u
#define T_DOT_OFF 237u
#define PAL_PASS 1u
#define PAL_FAIL 2u
#define PAL_WAIT 3u
enum { ROW_ROLE, ROW_TEST, ROW_RATE, ROW_LINK, ROW_CPU, MENU_ROWS };

char line[32], digits[11];
uint8_t tiles[20], attrs[20], font_base, cursor, shown_running;
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
        else if (c == '|') tiles[i] = 241;
        else if (c == '}') tiles[i] = T_CURSOR;
        else if (c == '{') tiles[i] = T_LARROW;
        else if (c == '#') tiles[i] = T_CHECK;
        else if (c == '*') tiles[i] = T_CROSS;
        else if (c == '[') tiles[i] = T_BAR_OFF;
        else if (c == ']') tiles[i] = T_BAR_ON;
        else if (c == '(') tiles[i] = T_DOT_ON;
        else if (c == ')') tiles[i] = T_DOT_OFF;
        else tiles[i] = font_min[2u + c] + font_base;
    }
    set_bkg_tiles(0, y, 20, 1, tiles);
    if (running) service();
}
/* CGB attribute bytes pick the palette; the icon and words say the same thing. */
void row_palette(uint8_t y, uint8_t palette) {
    if (_cpu != CGB_TYPE) return;
    memset(attrs, palette, 20);
    VBK_REG = VBK_BANK_1;
    set_bkg_tiles(0, y, 20, 1, attrs);
    VBK_REG = VBK_BANK_0;
}
void clear_screen(void) {
    uint8_t y;
    for (y = 0; y != 18; ++y) { row_palette(y, 0); row(y, ""); }
}

/* A box from row y0 to row y1; its text rows carry '|' at both ends. */
void draw_box(uint8_t y0, uint8_t y1) {
    uint8_t i;
    for (i = 0; i != 20; ++i) tiles[i] = i == 0 ? 242u : (i == 19 ? 243u : 240u);
    set_bkg_tiles(0, y0, 20, 1, tiles);
    for (i = 0; i != 20; ++i) tiles[i] = i == 0 ? 244u : (i == 19 ? 245u : 240u);
    set_bkg_tiles(0, y1, 20, 1, tiles);
}
void draw_arena(void) {
    uint8_t y;
    draw_box(5, 14);
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
void blank(void) { memset(line, ' ', 20); line[20] = 0; }
void put(uint8_t x, const char *s) {
    while (*s && x < 20) line[x++] = *s++;
}
/* Write a number at column x and return the column after it. */
uint8_t put_n(uint8_t x, uint32_t n, uint8_t base) {
    const char *d = number(n, base);
    put(x, d);
    return x + strlen(d);
}
/* Right-align a number so that it ends just before column end. */
void put_right(uint8_t end, uint32_t n, uint8_t base) {
    const char *d = number(n, base);
    uint8_t len = strlen(d);
    put(end > len ? end - len : 0, d);
}
/* A count past 99999 stops growing on screen; the run has failed long before. */
void put_count(uint8_t end, uint32_t n) { put_right(end, n > 99999ul ? 99999ul : n, 10); }
/* M:SS ending just before column end. */
void put_time(uint8_t end, uint32_t seconds) {
    put_right(end - 3u, seconds / 60u, 10);
    line[end - 3u] = ':';
    line[end - 2u] = '0' + (uint8_t)((seconds % 60u) / 10u);
    line[end - 1u] = '0' + (uint8_t)(seconds % 10u);
}
void count_row(uint8_t y, const char *label, uint32_t n) {
    blank(); put(0, label); put_right(20, n, 10); row(y, line);
}
void pair_row(uint8_t y, const char *a, uint32_t an, const char *b, uint32_t bn) {
    blank(); put(0, a); put_count(10, an); put(11, b); put_count(20, bn); row(y, line);
}

/* The first NO SYNC while no packet has ever arrived is the wait for the other console. */
uint8_t failed(void) { return first_code && !(first_code == 5 && !good); }

/* Rows 0-4 are the same on every page: who, what, how long, verdict. */
void draw_header(void) {
    uint8_t palette;
    blank(); put(0, host ? "HOST  " : "PEER  "); put(6, profiles[profile]); row(0, line);
    blank(); put(0, host ? modes[rate_mode] : "HOST SETS RATE");
    put(16, fast ? "FAST" : "NORM"); row(1, line);
    blank(); put(0, !running ? "STOPPED" : (frozen ? "HELD" : "RUNNING"));
    put(8, double_cpu ? "CPU 2X" : "CPU 1X"); put_time(20, elapsed_seconds); row(2, line);
    blank();
    if (failed()) {
        palette = PAL_FAIL; line[0] = '*'; put(2, "FAIL "); put(7, failures[first_code]);
    } else if (!good) {
        palette = PAL_WAIT; line[0] = '(';
        put(2, host ? "WAITING FOR PEER" : "WAITING FOR HOST");
    } else if (elapsed_seconds >= PASS_SECONDS) {
        palette = PAL_PASS; line[0] = '#'; put(2, "PASS: NO ERRORS");
    } else {
        palette = PAL_WAIT; line[0] = running ? '(' : ')';
        put(2, running ? "NO ERRORS YET" : "STOPPED EARLY");
    }
    row(3, line); row_palette(3, palette);
    blank();
    if (failed()) {
        put(0, "FIRST AT"); put_time(14, first_sec); if (lost) put(15, "DOWN");
    } else if (deadlines) {
        put_count(5, deadlines); put(6, deadlines == 1 ? "LATE UPDATE" : "LATE UPDATES");
    } else if (good && elapsed_seconds < PASS_SECONDS) put(0, "10 MIN FOR A PASS");
    row(4, line);
}

/* Page strip: arrows show that L/R turn the page, dots show which one this is. */
void draw_footer(const char *name) {
    uint8_t i;
    blank(); line[0] = '{'; line[19] = '}'; put(2, name);
    for (i = 0; i != 4; ++i) line[12 + 2u * i] = i == page ? '(' : ')';
    row(16, line);
    row(17, !running ? "START: SETTINGS" : (frozen ? "SELECT: RESUME" : "B STOP  SELECT HOLD"));
}

/* Detail for the first error: expected value, then the value received. */
void draw_detail(uint8_t y) {
    const char *tag;
    uint16_t want, got;
    uint8_t x;
    blank();
    if (!failed()) {
        /* Nothing to explain. */
    } else if (first_code == 4) {
        put(0, "WANT "); put_n(5, first_wanted_seq, 16);
    } else if (first_code == 5) {
        put(0, first_sec < 5u ? "STARTED LATE? REDO" : "NO PACKETS FOR 2 S");
    } else if (first_code >= 9) {
        if (first_code == 9) { tag = "HASH "; want = first_wanted_hash; got = first_got_hash; }
        else if (first_code == 10) {
            tag = first_test_mismatch ? "TEST " : "CMD "; want = first_kind; got = first_got_kind;
        } else { tag = "STEP "; want = first_wanted_epoch; got = first_got_epoch; }
        put(0, tag); x = put_n(strlen(tag), want, 16); line[x] = '>'; put_n(x + 1u, got, 16);
    } else if (first_code == 1) {
        put(0, "CRC "); x = put_n(4, first_expected_crc, 16); line[x] = '>';
        put_n(x + 1u, first_received_crc, 16);
    }
    row(y, line);
}

void draw_link_page(void) {
    uint16_t ov, un;
    uint8_t i, cells;
    CRITICAL { ov = overflow; un = underrun; }
    cells = (uint8_t)((uint32_t)(elapsed_seconds > PASS_SECONDS ? PASS_SECONDS : elapsed_seconds) * 18u / PASS_SECONDS);
    row(5, "");
    blank(); for (i = 0; i != 18; ++i) line[1 + i] = i < cells ? ']' : '['; row(6, line);
    row(7, "");
    count_row(8, "GOOD", good);
    pair_row(9, "CRC", crc_errors, "SEQ", seq_errors);
    pair_row(10, "DATA", data_errors, "GAPS", timeouts);
    pair_row(11, "OV", ov, "UN", un);
    row(12, "");
    blank(); put(0, "FIRST "); put(6, failures[failed() ? first_code : 0]); row(13, line);
    blank(); if (failed()) { put(0, "PKT "); put_n(4, first_seq, 16); } row(14, line);
    draw_detail(15);
    draw_footer("LINK");
}

void draw_stress_page(void) {
    stress_state shown = simulation;
    uint8_t i;
    if (!profile) {
        for (i = 5; i != 16; ++i) row(i, "");
        row(6, "NOT USED BY SUSTAIN"); row(8, "PICK A STRESS TEST");
        row(9, "IN THE SETTINGS");
    } else {
        count_row(5, "UPDATES", updates); count_row(6, "SCENES", barriers);
        row(7, "");
        count_row(8, "STATE ERRORS", state_errors);
        count_row(9, "BAD BARRIERS", barrier_errors);
        count_row(10, "SKIPPED STEPS", epoch_errors);
        blank(); put(0, "OLD ACKS"); put_count(17, stale_replies); put(18, "OK"); row(11, line);
        row(12, "");
        blank(); put(0, "STEP"); put_right(16, shown.epoch, 10); row(13, line);
        blank(); put(0, "BALL"); i = put_n(5, shown.x, 10); put_n(i + 1u, shown.y, 10); row(14, line);
        row(15, scene_pending ? "LOADING: HOLD REPLY" : (waiting ? "WAITING FOR ACK" : "UPDATE ACCEPTED"));
    }
    draw_footer("STRESS");
}

void draw_timing_page(void) {
    uint8_t i;
    blank(); put(0, double_cpu ? "CPU DOUBLE SPEED" : "CPU NORMAL SPEED"); row(5, line);
    blank();
    if (!host) put(0, "HOST SETS WIRE RATE");
    else put(0, fast ? (double_cpu ? "WIRE 524288 BIT/S" : "WIRE 262144 BIT/S")
        : (double_cpu ? "WIRE 16384 BIT/S" : "WIRE 8192 BIT/S"));
    row(6, line);
    row(7, "");
    for (i = 8; i != 12; ++i) {
        blank();
        if (i == 8) { put(0, "SLOWEST REPLY"); if (host) put_count(18, max_reply); else put(16, "--"); }
        else if (i == 9) { put(0, "LONGEST GAP"); put_count(18, max_gap); }
        else if (i == 10) { put(0, "RECOVERY"); put_count(18, max_recovery); }
        else { put(0, "LATE UPDATES"); if (host) put_count(19, deadlines); else put(17, "--"); }
        if (i != 11 && (host || i != 8)) put(19, "F");
        row(i, line);
    }
    row(12, "");
    blank();
    if (host) { put(0, "REPLY BUDGET"); put_count(18, reply_budget()); put(19, "F"); }
    else put(0, "HOST SETS BUDGET");
    row(13, line);
    row(14, "F IS ONE FRAME 17 MS");
    row(15, "");
    draw_footer("TIMING");
}

void draw_ball_page(void) {
    blank(); put(0, "STEP"); put_n(5, simulation.epoch, 10); row(15, line);
    draw_footer("BALL");
}

void draw(void) {
    draw_header();
    if (page != 3 || !profile) HIDE_SPRITES;
    if (page == 3) {
        uint8_t y;
        for (y = 5; y != 15; ++y) row(y, "");
        draw_arena();
        if (!profile) {
            blank(); line[0] = line[19] = '|'; put(3, "NOT USED BY SUSTAIN"); row(9, line);
        } else SHOW_SPRITES;
        draw_ball_page();
    } else if (page == 1) draw_stress_page();
    else if (page == 2) draw_timing_page();
    else draw_link_page();
}

void set_cpu_speed(void) {
    uint8_t mask;
    if (_cpu != CGB_TYPE || !!(KEY1_REG & 0x80u) == !!double_cpu) return;
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
    have_seq = window_len = window_pos = first_code = lost = frozen = 0;
    /* A stress test opens on the ball, which shows both consoles still agreeing. */
    page = profile ? 3u : 0u;
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

const char *menu_label[MENU_ROWS] = {"ROLE", "TEST", "RATE", "LINK", "CPU"};
const char *role_help[2][2] = {{"START THIS ONE FIRST", "THEN START THE HOST"}, {"START THIS WITHIN", "2 SEC OF THE PEER"}};
const char *test_help[5][2] = {
    {"PACKETS WITH CRC AND", "ORDER CHECKS"}, {"SCENE READY EVERY 32", "PEER STALLS 6 FRAMES"},
    {"3 BUSY FRAMES PER 8", "UPDATES IN TURNS"}, {"BOTH RUN A BALL AND", "COMPARE ITS STATE"},
    {"SCENES + LOAD + BALL", "THE HARDEST TEST"}
};
const char *rate_help[4][2] = {
    {"ONE BYTE THEN WAIT", "FOR THE NEXT FRAME"}, {"FOUR BYTES THEN WAIT", "FOR THE NEXT FRAME"},
    {"NO FRAME WAIT. 2 MS", "GAP BETWEEN BYTES"}, {"PEER IGNORES RATE", "THE HOST SETS IT"}
};
const char *link_help[2][2] = {{"MUST MATCH ON BOTH", "8192 BIT/S AT 1X"}, {"MUST MATCH ON BOTH", "262144 BIT/S AT 1X"}};
const char *cpu_help[2][2] = {{"CPU SPEED CAN DIFFER", "HOST CPU SETS WIRE"}, {"2X CPU DOUBLES THE", "HOST WIRE CLOCK"}};

const char *menu_value(uint8_t r) {
    switch (r) {
    case ROW_ROLE: return host ? "HOST" : "PEER";
    case ROW_TEST: return profiles[profile];
    case ROW_RATE: return host ? modes[rate_mode] : "SET BY HOST";
    case ROW_LINK: return fast ? "CGB FAST" : "NORMAL";
    default: return double_cpu ? "DOUBLE" : "NORMAL";
    }
}
void menu_help(const char **two) { row(10, two[0]); row(11, two[1]); }
void draw_menu_row(uint8_t r) {
    const char *value = menu_value(r);
    uint8_t length = strlen(value);
    blank(); line[0] = line[19] = '|';
    put(2, menu_label[r]); put(7, value);
    if (cursor == r) {
        line[1] = '}';
        /* Arrows mark the value that Left/Right changes. */
        if (length < 12) { line[6] = '{'; line[7 + length] = '}'; }
    }
    row(3 + r, line);
}
void change_setting(int8_t step) {
    switch (cursor) {
    case ROW_ROLE: host ^= 1u; break;
    case ROW_TEST: profile = (profile + 5u + step) % 5u; break;
    case ROW_RATE: rate_mode = (rate_mode + 3u + step) % 3u; break;
    case ROW_LINK: fast ^= 1u; break;
    default: if (_cpu == CGB_TYPE) double_cpu ^= 1u;
    }
}

void menu(void) {
    uint8_t previous = 0, keys, pressed, r, dirty = 1, blink = 2, phase;
    HIDE_SPRITES;
    clear_screen();
    row(0, "LINK SUSTAIN v1.2");
    draw_box(2, 8);
    while (joypad() & J_START) vsync();
    for (;;) {
        if (dirty) {
            dirty = 0;
            for (r = 0; r != MENU_ROWS; ++r) draw_menu_row(r);
            switch (cursor) {
            case ROW_ROLE: menu_help(role_help[host ? 1 : 0]); break;
            case ROW_TEST: menu_help(test_help[profile]); break;
            case ROW_RATE: menu_help(rate_help[host ? rate_mode : 3]); break;
            case ROW_LINK: menu_help(link_help[fast ? 1 : 0]); break;
            default: menu_help(cpu_help[double_cpu ? 1 : 0]);
            }
        }
        phase = (frame_now() >> 5) & 1u;
        if (phase != blink) { blink = phase; row(16, phase ? "    PRESS START" : ""); }
        vsync(); keys = joypad(); pressed = keys & ~previous; previous = keys;
        if (pressed & J_UP) { cursor = (cursor + MENU_ROWS - 1u) % MENU_ROWS; dirty = 1; }
        if (pressed & J_DOWN) { cursor = (cursor + 1u) % MENU_ROWS; dirty = 1; }
        if (pressed & J_LEFT) { change_setting(-1); dirty = 1; }
        if (pressed & J_RIGHT) { change_setting(1); dirty = 1; }
        if (pressed & J_START) break;
    }
    clear_screen(); start_test();
}

void main(void) {
    uint8_t keys, pressed, previous = 0, i;
    font_t handle;
    const palette_color_t colors[4] = {RGB(31,31,27), RGB(21,24,19), RGB(10,14,10), RGB(1,3,2)};
    const palette_color_t pass[4] = {RGB(31,31,27), RGB(21,24,19), RGB(6,16,8), RGB(1,9,3)};
    const palette_color_t fail[4] = {RGB(31,31,27), RGB(26,20,18), RGB(24,6,5), RGB(20,1,1)};
    const palette_color_t wait[4] = {RGB(31,31,27), RGB(26,24,16), RGB(16,12,2), RGB(12,7,0)};
    font_init(); handle = font_load(font_min);
    font_base = ((pmfont_handle)handle)->first_tile;
    if (_cpu == CGB_TYPE) {
        set_bkg_palette(0, 1, colors); set_sprite_palette(0, 1, colors);
        set_bkg_palette(PAL_PASS, 1, pass); set_bkg_palette(PAL_FAIL, 1, fail);
        set_bkg_palette(PAL_WAIT, 1, wait);
    }
    set_bkg_data(T_CURSOR, 8, ui_tiles);
    set_bkg_data(240, 6, frame_tiles);
    set_bkg_data(246, 6, punctuation_tiles);
    set_sprite_data(0, 1, ball_tiles); set_sprite_tile(0, 0);
    SHOW_BKG; DISPLAY_ON;
    add_SIO(serial_isr); add_SIO(nowait_int_handler);
    set_interrupts(VBL_IFLAG | SIO_IFLAG);
    menu(); shown_running = running; draw();
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
        if (running && (pressed & J_SELECT)) { frozen ^= 1u; draw(); }
        if (pressed & J_B) { running = 0; SC_REG = 0; frozen = 0; }
        /* A stop from B or from a serial hang both end up here. */
        if (shown_running && !running) { shown_running = 0; draw(); }
        if (!running && (pressed & J_START)) { menu(); previous = J_START; shown_running = running; draw(); }
        if (running && !frozen && (uint16_t)(frame_now() - last_draw) >= 30u) {
            last_draw = frame_now(); draw();
        }
    }
}
