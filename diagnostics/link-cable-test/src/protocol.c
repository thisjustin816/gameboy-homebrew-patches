#include "protocol.h"
uint16_t packet_crc(const uint8_t *p, uint8_t n) {
    uint16_t c = 0xffffu;
    uint8_t i;
    while (n--) {
        c ^= (uint16_t)*p++ << 8;
        for (i = 0; i != 8; ++i)
            c = (c & 0x8000u) ? (c << 1) ^ 0x1021u : (uint16_t)(c << 1);
    }
    return c;
}
uint8_t packet_pattern(uint32_t seq, uint8_t role, uint8_t index) {
    /* Alternating rails, alternating bits, then changing bits in every lane. */
    uint8_t s = (uint8_t)(seq ^ (seq >> 8) ^ (seq >> 16) ^ (seq >> 24));
    switch (index) {
    case 0: return (seq & 1u) ? 0x00u : 0xffu;
    case 1: return (seq & 1u) ? 0x55u : 0xaau;
    case 2: return (uint8_t)(1u << (seq & 7u));
    case 3: return (uint8_t)~(1u << (seq & 7u));
    case 4: return (uint8_t)(s * 37u + role * 83u);
    default: return (uint8_t)~(s * 37u + role * 83u);
    }
}
void packet_make(uint8_t *p, uint32_t seq, uint8_t role) {
    uint8_t i;
    uint16_t c;
    p[0] = 0xd3; p[1] = 0x91; p[2] = role;
    for (i = 0; i != 4; ++i) p[3+i] = (uint8_t)(seq >> (8u*i));
    for (i = 0; i != 6; ++i) p[7+i] = packet_pattern(seq, role, i);
    c = packet_crc(p, 13);
    p[13] = (uint8_t)c; p[14] = (uint8_t)(c >> 8); p[15] = 0x5a;
}
uint8_t packet_check(const uint8_t *p, uint8_t peer_role, uint32_t *seq) {
    uint8_t i;
    uint16_t c;
    if (p[0] != 0xd3 || p[1] != 0x91) return 1;
    c = packet_crc(p, 13);
    if (p[13] != (uint8_t)c || p[14] != (uint8_t)(c >> 8) || p[15] != 0x5a) return 1;
    if (p[2] != peer_role) return 2;
    *seq = 0;
    for (i = 0; i != 4; ++i) *seq |= (uint32_t)p[3+i] << (8u*i);
    for (i = 0; i != 6; ++i)
        if (p[7+i] != packet_pattern(*seq, peer_role, i)) return 3;
    return 0;
}
