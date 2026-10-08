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
