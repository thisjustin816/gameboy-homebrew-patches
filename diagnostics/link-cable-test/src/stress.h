#ifndef STRESS_H
#define STRESS_H
#include "protocol.h"
#define STRESS_UPDATE 1u
#define STRESS_SCENE 2u
#define STRESS_ACK 0x80u
#define STRESS_STALE 0u
#define STRESS_ACCEPT 1u
#define STRESS_STATE_ERROR 2u
#define STRESS_COMMAND_ERROR 3u
#define STRESS_EPOCH_ERROR 4u

typedef struct {
    uint16_t epoch;
    uint8_t command, x, y;
    int8_t vx, vy;
} stress_state;
void stress_init(stress_state *s);
void stress_next(stress_state *s, uint8_t profile);
uint16_t stress_hash(const stress_state *s);
void stress_payload(const stress_state *s, uint8_t profile, uint8_t ack, uint8_t *payload);
uint8_t stress_accept(stress_state *s, uint8_t profile, uint8_t host, const uint8_t *payload);
void stress_packet(uint8_t *p, uint32_t sequence, uint8_t role, const uint8_t *payload);
uint8_t stress_packet_check(const uint8_t *p, uint8_t role, uint32_t *sequence);
#endif
