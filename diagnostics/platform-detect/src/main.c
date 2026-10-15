#include <gbdk/platform.h>
#include <gb/cgb.h>
#include <gb/sgb.h>
#include <stdio.h>
#include <stdint.h>

#define REG_FF72 (*(volatile uint8_t *)0xFF72u)
#define REG_FF73 (*(volatile uint8_t *)0xFF73u)

typedef struct ProbeResult {
    uint8_t before;
    uint8_t first;
    uint8_t second;
    uint8_t passed;
} ProbeResult;

static ProbeResult probe_register(volatile uint8_t *reg, uint8_t first_pattern, uint8_t second_pattern) {
    ProbeResult result;

    result.before = *reg;

    *reg = first_pattern;
    result.first = *reg;

    *reg = second_pattern;
    result.second = *reg;

    *reg = result.before;

    result.passed = (result.first == first_pattern) && (result.second == second_pattern);
    return result;
}

static void print_hex8(uint8_t value) {
    static const char hex[] = "0123456789ABCDEF";
    putchar(hex[value >> 4]);
    putchar(hex[value & 0x0Fu]);
}

static void print_hardware(uint8_t is_sgb) {
    printf("HW: ");

    if (is_sgb) {
        if (_cpu == MGB_TYPE) printf("SGB2\n");
        else printf("SGB1\n");
    } else if (_cpu == DMG_TYPE) {
        printf("DMG\n");
    } else if (_cpu == MGB_TYPE) {
        printf("MGB\n");
    } else if (_cpu == CGB_TYPE) {
        if (_is_GBA == GBA_DETECTED) printf("GBA/CGB\n");
        else printf("CGB\n");
    } else {
        printf("UNKNOWN\n");
    }
}

static void print_probe(const char *name, ProbeResult *result, uint8_t p1, uint8_t p2) {
    printf("%s ", name);
    print_hex8(result->before);
    printf(" ");
    print_hex8(p1);
    printf(">");
    print_hex8(result->first);
    printf(" ");
    print_hex8(p2);
    printf(">");
    print_hex8(result->second);
    printf(" %s\n", result->passed ? "OK" : "FAIL");
}

void main(void) {
    uint8_t is_sgb;
    ProbeResult ff72;
    ProbeResult ff73;
    uint8_t binjgb_like;

    for (uint8_t i = 4u; i != 0u; --i) vsync();
    DISPLAY_ON;

    /* GBDK leaves the CGB palettes at their power-on white, so set them. */
    if (_cpu == CGB_TYPE) {
        static const palette_color_t text_palette[4] = {RGB_WHITE, RGB(21, 21, 21), RGB(10, 10, 10), RGB_BLACK};
        set_bkg_palette(0, 1, text_palette);
    }

    is_sgb = sgb_check();

    printf("PLATFORM DETECT 1.1\n");
    print_hardware(is_sgb);

    if (_cpu != CGB_TYPE) {
        printf("HOST: N/A\n\n");
        printf("FF72/73 probe is\n");
        printf("CGB-only.\n");
    } else {
        ff72 = probe_register((volatile uint8_t *)0xFF72u, 0x5Au, 0xA5u);
        ff73 = probe_register((volatile uint8_t *)0xFF73u, 0x3Cu, 0xC3u);

        binjgb_like = (!ff72.passed && !ff73.passed &&
                       ff72.first == 0xFFu && ff72.second == 0xFFu &&
                       ff73.first == 0xFFu && ff73.second == 0xFFu);

        if (binjgb_like) printf("HOST: BINJGB-LIKE\n");
        else if (ff72.passed && ff73.passed) printf("HOST: CGB-LIKE\n");
        else printf("HOST: OTHER/QUIRK\n");

        print_probe("72", &ff72, 0x5Au, 0xA5u);
        print_probe("73", &ff73, 0x3Cu, 0xC3u);

        printf("\nBINJGB-LIKE means\n");
        printf("this fingerprint,\n");
        printf("not every web emu.\n");
    }

    while (1) vsync();
}
