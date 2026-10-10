"""Native ROM controls, CPU switching, state faults, and scene-ready delay."""
from pathlib import Path
import ctypes as c
import json
import shutil
import tempfile
from pyboy import PyBoy
from rom_helpers import configure, has_color, is_green, is_red, load_symbols, read_value, screen_row
from stress_helpers import State, build_library

ROOT = Path(__file__).resolve().parents[1]


with tempfile.TemporaryDirectory() as temp:
    folder = Path(temp); lib = build_library(folder)
    symbols = load_symbols(ROOT / "link-sustain.noi")
    rom = folder / "test.gbc"; shutil.copyfile(ROOT / "link-sustain.gbc", rom)
    p = PyBoy(str(rom), window="null", sound_emulated=False)
    p.set_emulation_speed(0)
    def get(name, size=1): return read_value(p, symbols, name, size)
    def press(button):
        p.button_press(button); p.tick(8, True); p.button_release(button); p.tick(8, True)
    def inject(state, profile=1, ack=False, fault=None):
        payload = (c.c_uint8 * 6)(); packet = (c.c_uint8 * 16)()
        lib.stress_payload(c.byref(state), profile, int(ack), payload)
        if fault == "state": payload[3] ^= 1
        if fault == "type": payload[0] ^= 3
        inject.sequence += 1
        lib.stress_packet(packet, inject.sequence, 2 if ack else 1, payload)
        index = get("wr")
        for byte in packet:
            p.memory[symbols['_ring'] + index] = byte; index = (index + 1) & 127
        p.memory[symbols['_wr']] = index
    inject.sequence = -1
    try:
        p.tick(150, True)
        configure(get, press, host=False, test=1, cpu=1)
        press("start")
        assert p.memory[0xff4d] & 0x80
        assert get("running") == 1
        peer = State(); lib.stress_init(c.byref(peer))
        lib.stress_next(c.byref(peer), 1); inject(peer); p.tick(2, True)
        assert get("updates", 4) == 1 and get("simulation", 2) == 1
        lib.stress_next(c.byref(peer), 1); inject(peer, fault="state"); p.tick(2, True)
        assert get("state_errors", 4) == 1 and get("first_code") == 9
        assert get("first_seq", 4) == 1
        assert get("first_wanted_hash", 2) ^ get("first_got_hash", 2) == 1
        assert get("simulation", 2) == 1
        inject(peer); p.tick(2, True)
        assert get("simulation", 2) == 2
        for _ in range(3, 32):
            lib.stress_next(c.byref(peer), 1); inject(peer); p.tick(2, True)
        lib.stress_next(c.byref(peer), 1); inject(peer); p.tick(2, True)
        assert get("scene_pending") == 1 and get("simulation", 2) == 31
        p.tick(6, True)
        assert get("scene_pending") == 0 and get("simulation", 2) == 32
        assert get("barriers", 4) == 1 and get("crc_errors", 4) == 0
        press("right"); assert get("page") == 1
        p.screen.image.save(ROOT / "build" / "stress-results.png")
        press("right"); assert get("page") == 2
        p.screen.image.save(ROOT / "build" / "timing-results.png")
        press("right"); assert get("page") == 3
        p.screen.image.save(ROOT / "build" / "ball-view.png")
        press("b"); assert get("running") == 0
        assert get("first_code") == 9
        # The verdict stays on every page after a stop, in red with the FAIL text.
        stopped = screen_row(p, 2, 7)
        assert has_color(screen_row(p, 3), is_red)
        for _ in range(4):
            press("right")
            assert screen_row(p, 2, 7) == stopped
            assert has_color(screen_row(p, 3), is_red)
        press("start"); assert get("running") == 0
        p.tick(30, True)
        configure(get, press, host=True, test=1, cpu=0)
        press("start")
        assert not (p.memory[0xff4d] & 0x80)
        assert get("running") == 1 and get("state_errors", 4) == 0
        inject.sequence = -1
        host = State(); lib.stress_init(c.byref(host)); lib.stress_next(c.byref(host), 1)
        inject(host, ack=True, fault="type"); p.tick(2, True)
        assert get("barrier_errors", 4) == 1 and get("waiting") == 1
        assert get("updates", 4) == 0 and get("simulation", 2) == 1
        inject(host, ack=True); p.tick(12, True)
        assert get("updates", 4) == 1 and get("simulation", 2) == 2
        p.tick(180, True)
        assert get("deadlines", 4) == 1 and get("max_reply", 2) > 0
        p.tick(90, True); assert get("deadlines", 4) == 1
        lib.stress_next(c.byref(host), 1); inject(host, ack=True); p.tick(12, True)
        assert get("updates", 4) == 2 and get("lost") == 0
        assert get("max_recovery", 2) >= 120 and get("first_code") == 10
        # A run with no error and ten minutes behind it reads PASS in green.
        press("b"); press("start")
        configure(get, press, host=True, test=0, rate=1, cpu=0)
        press("start"); p.tick(5, True)
        assert get("running") == 1 and get("first_code") == 0
        assert not has_color(screen_row(p, 3), is_green)
        p.memory[symbols["_good"]:symbols["_good"] + 4] = [1, 0, 0, 0]
        p.memory[symbols["_elapsed_seconds"]:symbols["_elapsed_seconds"] + 4] = [0x58, 0x02, 0, 0]
        p.tick(40, True)
        assert get("first_code") == 0
        assert has_color(screen_row(p, 3), is_green)
        p.screen.image.save(ROOT / "build" / "pass.png")
    finally:
        p.stop(save=False)
ROOT.joinpath("build", "feature-results.json").write_text(json.dumps({
    "controls_cpu": "menu profile/CPU settings, KEY1 double/normal switch, pages, stop and restart passed",
    "state_fault": "CRC-valid wrong state rejected without advancing; valid retransmission accepted",
    "scene": "peer retains previous epoch during six-frame ready delay; accepts scene afterward",
    "typed_ack": "wrong reply type with current epoch rejected; matching acknowledgement advances host",
    "timing": "one late count per stalled command, reply latency and recovery interval recorded; first failure retained"
}, indent=2) + "\n")
print("Native features: CPU switching, state-fault recovery, scene delay and typed acknowledgements passed")
