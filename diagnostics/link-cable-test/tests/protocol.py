"""Compile and exercise the same packet implementation used by the cartridge."""
from pathlib import Path
import ctypes as c
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as temp:
    libpath = Path(temp) / "protocol.so"
    subprocess.run(["cc", "-std=c99", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                    str(ROOT / "src" / "protocol.c"), "-o", str(libpath)], check=True)
    lib = c.CDLL(str(libpath))
    packet = (c.c_uint8 * 16)()
    result = c.c_uint32()
    lib.packet_make.argtypes = [c.POINTER(c.c_uint8), c.c_uint32, c.c_uint8]
    lib.packet_check.argtypes = [c.POINTER(c.c_uint8), c.c_uint8, c.POINTER(c.c_uint32)]
    lib.packet_crc.argtypes = [c.POINTER(c.c_uint8), c.c_uint8]
    lib.packet_crc.restype = c.c_uint16
    vector = (c.c_uint8 * 9)(*b"123456789")
    assert lib.packet_crc(vector, 9) == 0x29B1  # CRC-16/CCITT-FALSE known vector.
    for role in (1, 2):
        for seq in list(range(256)) + [0xffff, 0x10000, 0xffffff, 0x1000000, 0xffffffff]:
            lib.packet_make(packet, seq, role)
            assert lib.packet_check(packet, role, c.byref(result)) == 0
            assert result.value == seq
            assert lib.packet_check(packet, 3 - role, c.byref(result)) == 2
            for bit in range(128):
                packet[bit // 8] ^= 1 << (bit % 8)
                assert lib.packet_check(packet, role, c.byref(result)) != 0
                packet[bit // 8] ^= 1 << (bit % 8)
    # A valid CRC with the wrong deterministic payload is a DATA failure.
    lib.packet_make(packet, 42, 1)
    packet[9] ^= 4
    crc = lib.packet_crc(packet, 13)
    packet[13], packet[14] = crc & 255, crc >> 8
    assert lib.packet_check(packet, 1, c.byref(result)) == 3
print("Protocol: known CRC vector, sequence boundaries, roles, every single-bit error, payload validation passed")
