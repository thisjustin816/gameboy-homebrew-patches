"""Read GBDK symbols and little-endian cartridge state."""
import re


def load_symbols(path):
    symbols = {}
    for line in path.read_text().splitlines():
        match = re.fullmatch(r"DEF (\S+) (0x[0-9A-Fa-f]+)", line)
        if match:
            symbols[match[1]] = int(match[2], 16)
    if "_running" not in symbols:
        raise ValueError(f"Missing cartridge symbols in {path}; rebuild the ROM")
    return symbols


def read_value(emulator, symbols, name, size=1):
    address = symbols["_" + name]
    return int.from_bytes(bytes(emulator.memory[address:address + size]), "little")


def configure(get, press, host=True, test=0, rate=1, link=0, cpu=0):
    """Set the menu rows (ROLE, TEST, RATE, LINK, CPU) with the cursor and Left/Right."""
    def set_value(row, name, target):
        while get("cursor") != row:
            press("down")
        for _ in range(5):
            if get(name) == target:
                return
            press("right")
        assert get(name) == target, f"menu row {name} never reached {target}"
    set_value(0, "host", int(host))
    set_value(1, "profile", test)
    set_value(2, "rate_mode", rate)
    set_value(3, "fast", link)
    set_value(4, "double_cpu", cpu)


def configure_from_power_on(press, host=True, test=0, rate=1, link=0, cpu=0):
    """Menu presses for a fresh boot (cursor on ROLE; HOST, ALL STRESS, 4 BYTE BURST, NORMAL).

    The paired harness cannot read the cartridge's memory before its run ends, so it
    presses blind, in the order of the rows.
    """
    if not host:
        press("left")
    press("down")
    for _ in range((test - 4) % 5):
        press("right")
    press("down")
    for _ in range((rate - 1) % 3):
        press("right")
    press("down")
    if link:
        press("right")
    press("down")
    if cpu:
        press("right")


def screen_row(emulator, tile_row, columns=20):
    """Pixels of one tile row of the 20x18 screen, as an RGB image crop."""
    image = emulator.screen.image.convert("RGB")
    return image.crop((0, tile_row * 8, columns * 8, tile_row * 8 + 8))


def has_color(image, test):
    """True when any pixel (r, g, b) satisfies test."""
    return any(test(*pixel) for pixel in image.getdata())


def is_red(r, g, b):
    return r > 140 and g < 60 and b < 60


def is_green(r, g, b):
    return g > r + 30 and g > b + 20 and r < 80
