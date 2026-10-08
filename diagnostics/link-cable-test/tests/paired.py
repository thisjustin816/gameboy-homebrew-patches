"""Execute the built ROM in two PyBoy processes using its byte-link transport.

This validates protocol/ISR integration. Physical serial timing is unverified.
PyBoy's shared-memory transport ignores clock roles and CGB fast speed.
"""
from pathlib import Path
import multiprocessing as mp
import json
import sys
import shutil
import importlib.util
from rom_helpers import load_symbols, read_value

ROOT = Path(__file__).resolve().parents[1]
TARGET = 384


def source_emulator():
    """Use the installed PyBoy Python sources without altering the installation."""
    spec = importlib.util.find_spec("pyboy")
    if spec is None:
        raise RuntimeError("Paired checks require PyBoy (including its Python sources)")
    source = Path(spec.origin).parent
    parent = ROOT / "build" / "emulator-source"
    destination = parent / "pyboy"
    if source != destination:
        for file in source.rglob("*"):
            if file.is_file() and file.suffix in (".py", ".bin", ".txt", ".json"):
                target = destination / file.relative_to(source)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(file, target)
    sys.path.insert(0, str(parent))


def worker(role, buffer, fault, rate, output):
    from pyboy import PyBoy
    from pyboy.core import serial
    # The shipped transport uses 128 CPU cycles/bit; GB normal speed is 512.
    # Source-mode emulation lets the harness correct this test-only constant.
    serial.CYCLES_8192HZ = 512
    original = serial.SerialSharedMemory
    class PacedPeer(original):
        def set_SC(self, value):
            super().set_SC(value)
            if self.transfer_enabled and not self.internal_clock:
                # Synthetic host gap: PyBoy otherwise clocks the peer during
                # the host's idle time. This is protocol testing, not timing.
                self.clock_target += 8192
                self._cycles_to_interrupt = self.clock_target - self.clock
    serial.SerialSharedMemory = PacedPeer
    p = PyBoy(str(ROOT / "link-sustain.gbc"), window="null", sound_emulated=False,
              serial_shared_memory=buffer, serial_interrupt_based=True)
    p.set_emulation_speed(0)
    syms = load_symbols(ROOT / "link-sustain.noi")
    p.tick(150)
    def press(button):
        p.button_press(button); p.tick(1); p.button_release(button); p.tick(1)
    if role == "peer": press("left")
    for _ in range((rate - 1) % 3): press("up")
    press("start")
    # Constructor slot order is independent of role; the shared flag ends both.
    frames = 0
    while buffer.connected and frames < 12000:
        p.tick(1); frames += 1
    result = {}
    for name, size in [("good", 4), ("crc_errors", 4), ("seq_errors", 4),
                       ("data_errors", 4), ("timeouts", 4), ("first_code", 1),
                       ("overflow", 2), ("underrun", 2), ("expected", 4), ("next_tx", 4), ("first_seq", 4)]:
        result[name] = read_value(p, syms, name, size)
    result["frames"] = frames
    p.screen.image.save(str(ROOT / "build" / f"{fault}-{rate}-{role}.png"))
    output.put((role, result))
    p.stop(save=False)


def run(fault="clean", rate=1):
    from pyboy.core.serial import SerialSharedMemoryBuffer
    class TestBuffer(SerialSharedMemoryBuffer):
        def __init__(self):
            super().__init__()
            self.counts = mp.Array("i", [0, 0])
            self.finished = mp.Value("i", 0)
            self.initial = mp.Value("i", 0)
            self.sync_calls = 0

        def read(self, slot):
            value = super().read(slot)
            # The first two reads are constructor slot assignment, not bytes.
            with self.initial.get_lock():
                if self.initial.value < 2:
                    assigned_slot = self.initial.value
                    self.initial.value += 1
                    return assigned_slot
            receiver = 1 - slot
            self.counts[receiver] += 1
            count = self.counts[receiver]
            if fault == "corrupt" and count == 200:
                value ^= 4
            if fault == "gap" and 150 <= count < 900:
                value = 255
            if count >= (1184 if fault == "gap" else TARGET):
                self.finished.value = 1
            return value

        def synchronize(self):
            super().synchronize()
            self.sync_calls += 1
            # One constructor barrier, then two barriers per completed byte.
            # Stop only after the second; stopping after the first strands
            # the other worker between writing and reading its final byte.
            if self.sync_calls >= 3 and self.sync_calls % 2 and self.finished.value:
                self.connected = False

    buffer = TestBuffer()
    output = mp.Queue()
    processes = [mp.Process(target=worker, args=(role, buffer, fault, rate, output))
                 for role in ("host", "peer")]
    try:
        for p in processes: p.start()
        results = dict(output.get(timeout=120) for _ in processes)
        for p in processes:
            p.join(timeout=5)
            if p.is_alive(): raise AssertionError("owned test worker stalled")
            assert p.exitcode == 0
    finally:
        for p in processes:
            if p.is_alive(): p.terminate(); p.join(timeout=5)
        buffer.close()
    print(fault, rate, results, flush=True)
    for role, r in results.items():
        assert r["good"] > 15, (role, r)
        assert r["overflow"] == r["underrun"] == r["data_errors"] == 0, (role, r)
        if fault == "clean":
            assert r["crc_errors"] == r["seq_errors"] == r["timeouts"] == r["first_code"] == 0, (role, r)
        elif fault == "corrupt":
            assert r["crc_errors"] >= 1 and r["seq_errors"] >= 1 and r["first_code"] == 1, (role, r)
        elif fault == "gap":
            assert r["timeouts"] >= 1 and r["seq_errors"] >= 1 and r["first_code"] != 0, (role, r)
    return results


if __name__ == "__main__":
    mp.set_start_method("fork")
    source_emulator()
    evidence = {}
    for fault, rate in [("gap", 2), ("clean", 0), ("clean", 1), ("clean", 2), ("corrupt", 1)]:
        evidence[f"{fault}-{rate}"] = run(fault, rate=rate)
        (ROOT / "build" / "paired-results.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))
