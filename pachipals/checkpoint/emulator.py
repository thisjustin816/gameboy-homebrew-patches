"""Isolated PyBoy instances for checkpoint regressions."""

from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from pyboy import PyBoy
from build import PROFILES, identity

BUTTONS = ("left", "right", "up", "down", "a", "b", "start", "select")


@contextmanager
def emulator(rom):
    data = Path(rom).read_bytes()
    known = [PROFILES["input"], *PROFILES["profiles"].values(), *PROFILES["controls"].values()]
    actual = identity(data)
    if not any(all(actual[key] == p[key] for key in ("sha256", "md5")) for p in known):
        raise ValueError(f"Unsupported checkpoint ROM: {actual}")
    with TemporaryDirectory(prefix="pachipals-") as folder:
        copy = Path(folder) / "test.gbc"
        copy.write_bytes(data)
        player = PyBoy(str(copy), window="null", sound_emulated=False)
        try:
            yield player
        finally:
            player.stop(save=False)


def load_state(player, state):
    data = Path(state).read_bytes()
    if identity(data)["sha256"] not in PROFILES["states"].values():
        raise ValueError("Unsupported checkpoint state")
    with Path(state).open("rb") as source:
        player.load_state(source)
    for button in BUTTONS:
        player.button_release(button)
