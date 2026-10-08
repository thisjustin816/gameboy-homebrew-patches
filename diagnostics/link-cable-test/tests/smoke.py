"""Header, real boot/input, and disconnected-link checks on the built ROM."""
from pathlib import Path
import json
from pyboy import PyBoy
from rom_helpers import load_symbols, read_value

ROOT = Path(__file__).resolve().parents[1]
ROOT.joinpath("build").mkdir(exist_ok=True)
rom = ROOT / "link-sustain.gbc"
data = rom.read_bytes()
assert len(data) == 32768 and data[0x143] == 0xC0 and data[0x147] == 0
header = 0
for byte in data[0x134:0x14D]: header = (header - byte - 1) & 255
assert header == data[0x14D]
assert (sum(data[:0x14E]) + sum(data[0x150:])) & 65535 == int.from_bytes(data[0x14E:0x150], "big")
symbols = load_symbols(ROOT / "link-sustain.noi")

evidence = {}
for role in ("host", "peer"):
    p = PyBoy(str(rom), window="null", sound_emulated=False)
    p.set_emulation_speed(0)
    def get(name, size=1):
        return read_value(p, symbols, name, size)
    def press(button):
        p.button_press(button); p.tick(8); p.button_release(button); p.tick(8)
    try:
        p.tick(150)
        assert get("running") == 0
        if role == "host":
            p.screen.image.save(str(ROOT / "build" / "menu.png"))
            press("select"); assert get("fast") == 1
            press("select"); assert get("fast") == 0
            press("up"); assert get("rate_mode") == 2
            press("down"); assert get("rate_mode") == 1
        else: press("left")
        assert get("host") == (role == "host")
        press("start"); p.tick(240)
        assert get("running") == 1 and get("good", 4) == 0
        assert get("timeouts", 4) == 1 and get("first_code") == 5
        assert get("overflow", 2) == get("underrun", 2) == 0
        p.screen.image.save(str(ROOT / "build" / f"no-cable-{role}.png"))
        press("select"); assert get("frozen") == 1
        p.tick(90); assert get("timeouts", 4) == 1
        press("select"); assert get("frozen") == 0
        press("b"); assert get("running") == 0
        p.tick(90); assert get("first_code") == 5 and get("timeouts", 4) == 1
        press("start"); assert get("running") == 0
        press("start"); assert get("running") == 1 and get("first_code") == 0
        evidence[role] = "boot, controls, one no-sync episode, hold, stop, new-test reset passed"
    finally:
        p.stop(save=False)
ROOT.joinpath("build", "smoke-results.json").write_text(json.dumps(evidence, indent=2) + "\n")
print("ROM header/checksums and disconnected host/peer smoke checks passed")
