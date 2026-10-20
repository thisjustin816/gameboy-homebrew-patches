# Clock and round-progress review

Reviewed against feature-branch commit `ba36320`: 24 added or changed files and
no new commits at review time. No pull request is open. The original archive,
published patches, promoted BB1 baseline, and frozen BB2 source are unchanged.

The correctness pass follows the native score award and trapped-enemy
initialization into four fixed-ROM tables, and the round-clear VBlank dispatch
through `$1743`. Each table operand is checked before replacement. Discovering
`$1743` relocates its direct call and jump through the existing code scanner.

The frame-6037 investigation also checks the measurement: native `$FF93` is
already one tick ahead at emulator frame 6036. Game-clock mode starts both
workers at the same counter value, drives input by accumulated ticks, compares
identical ordered sample labels, and reports labels skipped by frame stepping.
The original emulator-frame mode is retained. Its longer failure is not claimed
as exact wall-time parity.

| Check | Ran | Found | Fixed | Left, and why |
|---|---|---|---|---|
| Correctness and old/new controls | Yes | Host reads score, bonus, lifetime, and velocity data from host ROM0; round-clear VBlank entry missing | Four relocated table references and discovered `$1743`; old game-clock run fails at tick 4844; old clear test stalls at round index 2 | Dedicated multiple-enemy bonus coverage remains future work |
| Measurement and coding standards | Yes | Emulator-frame samples cross different VBlank ticks; frame stepping can skip game-counter labels | Explicit clock mode, common-origin and sample-label checks, reported omissions, worker error details, and nonempty-sample check | Active has six omitted labels and idle one; no claim about their unobserved state |
| Behavior descriptions | Yes | Frame-6037 failure was unexplained and later rounds untested | Updated README, status, identities, research index, and reproducible commands | Forced clears prove progress, not normal victories or later-round graphics parity |
| Writing style and prose scan | Yes | Current notes needed to distinguish clocks and test scope | ASCII prose and comments reviewed; validated scan, links, and whitespace checked | Historical output retained with its original terminology |
| Build and regressions | Yes | Old table values and startup fallback reproduced | Full build; active/idle game-clock runs through 12000; rounds 4-9 progress; KLL1, title VRAM, menu, SRAM/power cycle, password, and emulator-frame active through 6000 pass | Emulator-frame run through 6200 retains the timing failure; audio and hardware unverified |
| Repository hygiene | Partial | Other published-game ROM inputs are absent | Syntax, allowed file types, handoff hashes, and staged whitespace checks pass | Unchanged game suites cannot rerun without their original inputs; prior reviews record their available runs |

BB1 v0.14 remains promoted and BB2 v0.22 remains frozen. The candidate remains
on the feature branch for dedicated combo and later-round verification.
