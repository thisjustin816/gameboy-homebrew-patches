#ifndef PROTOCOL_H
#define PROTOCOL_H
#include <stdint.h>
#define PACKET_SIZE 16u
uint16_t packet_crc(const uint8_t *p, uint8_t n);
uint8_t packet_pattern(uint32_t seq, uint8_t role, uint8_t index);
void packet_wrap(uint8_t *p, uint32_t seq, uint8_t role);
uint8_t packet_envelope(const uint8_t *p, uint8_t peer_role, uint32_t *seq);
void packet_make(uint8_t *p, uint32_t seq, uint8_t role);
uint8_t packet_check(const uint8_t *p, uint8_t peer_role, uint32_t *seq);
#endif
