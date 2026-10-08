#include "stress.h"

void stress_init(stress_state *s) {
    s->epoch = 0; s->command = STRESS_UPDATE;
    s->x = 80; s->y = 72; s->vx = 2; s->vy = -3;
}

void stress_next(stress_state *s, uint8_t profile) {
    int16_t x, y;
    ++s->epoch;
    s->command = ((profile == 1 || profile == 4) && !(s->epoch & 31u))
        ? STRESS_SCENE : STRESS_UPDATE;
    if (s->command == STRESS_SCENE) {
        s->x = 32u + (s->epoch & 63u); s->y = 72;
        s->vx = 2; s->vy = -3;
        return;
    }
    x = (int16_t)s->x + s->vx; y = (int16_t)s->y + s->vy;
    if (x < 8) { x = 16 - x; s->vx = -s->vx; }
    if (x > 151) { x = 302 - x; s->vx = -s->vx; }
    if (y < 16) { y = 32 - y; s->vy = -s->vy; }
    if (y > 127) { y = 254 - y; s->vy = -s->vy; }
    s->x = (uint8_t)x; s->y = (uint8_t)y;
}

uint16_t stress_hash(const stress_state *s) {
    uint8_t bytes[7];
    bytes[0] = (uint8_t)s->epoch; bytes[1] = (uint8_t)(s->epoch >> 8);
    bytes[2] = s->command; bytes[3] = s->x; bytes[4] = s->y;
    bytes[5] = (uint8_t)s->vx; bytes[6] = (uint8_t)s->vy;
    return packet_crc(bytes, 7);
}

void stress_payload(const stress_state *s, uint8_t profile, uint8_t ack, uint8_t *p) {
    uint16_t hash = stress_hash(s);
    p[0] = s->command | (ack ? STRESS_ACK : 0);
    p[1] = (uint8_t)s->epoch; p[2] = (uint8_t)(s->epoch >> 8);
    p[3] = (uint8_t)hash; p[4] = (uint8_t)(hash >> 8); p[5] = profile;
}

uint8_t stress_accept(stress_state *s, uint8_t profile, uint8_t host, const uint8_t *p) {
    uint16_t epoch = p[1] | ((uint16_t)p[2] << 8);
    uint16_t hash = p[3] | ((uint16_t)p[4] << 8);
    uint8_t command = p[0] & 0x7fu;
    stress_state next;
    if (p[5] != profile || !!(p[0] & STRESS_ACK) != !!host)
        return STRESS_COMMAND_ERROR;
    if (command != STRESS_UPDATE && command != STRESS_SCENE)
        return STRESS_COMMAND_ERROR;
    if (host) {
        if (epoch != s->epoch)
            return (int16_t)(epoch - s->epoch) > 0 ? STRESS_EPOCH_ERROR : STRESS_STALE;
        if (command != s->command) return STRESS_COMMAND_ERROR;
        return hash == stress_hash(s) ? STRESS_ACCEPT : STRESS_STATE_ERROR;
    }
    if (epoch == s->epoch) {
        if (command != s->command) return STRESS_COMMAND_ERROR;
        return hash == stress_hash(s) ? STRESS_STALE : STRESS_STATE_ERROR;
    }
    if (epoch != (uint16_t)(s->epoch + 1u))
        return (int16_t)(epoch - s->epoch) > 0 ? STRESS_EPOCH_ERROR : STRESS_STALE;
    next = *s;
    stress_next(&next, profile);
    if (command != next.command) return STRESS_COMMAND_ERROR;
    if (hash != stress_hash(&next)) return STRESS_STATE_ERROR;
    *s = next;
    return STRESS_ACCEPT;
}

void stress_packet(uint8_t *p, uint32_t sequence, uint8_t role, const uint8_t *payload) {
    uint8_t i;
    for (i = 0; i != 6; ++i) p[7+i] = payload[i];
    packet_wrap(p, sequence, role | 0x80u);
}

uint8_t stress_packet_check(const uint8_t *p, uint8_t role, uint32_t *sequence) {
    return packet_envelope(p, role | 0x80u, sequence);
}
