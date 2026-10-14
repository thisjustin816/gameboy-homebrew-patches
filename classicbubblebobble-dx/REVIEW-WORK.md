# Working checkpoint review

Reviewed against the branch's preceding handoff commit `e217e44`. Scope: 53
added or changed files and zero new commits at review time. Most added lines are
instruction traces and recovered source variants. The original handoff archive
and its quoted notes are unchanged. No pull request was created.

The correctness review follows the changed control paths from VBlank dispatch,
through the two pointer tables, into their fixed and banked handlers. It also
checks the build wrapper, KLL1 replay, capture regression, and experimental
graphics changes. The variants intentionally preserve independent snapshots so
their machine-code identities and old/new failures remain reproducible.

The new capture test fails on the original probe and passes on the correction.
The KLL1 test fails on the exact v0.14 baseline and armed edgeprobe; both new
candidates pass through frame 3243. Their four inherited regressions pass. The
unchanged Classic, BB1, and BB2 patch verification suites also pass on the
uploaded stock/patched pairs. Other games' suites were not run because their
ROM inputs are absent; their files are unchanged.

Graphics parity fails on the new candidates. They remain experimental, with
v0.14 promoted and BB2 v0.22 frozen. The status document names the remaining
reads and the next trace targets. No hardware or selector work is claimed.

| Check | Ran | Found | Fixed | Left, and why |
|---|---|---|---|---|
| Correctness and old/new replay | Yes | Missing indirect entry, table bases, handler discovery, and malformed capture | Control relocation and capture corrected; regressions prove old failures | Graphics reads remain incomplete; candidates are not promoted |
| Coding standards and consistency | Yes | Probe-dependent timing; misleading scheduler comment | Probe-free variant, explicit build profiles, and corrected comment | Legacy builder structure preserved for reproducible snapshots |
| Behavior descriptions | Yes | Archive status describes paused work | Current README and status describe the working checkpoint | Original handoff remains a historical record |
| Writing style and prose scan | Yes | Patch context lines trigger Git whitespace warnings | Trace patch uses zero context; new prose and message use ASCII | Raw test output and inherited source wording retained as evidence |
| Build, tests, and hygiene | Yes | Expected failures on old variants; graphics mismatch on candidates | Four builds, capture/KLL1 regressions, inherited checks, three patch suites, syntax and whitespace checks completed | Other games lack ROM inputs; physical validation and graphics promotion remain future work |
