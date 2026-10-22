"""The cartridge header's two checksums."""

OFF_HDR_SUM = 0x14D
OFF_GLOBAL_SUM = 0x14E


def header_checksum(rom):
    """The byte the boot ROM checks at $014D, over $0134-$014C."""
    x = 0
    for b in rom[0x134:OFF_HDR_SUM]:
        x = (x - b - 1) & 0xFF
    return x


def global_checksum(rom):
    """The 16-bit sum of every byte except the two checksum bytes themselves."""
    return (sum(rom) - rom[OFF_GLOBAL_SUM] - rom[OFF_GLOBAL_SUM + 1]) & 0xFFFF
