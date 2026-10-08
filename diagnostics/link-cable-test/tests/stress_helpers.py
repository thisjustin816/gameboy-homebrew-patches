"""Host ABI and build helper for the cartridge stress protocol."""
from pathlib import Path
import ctypes as c
import subprocess

ROOT = Path(__file__).resolve().parents[1]


class State(c.Structure):
    _fields_ = [("epoch", c.c_uint16), ("command", c.c_uint8),
                ("x", c.c_uint8), ("y", c.c_uint8), ("vx", c.c_int8), ("vy", c.c_int8)]


def build_library(folder, broken=False):
    source = ROOT / "src" / "stress.c"
    if broken:
        source = folder / "missing-type-guard.c"
        source.write_text((ROOT / "src" / "stress.c").read_text().replace(
            "if (command != s->command) return STRESS_COMMAND_ERROR;", "/* injected fault */"))
    target = folder / ("broken.so" if broken else "stress.so")
    subprocess.run(["cc", "-std=c99", "-Wall", "-Wextra", "-Werror", "-shared", "-fPIC",
                    "-I", str(ROOT / "src"), str(source), str(ROOT / "src" / "protocol.c"),
                    "-o", str(target)], check=True)
    lib = c.CDLL(str(target))
    lib.stress_init.argtypes = [c.POINTER(State)]
    lib.stress_next.argtypes = [c.POINTER(State), c.c_uint8]
    lib.stress_payload.argtypes = [c.POINTER(State), c.c_uint8, c.c_uint8, c.POINTER(c.c_uint8)]
    lib.stress_accept.argtypes = [c.POINTER(State), c.c_uint8, c.c_uint8, c.POINTER(c.c_uint8)]
    lib.stress_accept.restype = c.c_uint8
    lib.stress_packet.argtypes = [c.POINTER(c.c_uint8), c.c_uint32, c.c_uint8, c.POINTER(c.c_uint8)]
    lib.stress_packet_check.argtypes = [c.POINTER(c.c_uint8), c.c_uint8, c.POINTER(c.c_uint32)]
    lib.stress_packet_check.restype = c.c_uint8
    return lib
