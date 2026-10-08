# Changelog

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
