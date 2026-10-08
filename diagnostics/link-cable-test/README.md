# Link Sustain

A 32 KiB Game Boy Color ROM for sustained link-cable testing. Both consoles
send changing packets and check the received CRC, payload, and sequence.
Errors and the first failure stay on screen after sync recovers.

Build link-sustain.gbc with the command below, then load it on both consoles.
The generated ROM is excluded from Git.

## First run

1. Connect the consoles. Choose PEER on one and HOST on the other with
   Left/Right. Leave 4 BYTE BURST and NORMAL 8192 selected.
2. Press Start on the peer, then Start on the host within two seconds.
3. Both GOOD counters should increase. Run for at least 10 minutes, or longer
   than the game usually takes to disconnect. A clean run has zero CRC, SEQ,
   DATA, GAPS, OV, and UN.
4. Photograph both screens. Press B on both to stop and keep the results.
5. Repeat with the clock roles swapped, keeping the same cable and power supply.

Select freezes the display while transfers continue; Select again refreshes it.
Start while stopped opens the menu. Starting a new test or powering off clears
all results. The ROM has no SRAM log. Stopping only one console causes expected
errors on the other.

## Settings

Left/Right changes the clock role. Up/Down changes the host's traffic schedule;
the peer's rate setting is ignored. Select in the menu changes clock speed.
Match clock speed on both consoles. Two hosts or two peers cannot run a valid test.

| Setting | Traffic |
| --- | --- |
| 1 BYTE/FRAME | One byte per display frame, about 60 bytes/s before processing overhead |
| 4 BYTE BURST | Four bytes followed by a VBlank wait, about 240 bytes/s before processing overhead |
| CONTINUOUS | Transfers with a minimum 2 ms idle gap and no VBlank wait |
| NORMAL 8192 | 8,192-bit/s wire clock, about 0.98 ms per byte |
| CGB 262144 | 262,144-bit/s wire clock, about 0.031 ms per byte |

CPU speed stays normal. Packet preparation and display updates add idle time.
Fast mode increases the wire clock; the traffic schedule stays the same.

## Results

| Field | Meaning |
| --- | --- |
| SEC | Elapsed time from the nominal Game Boy frame clock |
| GOOD | Packets with valid CRC, role, and payload; compare both screens |
| CRC | Candidate packets with a bad CRC or end marker |
| SEQ | Valid packets with unexpected sequence numbers: loss, duplicates, or a restarted peer |
| DATA | CRC-valid packets with the wrong role or payload |
| GAPS | Episodes with no valid packet for about two seconds, or a host serial hang |
| OV / UN | Local receive-ring overflow / transmit-buffer underrun |
| FIRST / AT SEC / PKT | First error, elapsed time, and received sequence; a timeout shows the next expected sequence |
| CRC x>y | Calculated versus received CRC at the first bad packet, in hex |
| WANT | Expected sequence at the first sequence error; PKT shows the received sequence, in hex |

GOOD includes packets with an unexpected sequence; SEQ counts those separately.
A damaged start marker can appear as a sequence error or gap without a CRC error.
GAPS includes failure to establish the initial connection. FIRST stays latched
while the receiver searches for the next valid packet and resumes the test.

Keep the host role, cable orientation, power supply, settings, duration, and
both screens' results with each run. After swapping roles, try swapping cable
ends, then a known-good cable. Change one variable per run. Use a separate run
for an intentional unplug/replug test.

## Packet format

Each direction sends 16-byte packets: two-byte magic, role, 32-bit little-endian
sequence, six pattern bytes, CRC-16/CCITT-FALSE over bytes 0-12, and an end marker.
Patterns include 00/FF, 55/AA, walking bits, and sequence-dependent values.
The peer re-arms in its serial interrupt. The host leaves at least 2 ms before
the next byte to allow the peer to load its transmit register.

## Build and checks

Set GBDK_HOME to the GBDK-2020 installation:

```sh
make GBDK_HOME=/path/to/gbdk
python3 tests/protocol.py
python3 tests/smoke.py
python3 tests/paired.py
```

The protocol check requires a host C compiler. It checks the known CRC vector,
sequence boundaries, roles, every single-bit corruption of representative
packets, and a CRC-valid incorrect payload. Smoke checks use PyBoy to run the
ROM's menu, disconnected host/peer, display hold, stop, and restart controls.

Paired checks require PyBoy with its Python sources and a system supporting
multiprocessing fork. They run two copies of the ROM with clean traffic,
corruption, and an all-FF interruption. The harness copies the installed
emulator sources into build/ and adjusts its synthetic link timing, leaving
the installation untouched.

These checks cover software behavior. Physical cable timing, fast clock, bit
alignment, and loss of external clock remain unverified. The ROM also uses a
different protocol and interrupt load from Serve Sisters. Clean results narrow
the hardware investigation but cannot rule out game-specific timing problems.

The ROM, tests, and documentation were written with AI assistance (Codex).
