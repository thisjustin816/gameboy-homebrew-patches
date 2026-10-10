# Changelog

## Screens

- The settings are a framed list with a cursor: Up/Down pick ROLE, TEST, RATE,
  LINK or CPU, Left/Right change the value, Start begins. A note under the box
  explains the row and its value, and the peer's RATE row reads SET BY HOST.
- Every results page opens with the same header: role and test, rate and link
  clock, run state, CPU speed and elapsed time, then a verdict in color and
  words. FAIL names the first error and when it happened. PASS needs 10 minutes
  without an error, and a progress bar on the first page counts to it.
- The settings default to ALL STRESS, and a stress test opens on the BALL page.
- Counters are grouped and right-aligned. SUSTAIN no longer shows stress and
  ball pages full of zeros, and the peer shows -- for the host-only timing rows.
- A stopped test keeps its STOPPED state and verdict when the page changes, and
  a serial hang now redraws the screen.
- Fixed `=` and `,` drawing as blanks, and the cut-off "ACK TIMING: HOST ONLY".
- SCENE BARRIERS is SCENE WAIT, and STATE MISMATCH is BAD STATE, to fit the verdict.
- The paired tests patch their private PyBoy copy so an instruction that starts at
  $3FFE or $3FFF is fetched correctly.

## v1.1+ test build

- Added SCENE BARRIERS, UNEQUAL LOAD, SHARED BALL, and ALL STRESS profiles.
- Scene tests require a reply with the correct command, update number, and
  simulation hash. The peer delays scene readiness for six display frames.
- Load tests alternate three frames of main-thread work between consoles while
  serial interrupts continue. Expanded the transmit queue to eight packets so
  the diagnostic's planned pauses do not cause a transmit underrun.
- Both consoles run an integer ball simulation. Duplicate requests do not move
  the ball again; bad state hashes and skipped updates retain separate errors.
- Added normal/double CPU selection separately from the link-clock setting.
  The host's CPU speed also changes the effective wire clock.
- Added stress, timing, and ball results pages. Timing records the longest
  acknowledgement delay, valid-packet gap, recovery interval, and late updates.
- Retained the first failure through recovery, including expected and received
  state hashes, command types, or update numbers and the received packet number.
- Added native frame and punctuation tiles for the ball arena and readable
  version, timing, and failure displays.
- Added protocol fault tests, update-number wrap checks, native control and
  recovery tests, and paired emulator runs for the new profiles.

The original SUSTAIN profile remains available. This ROM contains original
diagnostic code. No physical console result is claimed by the emulator checks.
