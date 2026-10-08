#include <gb/gb.h>
#include <gb/cgb.h>
#include <gbdk/font.h>
#include <stdio.h>
#include <string.h>
#include "protocol.h"

/* No send_byte()/receive_byte(): their default ISR owns SB/SC. */
volatile uint8_t running, host = 1, fast, done;
volatile uint8_t tx[4][PACKET_SIZE], ready[4], active, txpos;
volatile uint8_t ring[128], wr, rd;
volatile uint16_t overflow, underrun;
uint8_t rate_mode = 1, frozen, lost, have_seq, window[16], candidate[16], window_len, window_pos;
uint32_t next_tx, expected, good, crc_errors, seq_errors, data_errors;
uint32_t timeouts, first_sec, first_seq, first_wanted_seq, elapsed_seconds, second_phase;
uint16_t old_time, last_good, last_draw, first_expected_crc, first_received_crc;
uint8_t first_code;
const char *modes[] = {"1 BYTE/FRAME", "4 BYTE BURST", "CONTINUOUS"};
const char *failures[] = {"NONE", "CRC/FRAME", "ROLE", "PAYLOAD", "SEQUENCE", "NO SYNC", "RX OVERRUN", "TX UNDERRUN", "SERIAL HANG"};

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
        n = (active + 1u) & 3u;
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

void refill(void) {
    uint8_t b, i;
    /* Keep three packets ahead so a redraw or bad-frame scan has headroom. */
    for (i = 1; i != 4; ++i) {
        b = (active + i) & 3u;
        if (!ready[b]) {
            packet_make((uint8_t *)tx[b], next_tx++, host ? 1u : 2u);
            ready[b] = 1;
            return;
        }
    }
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
        code = packet_check(candidate, host ? 2u : 1u, &seq);
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
            ++good; last_good = frame_now(); lost = 0;
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
        tiles[i] = font_min[2u + c] + font_base;
    }
    set_bkg_tiles(0, y, 20, 1, tiles);
    if (running) service();
}
void clear_screen(void) {
    uint8_t y;
    for (y = 0; y != 18; ++y) row(y, "");
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
    CRITICAL { ov = overflow; un = underrun; }
    row(0, "LINK SUSTAIN v1.0");
    strcpy(line, host ? "HOST " : "PEER ");
    strcat(line, fast ? "FAST " : "8192 ");
    strcat(line, frozen ? "HOLD" : "LIVE"); row(1, line);
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
    } else {
        strcpy(line, "CRC "); strcat(line, number(first_expected_crc, 16));
        strcat(line, ">"); strcat(line, number(first_received_crc, 16)); row(14, line);
    }
    row(15, "SELECT HOLD DISPLAY");
    row(16, "B STOP: KEEPS DATA");
    row(17, "START MENU IF STOP");
}

void start_test(void) {
    uint8_t b;
    running = 0; SC_REG = 0;
    good = crc_errors = seq_errors = data_errors = timeouts = 0;
    elapsed_seconds = second_phase = first_sec = first_seq = first_wanted_seq = 0;
    overflow = underrun = first_expected_crc = first_received_crc = 0;
    wr = rd = active = txpos = done = 0;
    have_seq = window_len = window_pos = first_code = lost = frozen = 0;
    for (b = 0; b != 4; ++b) {
        packet_make((uint8_t *)tx[b], b, host ? 1u : 2u);
        ready[b] = 1;
    }
    next_tx = 4;
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
    delay(2);
    return 1;
}

void menu(void) {
    uint8_t previous = 0, keys, pressed;
    clear_screen();
    row(0, "LINK SUSTAIN v1.0");
    row(2, "2 CONSOLES, SAME ROM");
    row(3, "ONE HOST + ONE PEER");
    row(4, "START PEER FIRST");
    row(5, "THEN START HOST");
    row(12, "LEFT/RIGHT: ROLE");
    row(13, "UP/DOWN: HOST RATE");
    row(14, "SELECT: CLOCK SPEED");
    row(15, "MATCH SPEED ON BOTH");
    row(17, "START: NEW TEST");
    while (joypad() & J_START) vsync();
    for (;;) {
        row(7, host ? "ROLE  HOST" : "ROLE  PEER");
        strcpy(line, "RATE  "); strcat(line, modes[rate_mode]); row(8, line);
        row(9, fast ? "CLOCK CGB 262144" : "CLOCK NORMAL 8192");
        vsync(); keys = joypad(); pressed = keys & ~previous; previous = keys;
        if (pressed & (J_LEFT | J_RIGHT)) host ^= 1u;
        if (pressed & J_UP) rate_mode = (rate_mode + 1u) % 3u;
        if (pressed & J_DOWN) rate_mode = (rate_mode + 2u) % 3u;
        if ((pressed & J_SELECT) && _cpu == CGB_TYPE) fast ^= 1u;
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
    if (_cpu == CGB_TYPE) set_bkg_palette(0, 1, colors);
    SHOW_BKG; DISPLAY_ON;
    add_SIO(serial_isr); add_SIO(nowait_int_handler);
    set_interrupts(VBL_IFLAG | SIO_IFLAG);
    menu(); draw();
    for (;;) {
        if (running) {
            if (host) {
                for (i = 0; i != (rate_mode == 0 ? 1u : 4u) && running; ++i)
                    if (!transfer()) break;
                if (rate_mode != 2) vsync();
            } else vsync();
            service();
        } else vsync();
        keys = joypad(); pressed = keys & ~previous; previous = keys;
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
