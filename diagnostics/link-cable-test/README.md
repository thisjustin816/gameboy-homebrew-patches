# Link Sustain

A 32 KiB Game Boy Color diagnostic for sustained link traffic, scene-ready
barriers, uneven CPU workloads, and a shared ball simulation. Packet errors and
the first failure remain visible after communication recovers. v1.1+ is a
test build. Download [link-sustain.gbc](link-sustain.gbc) for both consoles.

## Run a test

Load the same ROM on both consoles. Connect them, choose PEER on one and HOST
on the other, and match TEST and CLOCK. Start the peer first, then the host
within two seconds. The host controls the traffic rate; the peer's rate setting
is ignored. CPU settings can differ.

| Menu button | Setting |
| --- | --- |
| Left/Right | HOST or PEER |
| Up/Down | Host traffic rate |
| Select | Normal or CGB fast link clock |
| A | Normal or double-speed CPU, applied when the test starts |
| B | Test profile |
| Start | Start a fresh test; clears previous results |

Start with SUSTAIN, 4 BYTE BURST, normal clock, and normal CPU. Run for at least
10 minutes. Then run ALL STRESS at the same rate with both CPUs in double speed.
Repeat with host and peer swapped. Photograph the results on both consoles.

During a test, Left/Right changes results pages. Select holds the display while
the test continues; Select again refreshes it. B stops and retains results.
Start while stopped returns to settings. Results are held in RAM and disappear
when a new test starts or power is removed. There is no SRAM log.

## Profiles

| Test | Behavior |
| --- | --- |
| SUSTAIN | Changing patterns with CRC, role, payload, and sequence checks |
| SCENE BARRIERS | Shared simulation with a scene-ready exchange every 32 commands; the peer delays readiness for six display frames |
| UNEQUAL LOAD | Shared simulation with three frames of CPU work every eight commands, alternating between consoles; serial interrupts stay enabled |
| SHARED BALL | Both consoles compute ball movement and compare the resulting state hash before the host issues another update |
| ALL STRESS | Shared simulation, scene barriers, and alternating CPU work together |

The host waits for an acknowledgement with the current command type, update
number, and state hash. A gameplay reply cannot acknowledge a scene barrier,
even if its number matches. The peer applies each command once; repeated
requests repeat the reply without moving the ball again. The simulation uses
original diagnostic code and contains no game assets or patched game routines.

The ball page shows local simulation state. The host can be one pending update
ahead of the peer while waiting for a reply. The test compares completed
updates, not the timing of the two LCDs.

## Traffic and clocks

| Rate | Host schedule |
| --- | --- |
| 1 BYTE/FRAME | One byte, then a VBlank wait |
| 4 BYTE BURST | Four bytes, then a VBlank wait |
| CONTINUOUS | No VBlank wait; at least a nominal 2 ms idle gap between bytes |

Packet preparation and screen updates add idle time. The gap compensates for
double-speed CPU operation. Match the link clock setting on both consoles.
The host's CPU speed determines the effective wire clock:

| Clock setting | Normal host CPU | Double-speed host CPU |
| --- | --- | --- |
| Normal | 8,192 bit/s | 16,384 bit/s |
| CGB fast | 262,144 bit/s | 524,288 bit/s |

CPU and clock settings are separate controls, but changing host CPU speed also
changes wire speed. For mixed CPU tests, repeat with each console as host.

## Results

The first page retains the transport counters: GOOD, CRC, SEQ, DATA, GAPS,
receive overrun OV, and transmit underrun UN. FIRST records the first error,
AT SEC its elapsed time, and PKT the received sequence. A sequence error shows
WANT; a CRC error shows calculated and received CRC values. Stress failures show
expected and received hash, command/profile, or update number in hexadecimal. GOOD includes
sequence errors, which are counted separately. GAPS includes initial failure
to connect and episodes with no valid packet for about two seconds.

The stress page adds:

| Field | Meaning |
| --- | --- |
| UPDATES / SCENES | Accepted simulation updates and scene barriers |
| STATE | CRC-valid replies or requests whose simulation hash differs |
| BARRIER | Wrong command type, reply direction, or test profile |
| ORDER | A future command or reply skips the required update |
| OLD ACK | Old replies ignored by the host; expected with queued packets |
| STEP / BALL X / BALL Y | Local update number and ball position |

The timing page shows MAX ACK F (host request-to-valid-reply delay), MAX GAP F
(longest interval between valid received packets after the first), RECOVER F
(longest such interval that included a no-sync episode), and LATE UPD (commands
that exceeded the reply budget). F means display frames, about 16.74 ms each.
Reply budgets are 360, 120, and 60 frames for the three traffic rates. A command
counts as late once, even if it stays pending. These budgets are diagnostic
thresholds, not measurements of a game's frame deadlines. Timing counters are
16-bit frame intervals; intervals beyond about 18 minutes wrap.

For a clean stress run, UPDATES must continue increasing, SCENES must increase
in barrier profiles, and transport and stress error counters should stay zero.
OLD ACK is expected. LATE UPD reports delays separately from corrupted data.
A mismatch is retained even if the next correct request or reply recovers.

Keep the settings, duration, cable orientation, power supply, and both screens'
results with each run. Swap clock roles, then cable ends, then try a known-good
cable. Change one variable per run. Use a separate intentional unplug/replug run.
Stopping only one console causes expected errors on the other.

## Packets

Both formats use 16 bytes: two-byte magic, role, 32-bit little-endian sequence,
six payload bytes, CRC-16/CCITT-FALSE over bytes 0-12, and an end marker. SUSTAIN
patterns include 00/FF, 55/AA, walking bits, and sequence-dependent values.
Stress packets mark the role's high bit and carry command type, 16-bit update
number, 16-bit state hash, and profile. The update number wraps after 65,536
commands. The peer re-arms in its serial interrupt.

## Build and checks

```sh
make GBDK_HOME=/path/to/gbdk/
python3 tests/protocol.py
python3 tests/stress.py
python3 tests/smoke.py
python3 tests/features.py
python3 tests/paired.py
python3 tests/paired.py --stress
```

Use GBDK-2020 and Python with PyBoy and Pillow. Protocol and stress checks also
need a host C compiler. They compile the cartridge's C routines, check every
single-bit corruption of representative packets, exercise update-number wrap,
and reject state, order, and acknowledgement-type faults. An injected missing
type guard confirms that the scene acknowledgement check detects that defect.

Native PyBoy checks cover boot, settings, CPU switching, results pages, stop,
restart, a CRC-valid state mismatch and recovery, and the six-frame scene-ready
delay. Paired checks need PyBoy's Python sources and multiprocessing fork. They
run two ROMs with clean traffic, corruption, and an all-FF interruption. Stress
pairs cover each profile and both normal and double CPU settings. Barrier pairs
seed both simulations just before a scene boundary to keep the test bounded.
The harness uses a synthetic byte link and does not establish physical serial
timing, fast-clock operation, or cable behavior. Screenshots and JSON results
are written under build/; test artifacts are excluded from Git. The verified
standalone diagnostic ROM is included in this directory.

These tests use a different protocol and interrupt load from any commercial
game. A clean run narrows the hardware investigation but cannot rule out a
game-specific timing problem. Physical console checks remain to be done.

The ROM, tests, and documentation were written with AI assistance (Codex).
