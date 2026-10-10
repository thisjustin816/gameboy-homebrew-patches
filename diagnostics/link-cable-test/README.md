# Link Sustain

A 32 KiB Game Boy Color diagnostic for sustained link traffic, scene-ready
barriers, uneven CPU workloads, and a shared ball simulation. Packet errors and
the first failure remain visible after communication recovers. v1.2 is a
test build. Download [link-sustain.gbc](link-sustain.gbc) for both consoles.

## Run a test

Load the same ROM on both consoles and connect them. The settings screen lists
five rows: ROLE, TEST, RATE, LINK and CPU. Pick PEER on one console and HOST on
the other, and give both the same TEST and LINK. Press Start on the peer first,
then on the host within two seconds. The host controls the traffic rate; the
peer's RATE row reads SET BY HOST. CPU can differ.

| Button | Settings screen |
| --- | --- |
| Up/Down | Move the cursor between rows |
| Left/Right | Change the value of the row under the cursor |
| Start | Start a fresh test; clears previous results |

A two-line note under the box explains the row under the cursor and its current
value. Arrows beside the value show that Left/Right change it.

The settings open on ALL STRESS, 4 BYTE BURST, NORMAL link and NORMAL CPU, and a
stress test opens on the BALL page. Run for at least 10 minutes. Then run it
again at the same rate with both CPUs in DOUBLE. SUSTAIN, which opens on the LINK
page, is the plain packet check to fall back on.
Repeat with host and peer swapped. Photograph the results on both consoles.

CPU DOUBLE takes effect when the test starts. LINK CGB FAST selects the fast
serial clock.

| Button | During a test |
| --- | --- |
| Left/Right | Change page |
| Select | Hold the display while the test continues; again to refresh it |
| B | Stop and keep the results |
| Start | After a stop, return to the settings |

Results are held in RAM and disappear when a new test starts or power is
removed. There is no SRAM log.

## Reading the screen

The top five rows are the same on every page:

| Row | Content |
| --- | --- |
| 1 | Role and test |
| 2 | Traffic rate (host) and link clock |
| 3 | RUNNING, HELD or STOPPED, CPU speed and elapsed time |
| 4 | Verdict |
| 5 | Note: when the first error happened, the number of late updates, or the 10-minute target |

The verdict is in color and in words, with an icon in front:

| Verdict | Meaning |
| --- | --- |
| WAITING FOR PEER / HOST (amber) | No valid packet has arrived yet |
| NO ERRORS YET / STOPPED EARLY (amber) | Packets are arriving and nothing has failed, or the run was stopped before 10 minutes |
| PASS: NO ERRORS (green) | At least 10 minutes with no retained error |
| FAIL and the first error (red) | Any error was recorded, even if the link recovered |

The bottom rows show the page name between arrows, four dots for the four
pages, and the button that does something now. A bar on the first page fills
over the 10 minutes. A stopped test keeps its verdict on every page.

## Profiles

| Test | Behavior |
| --- | --- |
| SUSTAIN | Changing patterns with CRC, role, payload, and sequence checks |
| SCENE WAIT | Shared simulation with a scene-ready exchange every 32 commands; the peer delays readiness for six display frames |
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

The first page (LINK) shows the transport counters: GOOD, CRC, SEQ, DATA, GAPS,
receive overrun OV, and transmit underrun UN. FIRST names the first error and
PKT the received sequence in hexadecimal. A sequence error shows WANT; a CRC
error shows the calculated and received CRC values. Stress failures show
expected and received hash, command/profile, or update number in hexadecimal.
GOOD includes sequence errors, which are counted separately. GAPS includes the
initial failure to connect and episodes with no valid packet for about two
seconds. An initial wait for the other console is not a failure; the same gap
after the first packet is. If the other console started more than two seconds
late, the first page says STARTED LATE? REDO. Counts stop growing on screen at
99999.

The STRESS page (profiles other than SUSTAIN; SUSTAIN shows NOT USED):

| Field | Meaning |
| --- | --- |
| UPDATES / SCENES | Accepted simulation updates and scene barriers |
| STATE ERRORS | CRC-valid replies or requests whose simulation hash differs (shown as BAD STATE in the verdict) |
| BAD BARRIERS | Wrong command type, reply direction, or test profile |
| SKIPPED STEPS | A future command or reply skips the required update |
| OLD ACKS | Old replies ignored by the host; expected with queued packets |
| STEP / BALL | Local update number and ball position |

The TIMING page shows the CPU speed and the wire rate, then SLOWEST REPLY
(host request to valid reply), LONGEST GAP (longest interval between valid
received packets after the first), RECOVERY (longest such interval that
included a no-sync episode) and LATE UPDATES (commands that exceeded the reply
budget). The reply rows are host-only and show -- on the peer. F means display
frames, about 16.74 ms each. Reply budgets are 360, 120, and 60 frames for the
three traffic rates. A command counts as late once, even if it stays pending.
These budgets are diagnostic thresholds, not measurements of a game's frame
deadlines. Timing counters are 16-bit frame intervals; intervals beyond about 18
minutes wrap.

The BALL page shows the local simulation in a frame and the step number. The
host can be one pending update ahead of the peer while waiting for a reply. The
test compares completed updates, not the timing of the two LCDs.

For a clean stress run, UPDATES must continue increasing, SCENES must increase
in barrier profiles, and transport and stress error counters should stay zero.
OLD ACKS is expected. Late updates are reported next to the verdict and do not
fail the run, because they are delays and not corrupted data. A mismatch is
retained even if the next correct request or reply recovers.

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

Native PyBoy checks cover boot, the settings cursor, CPU switching, results
pages, stop, restart, a CRC-valid state mismatch and recovery, and the six-frame
scene-ready delay. They also check the verdict. It turns red after an error on
every page of a stopped run, and an error before the first packet replaces the
wait for the other console. It turns green once a run with no error passes 10
minutes, and a stopped test keeps its STOPPED row when the page changes.
Paired checks need PyBoy's Python sources and multiprocessing fork. They copy
the sources into build/ and patch that copy, because PyBoy's pure-Python CPU
reads an instruction that starts at $3FFE or $3FFF as $FF. They run two ROMs with clean traffic, corruption, and an all-FF interruption. Stress
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
The settings and results screens were redesigned with Claude.
