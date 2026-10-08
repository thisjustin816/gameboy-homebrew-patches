"""Exercise the cartridge's shared-state and scene acknowledgement rules."""
from pathlib import Path
import ctypes as c
import tempfile

from stress_helpers import State, build_library


def wrong_type_reply(lib):
    s = State(); lib.stress_init(c.byref(s))
    for _ in range(32): lib.stress_next(c.byref(s), 1)
    payload = (c.c_uint8 * 6)()
    lib.stress_payload(c.byref(s), 1, 1, payload)
    payload[0] = 0x81  # Gameplay reply with the current scene token and hash.
    return lib.stress_accept(c.byref(s), 1, 1, payload)


with tempfile.TemporaryDirectory() as temp:
    folder = Path(temp); lib = build_library(folder)
    assert wrong_type_reply(build_library(folder, broken=True)) == 1
    assert wrong_type_reply(lib) == 3
    for profile in (1, 2, 3, 4):
        host, peer = State(), State()
        lib.stress_init(c.byref(host)); lib.stress_init(c.byref(peer))
        payload = (c.c_uint8 * 6)()
        for step in range(65569):
            lib.stress_next(c.byref(host), profile)
            lib.stress_payload(c.byref(host), profile, 0, payload)
            assert lib.stress_accept(c.byref(peer), profile, 0, payload) == 1
            assert bytes(host) == bytes(peer)
            assert 8 <= peer.x <= 151 and 16 <= peer.y <= 127
            assert peer.command == (2 if profile in (1, 4) and peer.epoch % 32 == 0 else 1)
            before = bytes(peer)
            assert lib.stress_accept(c.byref(peer), profile, 0, payload) == 0
            assert bytes(peer) == before
            lib.stress_payload(c.byref(peer), profile, 1, payload)
            assert lib.stress_accept(c.byref(host), profile, 1, payload) == 1
        before = bytes(host)
        payload[3] ^= 1
        assert lib.stress_accept(c.byref(host), profile, 1, payload) == 2
        assert bytes(host) == before
        payload[3] ^= 1; payload[5] = 0
        assert lib.stress_accept(c.byref(host), profile, 1, payload) == 3
        payload[5] = profile; payload[1] += 1
        assert lib.stress_accept(c.byref(host), profile, 1, payload) == 4
        payload[1] -= 2
        assert lib.stress_accept(c.byref(host), profile, 1, payload) == 0
    packet = (c.c_uint8 * 16)(); seq = c.c_uint32()
    lib.stress_packet(packet, 42, 1, payload)
    assert lib.stress_packet_check(packet, 1, c.byref(seq)) == 0 and seq.value == 42
    assert lib.stress_packet_check(packet, 2, c.byref(seq)) == 2
    for bit in range(128):
        packet[bit // 8] ^= 1 << (bit % 8)
        assert lib.stress_packet_check(packet, 1, c.byref(seq)) != 0
        packet[bit // 8] ^= 1 << (bit % 8)
print("Stress: typed replies, state faults, update order, duplicate requests, CPU-independent simulation and epoch wrap passed")
