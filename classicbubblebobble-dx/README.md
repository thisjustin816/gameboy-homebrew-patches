# Classic Bubble Bobble DX handoff

Work is paused at the edgeprobe18b checkpoint. The complete supplied archive is
preserved byte for byte in [handoff/](handoff/), with copies of its four notes for
reading on GitHub. This branch adds no patch changes or runtime validation.

Read [REVIEW.md](REVIEW.md) before the [resume prompt](handoff/CODEX-HANDOFF-PROMPT.txt)
and [status handoff](handoff/STATUS-HANDOFF.md). The supplied notes describe BB1
v0.14 as the promoted baseline, BB2 v0.22 as frozen, and edgeprobe18b as experimental.
They disagree about the latest probe's execution status; the review records that
conflict without treating either account as newly verified.

The outer ZIP contains `BubbleBobbleDX-diagnostic-edgeprobe18b-source.zip`, which
holds all 238 source, research, reference, and manifest files. Extract both ZIPs
into a scratch directory to resume. No game ROMs or saves are included. The exact
patched inputs and their MD5 hashes are listed in the status handoff.

From this directory, check the imported files with:

```sh
sha256sum -c SHA256SUMS
```

The files under `handoff/` are original records, including their wording and
historical claims. The checksum file beside this README describes the imported
bytes; the older manifest inside the source ZIP has a stale self-hash.
