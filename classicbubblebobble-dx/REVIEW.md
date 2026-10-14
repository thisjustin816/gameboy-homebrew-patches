# Handoff import review

Reviewed against freshly fetched `origin/main` at
`c89ebde0357d8791ddafb979bc06b51a20dd0579` before committing. Scope: nine added or
changed files, zero new commits at review time, and no pull request. The archive
is retained as an artifact; its patch code is unchanged and is not installed over
the repository's existing patches.

The correctness pass checked the import, archive contents, extraction paths,
manifest, note copies, and resume instructions. Coding standards, writing style,
prose scanning, and the Game Boy repository's ROM/save hygiene rules apply.
Language-specific implementation checks do not apply to this archive-only import.
There are no gameplay changes requiring emulator or hardware regression tests.

| Check | Ran | Found | Fixed | Left, and why |
|---|---|---|---|---|
| Correctness review | Yes | Conflicting runtime claims; stale manifest self-hash | Added this review and an import checksum file | Original records preserved at the user's request |
| Archive integrity and content | Yes | Both ZIP CRC checks pass; 238 inner files; no unsafe paths, ROMs, saves, states, or object files | None needed | Proves preservation, not gameplay correctness |
| Snapshot hashes | Yes | 237 entries match; `SNAPSHOT-SHA256.txt` does not match its own recorded hash | Import hashes cover the preserved files | Original manifest stays unchanged |
| Coding standards | Yes | No executable changes; original notes copied exactly | None needed | Diagnostic implementation remains unfinished |
| Behavior descriptions | Yes | Historical version labels and runtime claims disagree | Current entry point explains the conflict | No unsupported reconciliation of historical claims |
| Writing style and prose scan | Yes | Original notes contain Unicode punctuation and chat instructions | New README, review, and commit message use plain ASCII | Original notes are quoted source records |
| Game Boy hygiene | Yes | Source-only archive; existing patches untouched | None needed | No ROM build, emulator run, or promotion performed |
| Import checks | Yes | Byte equality, SHA-256 checks, local links, and new-text whitespace checks pass | None needed | Runtime suites require the exact ROM inputs and would continue the paused work |

## Resume caveats

- `CODEX-HANDOFF-PROMPT.txt` reports a Gambatte run reaching marker `$C4` at frame
  2094 and reports suspect stack capture values. `EDGE-PROBE-NOTE.md` and the final
  section of `STATUS-HANDOFF.md` say edgeprobe18b was not built or run. This import
  does not establish which execution account is correct.
- The original README labels the snapshot v0.19, the status note labels it v0.20,
  and parts of the status note still describe v0.13/v0.14. The supplied archive
  contains the edgeprobe18b diagnostic source. Do not infer a promoted build from
  a filename, section heading, or historical hash.
- The archived checksum manifest includes a stale self-hash. All other 237 listed
  files match. Use the new `SHA256SUMS` to verify the imported handoff.
- The resume prompt names `GB-DEVELOPMENT-PROJECT-INSTRUCTIONS` and
  `agents-main.zip`, neither of which is attached in this handoff. The local
  Game Boy skills were available for this import, but those older dependencies
  have not been reconstructed or added.
- The runner `run_edgeprobe_arg_long.py` names a prior session's `/mnt/data`
  Stable-Retro path and Python 3.13 extension. Its portability and the reported
  stack-capture issue remain future work.

The default Git whitespace check flags the original notes' Markdown hard-break
spaces and a final blank line. Those bytes are preserved; the new prose passes.

No patch code, diagnostic code, or original handoff text was edited. No ROMs were
built, no runtime tests were run, and no pull request was opened.
