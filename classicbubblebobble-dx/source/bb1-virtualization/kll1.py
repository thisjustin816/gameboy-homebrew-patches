"""Replay the preserved KLL1 input sequence on the installed Gambatte core."""
from pathlib import Path

import numpy as np
import stable_retro
from stable_retro import _retro

BUTTONS = ["B", None, "SELECT", "START", "UP", "DOWN", "LEFT", "RIGHT", "A"]
GRID = ["BCDFGHJK", "LMNPQRST", "VWXZ1345"]


class Replay:
    def __init__(self, rom):
        cores = Path(stable_retro.__file__).parent / "cores"
        _retro.core_path(str(cores))
        _retro.RetroEmulator.load_core_info((cores / "gambatte.json").read_text())
        self.emulator = _retro.RetroEmulator(str(rom))
        self.data = _retro.GameDataGlue()
        self.emulator.configure_data(self.data)
        self.frame = 0

    def read(self, address):
        return int(self.data.memory.extract(address, "|u1"))

    def step(self, *buttons, frames=1):
        mask = np.zeros(9, dtype=np.uint8)
        for button in buttons:
            mask[BUTTONS.index(button)] = 1
        for _ in range(frames):
            self.emulator.set_button_mask(mask, 0)
            self.emulator.step()
            self.frame += 1

    def press(self, button, after=12):
        self.step(button, frames=4)
        self.step(frames=after)

    def start_round_three(self):
        self.start_password("KLL1")

    def open_password_menu(self):
        for _ in range(11):
            self.step(frames=55)
            self.step("START", frames=5)
        self.step(frames=55)
        self.step("DOWN", frames=5)
        self.step(frames=30)
        self.step("START", frames=5)
        self.step(frames=90)

    def start_password(self, word):
        self.open_password_menu()
        for character in word:
            row = next(i for i, line in enumerate(GRID) if character in line)
            column = GRID[row].index(character)
            for _ in range(row):
                self.press("DOWN")
            for _ in range(column):
                self.press("RIGHT")
            self.press("A", after=20)
            for _ in range(row):
                self.press("UP")
            for _ in range(column):
                self.press("LEFT")
        for _ in range(4):
            self.press("DOWN")
        self.step(frames=400)
        self.press("A", after=150)
        self.step("START", frames=5)

    def observe(self):
        return {
            "frame": self.frame,
            "round_index": self.read(0xC200),
            "marker": self.read(0xFFEB),
            "scheduler": [self.read(0xDE01), self.read(0xDE11)],
        }
