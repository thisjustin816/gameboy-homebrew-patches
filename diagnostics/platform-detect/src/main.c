#include <gbdk/platform.h>
#include <gb/cgb.h>
#include <gb/sgb.h>
#include <gbdk/console.h>
#include <stdio.h>
#include <stdint.h>

typedef struct ProbeResult {
    uint8_t before;
    uint8_t first;
    uint8_t second;
    uint8_t passed;
} ProbeResult;

/* Each tell is a behavior a real CGB never shows. */
enum {
    TELL_72 = 0,  /* FF72/FF73 do not round-trip */
    TELL_74,      /* FF74 does not round-trip */
    TELL_75,      /* FF75 bits 4-6 do not round-trip */
    TELL_6C,      /* OPRI does not read FE after writing 00 */
    TELL_76,      /* PCM12/PCM34 do not read 00 with the APU idle */
    TELL_56,      /* RP does not read 2E, 3E or the FPGA's 02 after writing 00 */
    TELL_4F,      /* VBK does not read FE after writing 00 */
    TELL_4D,      /* KEY1 unused bits do not read 1 */
    TELL_4C,      /* KEY0 does not read FF after boot */
    TELL_01,      /* SB does not hold a written value */
    TELL_UNMAPPED,/* an unmapped register keeps a written value */
    TELL_SGB,     /* the SGB packet probe answered */
    TELL_COUNT
};

static const char *const tell_names[TELL_COUNT] = {
    "72", "74", "75", "6C", "76", "56", "4F", "4D", "4C", "01", "UN", "SGB"
};

/* SDCC drops a volatile read that follows a write to the same address and
   reuses the written value, so the write and read-back happen in asm. */
static uint8_t io_write_read(uint8_t lo, uint8_t value) __naked {
    (void)lo; (void)value;
    __asm
        ld c, a
        ld a, e
        ldh (c), a
        ldh a, (c)
        ret
    __endasm;
}

static uint8_t io_read(uint8_t lo) {
    return *(volatile uint8_t *)(0xFF00u + lo);
}

static void io_write(uint8_t lo, uint8_t value) {
    *(volatile uint8_t *)(0xFF00u + lo) = value;
}

static ProbeResult probe_register(uint8_t lo, uint8_t first_pattern, uint8_t second_pattern) {
    ProbeResult result;

    result.before = io_read(lo);
    result.first = io_write_read(lo, first_pattern);
    result.second = io_write_read(lo, second_pattern);
    io_write(lo, result.before);

    result.passed = (result.first == first_pattern) && (result.second == second_pattern);
    return result;
}

/* Writes value, returns the read-back, and restores the original. */
static uint8_t write_and_restore(uint8_t lo, uint8_t value) {
    uint8_t before = io_read(lo);
    uint8_t after = io_write_read(lo, value);
    io_write(lo, before);
    return after;
}

static void print_hex8(uint8_t value) {
    static const char hex[] = "0123456789ABCDEF";
    putchar(hex[value >> 4]);
    putchar(hex[value & 0x0Fu]);
}

/* CGB palettes: text, title bar, good, bad, section rule. Colors only
   reinforce words on screen, so the DMG layout reads the same. */
#define PAL_TEXT 0u
#define PAL_TITLE 1u
#define PAL_GOOD 2u
#define PAL_BAD 3u
#define PAL_RULE 4u

static const palette_color_t palettes[20] = {
    RGB_WHITE, RGB(21, 21, 21), RGB(10, 10, 10), RGB_BLACK,
    RGB(3, 5, 12), RGB(3, 5, 12), RGB(3, 5, 12), RGB_WHITE,
    RGB_WHITE, RGB(21, 21, 21), RGB(10, 10, 10), RGB(2, 14, 5),
    RGB_WHITE, RGB(21, 21, 21), RGB(10, 10, 10), RGB(24, 3, 3),
    RGB_WHITE, RGB(24, 24, 26), RGB(15, 15, 18), RGB(8, 8, 12)
};

/* One-pixel rule through the middle of the tile, in color 2. */
#define TILE_RULE 0x70u
static const uint8_t rule_tile[16] = {
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
};

static void paint(uint8_t x, uint8_t y, uint8_t width, uint8_t palette) {
    if (_cpu != CGB_TYPE) return;
    VBK_REG = VBK_ATTRIBUTES;
    for (; width != 0u; --width, ++x) set_bkg_tile_xy(x, y, palette);
    VBK_REG = VBK_TILES;
}

/* A section heading: the label set into a full-width rule. */
static void rule(uint8_t y, const char *label) {
    uint8_t x;
    for (x = 0u; x != 20u; ++x) set_bkg_tile_xy(x, y, TILE_RULE);
    gotoxy(2u, y);
    printf(" %s ", label);
    paint(0u, y, 20u, PAL_RULE);
}

static void field(uint8_t y, const char *label, const char *value, uint8_t palette) {
    gotoxy(1u, y);
    printf("%s", label);
    gotoxy(8u, y);
    printf("%s", value);
    paint(8u, y, 12u, palette);
}

static const char *hardware_name(uint8_t is_sgb) {
    /* A real SGB reports a DMG/MGB CPU, never CGB, so CGB wins over the probe. */
    if (is_sgb && _cpu != CGB_TYPE) return _cpu == MGB_TYPE ? "SGB2" : "SGB1";
    if (_cpu == DMG_TYPE) return "DMG";
    if (_cpu == MGB_TYPE) return "MGB";
    if (_cpu == CGB_TYPE) return _is_GBA == GBA_DETECTED ? "GBA/CGB" : "CGB";
    return "UNKNOWN";
}

/* "72 5A>5A A5>A5  OK" in columns 1-18. */
static void probe_row(uint8_t y, const char *name, ProbeResult *result, uint8_t p1, uint8_t p2) {
    gotoxy(1u, y);
    printf("%s ", name);
    print_hex8(p1);
    putchar('>');
    print_hex8(result->first);
    putchar(' ');
    print_hex8(p2);
    putchar('>');
    print_hex8(result->second);
    printf("  %s", result->passed ? "OK" : "NO");
    paint(17u, y, 2u, result->passed ? PAL_GOOD : PAL_BAD);
}

static void title(void) {
    gotoxy(1u, 0u);
    printf("PLATFORM DETECT");
    paint(0u, 0u, 20u, PAL_TITLE);
    gotoxy(15u, 17u);
    printf("V1.3");
    paint(15u, 17u, 4u, PAL_RULE);
}

void main(void) {
    uint8_t sgb_answered;
    ProbeResult ff72;
    ProbeResult ff73;
    ProbeResult ff74;
    uint8_t binjgb_like;
    uint8_t cgb_like;
    uint8_t oam[4];
    uint8_t unk75_ff;
    uint8_t key0;
    uint8_t pcm_ff;
    uint8_t vbk00;
    uint8_t ff4e_sticks;
    uint8_t ff57_sticks;
    uint16_t tells = 0u;
    uint8_t i;
    uint8_t failed;
    uint8_t shown;
    const char *match;
    uint8_t rp00;
    uint8_t likely;
    uint8_t emulator;

    /* GBDK leaves the CGB palettes at their power-on white. Palette RAM ignores
       writes while a line is drawn, so load it before the display is on. */
    if (_cpu == CGB_TYPE) set_bkg_palette(0u, 5u, palettes);
    set_bkg_data(TILE_RULE, 1u, rule_tile);

    for (i = 4u; i != 0u; --i) vsync();
    DISPLAY_ON;

    sgb_answered = sgb_check();

    title();

    if (_cpu != CGB_TYPE) {
        rule(2u, "SYSTEM");
        field(3u, "HW", hardware_name(sgb_answered), PAL_TEXT);
        field(4u, "HOST", "N/A", PAL_TEXT);
        field(5u, "SGB", sgb_answered ? "ANSWERED" : "NO", PAL_TEXT);
        rule(7u, "TELLS");
        gotoxy(1u, 8u);
        printf("CGB ONLY");
        while (1) vsync();
    }

    /* OAM is only readable outside modes 2 and 3, so read it right after VBlank starts. */
    vsync();
    for (i = 0u; i != 4u; ++i) oam[i] = *(volatile uint8_t *)(0xFEA0u + i);

    ff72 = probe_register(0x72u, 0x5Au, 0xA5u);
    ff73 = probe_register(0x73u, 0x3Cu, 0xC3u);
    ff74 = probe_register(0x74u, 0x5Au, 0xA5u);
    binjgb_like = (!ff72.passed && !ff73.passed &&
                   ff72.first == 0xFFu && ff72.second == 0xFFu &&
                   ff73.first == 0xFFu && ff73.second == 0xFFu);
    cgb_like = ff72.passed && ff73.passed;

    if (!cgb_like) tells |= 1u << TELL_72;
    if (!ff74.passed) tells |= 1u << TELL_74;

    unk75_ff = write_and_restore(0x75u, 0xFFu);
    if (write_and_restore(0x75u, 0x00u) != 0x8Fu || unk75_ff != 0xFFu) tells |= 1u << TELL_75;

    /* Leave OPRI at 00, not at the value read first: an emulator that misreads
       it as FF would take bit 0 back as DMG priority, and VBA-M also draws
       with the DMG palette while that bit is set. */
    if (io_write_read(0x6Cu, 0x00u) != 0xFEu) tells |= 1u << TELL_6C;

    pcm_ff = io_read(0x76u) == 0xFFu && io_read(0x77u) == 0xFFu;
    if (io_read(0x76u) != 0x00u || io_read(0x77u) != 0x00u) tells |= 1u << TELL_76;

    /* A CGB reads 2E (CGB-E) or 3E. The MiSTer-derived FPGA core the ModRetro
       Chromatic runs reads 02, which is hardware, not an emulator. */
    rp00 = write_and_restore(0x56u, 0x00u);
    if (rp00 != 0x2Eu && rp00 != 0x3Eu && rp00 != 0x02u) tells |= 1u << TELL_56;

    vbk00 = write_and_restore(0x4Fu, 0x00u);
    if (vbk00 != 0xFEu) tells |= 1u << TELL_4F;

    if ((write_and_restore(0x4Du, 0x00u) & 0x7Eu) != 0x7Eu) tells |= 1u << TELL_4D;

    key0 = io_read(0x4Cu);
    if (key0 != 0xFFu) tells |= 1u << TELL_4C;

    if (write_and_restore(0x01u, 0x00u) != 0x00u) tells |= 1u << TELL_01;

    ff4e_sticks = io_write_read(0x4Eu, 0x00u) != 0xFFu;
    ff57_sticks = io_write_read(0x57u, 0x00u) != 0xFFu;
    io_write(0x4Eu, 0xFFu);
    io_write(0x57u, 0xFFu);
    if (ff4e_sticks || ff57_sticks) tells |= 1u << TELL_UNMAPPED;

    if (sgb_answered) tells |= 1u << TELL_SGB;

    /* Signatures measured against each emulator's default CGB setup; see the README. */
    emulator = 1u;
    if (binjgb_like && pcm_ff) match = "BINJGB";
    else if (ff72.first == ff72.before && ff72.second == ff72.before && unk75_ff == 0x8Fu) match = "MGBA";
    else if (key0 == 0xFBu) match = "PYBOY";
    else if (ff57_sticks) match = "GEARBOY";
    else if (ff4e_sticks) match = "VBA-M";
    else if (oam[0] == 0x08u && oam[1] == 0x01u && oam[2] == 0xEFu && oam[3] == 0xDEu) match = "GAMBATTE";
    else if (vbk00 == 0x00u) match = "GB ONLINE";
    else {
        emulator = 0u;
        if (tells) match = "UNKNOWN";
        else if (rp00 == 0x02u) match = "MISTER FPGA";
        else match = "NONE";
    }

    failed = 0u;
    for (i = 0u; i != TELL_COUNT; ++i) {
        if (tells & (1u << i)) ++failed;
    }

    /* A named emulator counts even when every tell passes. */
    likely = tells || emulator;
    field(2u, "EMU", likely ? "LIKELY" : "NO TELLS", likely ? PAL_BAD : PAL_GOOD);
    field(3u, "MATCH", match, PAL_TEXT);

    rule(5u, "SYSTEM");
    field(6u, "HW", hardware_name(sgb_answered), PAL_TEXT);
    field(7u, "HOST", binjgb_like ? "BINJGB-LIKE" : cgb_like ? "CGB-LIKE" : "OTHER", cgb_like ? PAL_GOOD : PAL_BAD);
    field(8u, "SGB", sgb_answered ? "ANSWERED" : "NO", sgb_answered ? PAL_BAD : PAL_GOOD);

    rule(10u, "FF72 FF73");
    probe_row(11u, "72", &ff72, 0x5Au, 0xA5u);
    probe_row(12u, "73", &ff73, 0x3Cu, 0xC3u);

    rule(14u, "TELLS");
    gotoxy(1u, 15u);
    printf("%u OF %u FAILED", (unsigned int)failed, (unsigned int)TELL_COUNT);
    paint(1u, 15u, 18u, failed ? PAL_BAD : PAL_GOOD);
    /* Five codes fit the row; a count stands in for the rest. */
    gotoxy(1u, 16u);
    if (failed == 0u) printf("NONE");
    shown = 0u;
    for (i = 0u; i != TELL_COUNT && shown != 5u; ++i) {
        if (!(tells & (1u << i))) continue;
        printf("%s ", tell_names[i]);
        ++shown;
    }
    if (failed > shown) printf("+%u", (unsigned int)(failed - shown));

    while (1) vsync();
}
