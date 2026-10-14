# Classic Bubble Bobble DX — STATUS / HANDOFF

Checkpoint: **source snapshot v0.20 rollover**  
Date: **2026-10-13**  
Current BB1 implementation: **virtualization diagnostic v0.14 (promoted baseline unchanged)**  
Status: **BB2 remains frozen/known-good. BB1 v0.14 remains the promoted baseline. Stable-Retro/Gambatte now reproduces end-to-end KLL1 acceptance and the hosted round-start failure. Several real fixed/upper-ROM data virtualization bugs were identified experimentally, but no candidate is promoted. The current frontier is an unexpected re-entry into relocated BB1 startup `$4150` at frame 2094, immediately before hosted round state is cleared at frame 2095.**

## Goal / non-negotiables

Build one **2 MiB ordinary MBC5** image containing the user's existing patched releases:

1. Classic Bubble Bobble — SMS physics + save patch, native host/base game
2. Bubble Bobble — password-save patch
3. Bubble Bobble Part 2 — tearing fix + save patch
4. Later, a native selector/front end

**Do not use the Disney Afternoon multicart patch as an architectural reference.**

At the start of a fresh session, load:

- `.agents-main/skills/gb-development/SKILL.md`
- `.agents-main/skills/gb-rom-hacking/SKILL.md`

Keep producing frequent **source snapshot + STATUS/HANDOFF** checkpoints. Never put ROMs, `.ram`, `.sav`, or emulator save-state files in source archives.

## Exact patched inputs

| Input | Size | MD5 |
|---|---:|---|
| Classic Bubble Bobble patched v1.0 | 1,048,576 | `2c4c0b9cc0c106051fb195e4ed3365d9` |
| Bubble Bobble patched v1.0 | 131,072 | `b093fd9aa903453c1b30703738159a49` |
| Bubble Bobble Part 2 patched v1.1 | 262,144 | `f2ef3b62b6859cc89bbb8494bb4057b2` |

The builders reject unknown inputs.

## Physical MBC5 layout

| Physical banks | Contents |
|---|---|
| `$00-$3F` | patched Classic Bubble Bobble, native host |
| `$40-$47` | patched Bubble Bobble payload |
| `$48-$57` | patched Bubble Bobble Part 2 payload |
| `$58-$7F` | free (640 KiB) |

SRAM plan/current assignments:

- Classic: MBC5 SRAM bank 0
- BB1: MBC5 SRAM bank 1
- BB2: MBC5 SRAM bank 2
- bank 3 spare

## Frozen BB2 baseline

BB2 diagnostic **v0.22** is the promoted known-good baseline and should not be regressed while working on BB1.

- physical ROM banks `$48-$57`
- SRAM bank 2
- diagnostic ROM MD5 (ROM not in source archive): `4855fed2b2fcb5e6df9677df772b4dc3`
- accumulated boot/menu/gameplay/data/palette/save regressions pass
- three deterministic 18,000-frame stress runs pass (54,000 frames total)

See `source/bb2-virtualization/` and inherited BB2 research files for exact tests/evidence.

## BB1 current build

Diagnostic ROM (not included):
`Classic Bubble Bobble DX [BB1 virtualization diagnostic v0.13].gbc`

- MD5: `31427109af44e7575dca5c240daa9ce4`
- SHA-256: `1c529ab721ebd385c89394f8ebdaafa5bd6e80ece9c9c7d8ce07f0c8c0eff2e0`
- BB1 physical ROM banks: `$40-$47`
- relocated fixed bank V0: physical `$40`
- target SRAM: bank 1
- host range: `$1665-$1FD3` (host end `$1FD4`)
- 92 mapper sites
- 6,949 decoded fixed-bank instructions
- 61 fixed→upper edges / 54 unique upper targets
- 188 discovered banked→fixed edges / 24 unique low targets
- 19 fixed + 22 banked reachable DMG palette-write sites
- fixed JP-HL sites: `$080B,$0CB7,$29E2,$2C7E`

## Architecture retained from v0.6

BB1 startup clears most HRAM, including host state, so the post-clear wrapper restores `H_PHYS=$40` and `H_LOG=$01`.

BB1 fixed routine `$042F` is a cooperative stack/context switcher. The working architecture keeps the v0.6 design:

- VBlank tail-jumps into relocated `$4C6F` with no persistent host CALL frame.
- scheduler RET at logical `$0446` routes through RST `$10` / `host_context_ret`.
- that wrapper rewrites saved logical fixed-bank PCs to hosted `+$4000` addresses in-place.
- logical VBlank return routes through the host RETI path.

Do **not** replace this with the abandoned v0.7 “normal CALL VBlank + pre-relocated task pointers” experiment; that build eventually executed in WRAM and had early VRAM corruption.

## New fixes v0.8-v0.13

### v0.8 — seed cooperative task entry PCs

The fixed-bank CFG did not include tasks entered only by scheduler-restored PCs. In v0.6, logical task `$054A` therefore retained a raw `CALL $63B7`, which executed the wrong bytes while physical V0 was mapped.

Explicit task-entry seeds now include:
`$054A,$0D27,$1C92,$298A,$21A1`.

Old/new evidence:

- v0.6 completes frame 72, then frame 73's PyBoy `tick()` never returns.
- v0.8 reaches frame 120 normally under the same unhooked cold-boot harness.

Evidence: `research/bb1-old-v0.6-frame-stall.txt`, `research/bb1-new-v0.8-frame-progress.txt`.

### v0.9 — fixed-bank callers of `$021E`

BB1 fixed routine `$021E` copies `BC` bytes `[HL+] -> [DE+]`. Four fixed callers use upper-ROM sources after selecting a logical bank:
`$0507,$0513,$0524,$05B1`.

Relocated fixed code cannot see that selected bank, so those four sites now call `host_bb1_copy_bc`, which runs from real ROM0, exposes `H_LOG`, reproduces the 16-bit copy loop, restores V0 and preserves final A/F semantics.

Evidence:

- v0.8 has 3,860 wrong VRAM bytes at frame 80 versus the native-CGB timing reference.
- v0.9 has 0 differences at frame 80.

### v0.10 — banked callers of `$021E`

There are 23 discovered banked→fixed calls to `$021E` in logical banks 1 and 6. The generic low wrapper was wrong because it mapped V0 before the copy, hiding the caller's source bank.

`host_low_021e` now executes the original copy loop directly from real ROM0 **without changing the upper mapping**, then returns to the same banked caller.

Evidence:

- v0.9: 311 persistent early-boot/splash VRAM differences.
- v0.10: 5 persistent differences in the same early graphics path.

### v0.11 — dual-purpose bank-3 code/data shadow

The remaining five bytes revealed that BB1 deliberately uses executable ROM bytes as tile graphics.

- title block VRAM `$8FC0-$8FFF` comes from logical bank 3 `$6FA1-$6FE0`.
- routine `$6FD1-$705B` overlaps the end of that 64-byte graphics block.
- virtualization had rewritten three fixed-bank call operands inside `$6FD1`, so those patched operand bytes were later copied as graphics.

v0.11 resolves this without sacrificing either behavior:

1. Original bank-3 `$6FD1-$705B` is restored byte-for-byte for data reads.
2. An executable shadow copy is placed in verified original `$FF` padding at bank 3 `$7E00`.
3. The shadow's four fixed-bank calls are patched to host low wrappers.
4. The sole direct `$6FD1` caller reaches the shadow through `host_upper_6fd1`.

Evidence:

- v0.10: 5 persistent VRAM differences, beginning `$8FF6`.
- v0.11: those five early-boot differences are eliminated; sampled frames 85-400 reach 0 VRAM differences versus the native-CGB timing reference.
- builder asserts the original `$6FD1-$705B` region is restored exactly and the `$7E00` destination was all `$FF` in the exact input ROM.

Evidence: `research/bb1-title-v0.10.txt`, `research/bb1-title-v0.11.txt`, `research/bb1-dual-use-code-data-evidence.txt`.

### v0.12 — title transfer descriptor virtualization (diagnostic intermediate)

The frame-419 investigation found that the title transfer parser at logical `$16D7/$16E3` consumes a descriptor stream from the currently selected upper ROM bank. Under virtualization, relocated fixed code was reading the physically mapped V0 window instead. In v0.11 that produced a bogus source pointer `$0828`; subsequent title transfer writes therefore read the host diagnostic `$D3` poison from real ROM0.

v0.12 added `host_bb1_transfer_stream_entry`, which temporarily exposes `H_LOG` while reading the descriptor stream, then restores V0. This corrected the title source descriptor to logical bank 1 `$6F20`, but **v0.12 alone was not sufficient**: the bulk transfer worker at `$1725-$172C` still read its upper-ROM source while V0 was physically mapped.

Evidence:

- exact reconstructed v0.11 reproduces the authoritative frame-419 failure and MD5/SHA-256.
- v0.12 still diverges at frame 419 (62 VRAM bytes) and was never promoted as a good checkpoint.
- `research/live-v011-frame419-state.txt`, `research/live-v012-frame419-state.txt`, `research/live-vram-writers-v011.txt`, `research/live-vram-writers-v012.txt`.

### v0.13 — virtualize the 32-byte title transfer worker

A reachable-store trace identified the first corrupt writer exactly: physical `$5729` / logical `$1729`, `LD [HL+],A`, writing the title region beginning at VRAM `$9450`. The worker's source pointer is valid upper-ROM data, but relocated fixed code cannot see that selected bank while V0 is physically mapped.

v0.13 keeps the v0.12 descriptor fix and patches logical `$1725-$172C` to call `host_bb1_copy_vram32`. The helper:

1. copies one 32-byte block from the selected logical upper bank by temporarily exposing `H_LOG`;
2. restores physical V0 before returning to relocated fixed code;
3. also supports a fixed-bank source by reading the relocated V0 window at `+$4000`;
4. leaves the original outer block-count loop at `$172D+` intact.

Old/new regression evidence:

- v0.11: frames 400-600 contain 182 VRAM-mismatch frames; first failure is frame 419 at `$9450` with 64 wrong bytes; peak/settled difference is 2,991 bytes.
- v0.13: **0 VRAM-mismatch frames across every frame 400-600**, and scheduler bytes `$DE00-$DE1F` match at frame 600.
- rendered frame 600 has an exact one-to-one pixel-geometry mapping versus the native-CGB reference. The RGB values differ only because the hosted build intentionally mirrors the DMG/grayscale palette rather than the CGB compatibility palette.

Evidence: `research/regression-real-title-old-v011.txt`, `research/regression-real-title-new-v013.txt`, `research/render-parity-v0.13.txt`, `research/live-v013-frame419-state.txt`, `source/bb1-virtualization/test_real_title_vram_parity.py`.


### v0.14 — preserve the banked `$0465` cooperative-yield continuation

After title parity was fixed, the established 715-frame repeated-Start probe exposed a second independent scheduler failure. The native-CGB timing reference reaches the menu at frame 715, while v0.13 never returns from PyBoy's frame tick (timeout) after entering the cooperative transition task.

The root cause is the interaction between a banked caller and `host_low_0465`:

1. a banked task calls the game's logical `$0465` wait/yield routine through `host_low_0465`;
2. `$0465` cooperatively switches stacks and captures the caller return address as task state;
3. that saved return is not a logical BB1 fixed-bank PC — it is the ROM0 continuation inside the host wrapper immediately after `CALL $4465`;
4. `host_context_ret` previously treated every saved address below `$4000` as logical fixed-bank code and added `$4000`, turning the host continuation into unrelated relocated BB1 code on resume.

v0.14 gives the instruction immediately after `CALL $4465` the symbol `host_low_0465_resume`. `host_context_ret` compares the saved task return against that exact symbol; only that host continuation is left in ROM0. All other saved low PCs retain the existing relocation behavior.

Old/new regression evidence:

- v0.13: `source/bb1-virtualization/test_menu_transition.py` does not complete under the 715-frame input sequence and is killed by a 12-second timeout (`rc=124`).
- v0.14: the same sequence reaches frame 715 normally and produces RGB screen MD5 `e34db805a4d155f0da472d410fe3e77a`, exactly matching the native-CGB timing reference.
- v0.14 still has **0 VRAM-mismatch frames for every frame 400-600** in the established real-title regression, and scheduler `$DE00-$DE1F` still matches at frame 600.

Diagnostic ROM identity (ROM not included in source archive):

- MD5: `85ad58cbabcc52e53cb250b2abaddcd6`
- SHA-256: `546d9ac6c56904e9690bc6acbe33ee0a1266e0e84367e8e93230e1e6c9731fb6`
- host range: `$1665-$1FDF` (`host_end=$1FE0`)

Evidence: `research/test-menu-old-v0.13.txt`, `research/test-menu-new-v0.14.txt`, `research/menu-regression-new-v0.14.txt`, `research/regression-real-title-new-v014.txt`, `source/bb1-virtualization/test_menu_transition.py`.

## Corrected visual/status interpretation

**Correction retained from the v0.16 tracker:** frame 120 is the **TAITO splash**, not the Bubble Bobble title. The underlying early-boot parity measurements were valid; only their screen label was wrong.

At frame 120:

- hosted early build VRAM MD5: `e032674b722f87f66d780413d99e55ef`
- native-CGB timing reference VRAM MD5: same
- this proves TAITO splash / early-boot VRAM parity, **not title parity**

The real Bubble Bobble title transition begins around frame 400. The original v0.11 failure remains an important regression reference:

- frame 419: 64 VRAM bytes differ, first at `$9450`; host PC `$43D8` (logical `$03D8`) vs reference PC `$0296`
- frame 420: 128 bytes differ
- frame 425: 448 bytes differ
- frame 450: 2,047 bytes differ
- frame 465 onward: 2,991 bytes remain different
- by frame 600 v0.11 displays a repeating garbage-tile pattern instead of the Bubble Bobble title

v0.13 eliminates that failure. The regression samples **every frame 400-600** and reports zero VRAM differences. At frame 600 the complete title geometry matches the native-CGB timing reference pixel-for-pixel after accounting for the intentional palette mapping.

The temporary native-CGB reference (patched BB1 with only header `$0143=$80` plus recomputed checksums) is for **timing/data parity only**. Do not ship or archive that ROM.

## Current frontier

**BB1 v0.14 passes every safe PyBoy validation currently available.** The code itself is unchanged from checkpoint v0.18; v0.19 adds formal save/power-cycle/password-prefill regressions and acceptance evidence.

Validated in v0.19:

- exact rebuild MD5 `85ad58cbabcc52e53cb250b2abaddcd6` / SHA-256 `546d9ac6c56904e9690bc6acbe33ee0a1266e0e84367e8e93230e1e6c9731fb6`;
- zero VRAM mismatch frames for every frame 400-600 versus native-CGB timing reference;
- the 715-frame repeated-Start transition completes and matches the native rendered-frame hash, while v0.13 times out;
- `save_round` writes `b0 b1 00 00 a5` to **MBC5 SRAM bank 1 only**;
- the 32 KiB battery file contains that record only in bank 1 and a fresh PyBoy instance reloads it unchanged after power cycle;
- `pf_init` reads the persisted bank-1 save and produces password tiles `1F 15 15 01` = `VLL1`, with `SLOT=0` and `PF_PENDING=1`;
- `pf_step` copies `VLL1` into the entry buffer, sets `SLOT=3`, clears pending, selects END (`MENU=24`), and moves the hand to the expected END position while preserving B/C/D/E/HL.

Immediate next work:

1. Run the actual PASSWORD-screen/acceptance flow and round-start path in stable-retro/Gambatte when that runtime is available; do not use PyBoy round-start behavior as a correctness signal because stock/patched BB1 crash there too.
2. Verify a persisted VLL1 save is accepted as round 1 after a true power cycle, then exercise a nontrivial saved round such as KLL1/round 3.
3. Keep BB2 v0.22 frozen while working on BB1.
4. Only after BB1/BB2 launch/save/gameplay are reliable, build the player-facing selector.
5. Hardware-test on the intended ordinary MBC5 cartridge/Chromatic before declaring complete.


## 2026-10-13 Gambatte KLL1 investigation — authoritative new frontier

This section supersedes the older "remaining BB1 gap" wording below. Stable-Retro/Gambatte is now available and the KLL1 path has been reproduced deterministically. **Do not promote any experimental build described here. BB1 v0.14 remains the baseline.**

### Baseline reproduction

- Rebuilt BB1 v0.14 matches the published identities exactly:
  - MD5 `85ad58cbabcc52e53cb250b2abaddcd6`
  - SHA-256 `546d9ac6c56904e9690bc6acbe33ee0a1266e0e84367e8e93230e1e6c9731fb6`
- The exact preserved KLL1 password sequence was replayed under the low-level Stable-Retro 1.0.1 bridge with its bundled Gambatte core.
- Native patched BB1 accepts KLL1 and keeps round index `$C200=2`.
- Hosted v0.14 accepts KLL1 but later clears the round during startup/transition.

### Confirmed experimental fixes — real bugs, still unpromoted

The following were established as genuine virtualization problems during round start:

1. Logical `$1870-$1889` reads the selected upper-bank round pointer/payload and copies eight bytes into HRAM `$FFB5-$FFBC`. Relocated V0 sees the wrong physical bank. `host_bb1_round_payload` fixes that read and produces the correct payload, but does not fix the overall reset.
2. Round-start transfer setup at `$168F` uses a fixed-ROM pointer table at logical `$1A60`; relocated V0 must address its hosted copy (`$5A60`), not host ROM0 `$1A60`.
3. `host_bb1_transfer_stream_entry` must handle both selected upper-ROM streams and fixed/low BB1 ROM streams.
4. Logical `$1B7D-$1B8F` copies selected-upper-ROM data at `$5F67` into sparse WRAM table `$C112`; that source read also requires virtualization.

These changes appear in preserved **experimental** v0.16-v0.18b source trees. They advance correctness but do not satisfy KLL1 round start, so none is promoted.

### Negative experiments

Two fixed-ROM jump-table hypotheses were tested on top of v0.18b:

- v0.18c-jt29: relocate table base `$29E3 -> $69E3`
- v0.18c-jt2c: relocate table base `$2C7F -> $6C7F`

Both still change `$C200` from `2 -> 0` at frame 2095. Treat both as failed diagnostics, not fixes.

### First remaining control divergence

The most important finding is from the guarded startup-entry diagnostic built on v0.18b:

- Harness arms `$FFF9=$5A` after KLL1 round start.
- A trap placed at relocated startup entry `$4150` is hit at **frame 2094**.
- Captured `SP=$DFFD`.
- Captured top stack word = **`$41B1`**.
- The diagnostic freezes before startup clearing; `$C200` remains `2`.
- The corresponding non-trapping v0.18b clears `$C200` at **frame 2095**.

Therefore the next bug is not the startup clear itself: **control is incorrectly reaching relocated startup `$4150` during round start.** Trace the writer/control edge that targets `$4150`, using `$41B1` as the immediate stack clue. Prioritize cooperative scheduler/context-return and indirect-jump paths. Do not patch the downstream clear as a symptom.

Supporting note: `research/bb1-gambatte-kll1-round-start-2026-10-13.txt`.

### Exact next work

1. Keep BB2 v0.22 frozen and BB1 v0.14 promoted.
2. Use v0.18b only as experimental scaffolding because it contains the independently verified round-start data fixes.
3. Reproduce KLL1 in Gambatte.
4. Instrument the path that reaches `$4150` around frame 2094; resolve why the stack contains `$41B1` at `SP=$DFFD`.
5. Once a cause is fixed, require old-fails/new-passes KLL1 round start **and** rerun all v0.14 title/menu/save regressions before promotion.

## Source map

- `source/phase0/` — physical 2 MiB MBC5 layout builder/verifier
- `source/bb2-virtualization/` — frozen BB2 v0.22 source/tests
- `source/bb1-virtualization/prototype.py` — exact current BB1 v0.14 builder
- `source/bb1-virtualization/host.generated.asm` / `.sym` — generated current host code/symbols
- `source/bb1-virtualization/manifest-v0.14.txt` — current build manifest (`manifest-v0.11.txt` and `manifest-v0.13.txt` retained for regression provenance)
- `source/bb1-virtualization/test_title_vram_parity.py` — early-boot/splash VRAM parity probe used across v0.8-v0.11
- `source/bb1-virtualization/test_real_title_vram_parity.py` — v0.11-fails/v0.13-passes frame-400..600 real-title regression
- `source/bb1-virtualization/test_title_visual_probe.py` — stable visual/palette probe
- `source/bb1-virtualization/test_menu_transition.py` — v0.13-times-out/v0.14-passes 715-frame title-to-menu scheduler regression
- `source/bb1-virtualization/test_sram_bank1_powercycle.py` — direct `save_round`, SRAM-bank isolation, 32 KiB battery-file layout, and fresh-instance persistence regression
- `source/bb1-virtualization/test_password_prefill_routines.py` — persisted bank-1 `pf_init` and `pf_step` VLL1 prefill/cursor-state regression
- `research/bb1-title-v0.10.txt` / `bb1-title-v0.11.txt` — old/new proof for dual-use code/data fix
- inherited BB2 research files — v0.22 regression/stress/save evidence

## Resume prompt for a fresh project chat

> Continue Classic Bubble Bobble DX from `BubbleBobbleDX-source-snapshot-v0.20.zip` and `STATUS-HANDOFF.md`. Read `GB-DEVELOPMENT-PROJECT-INSTRUCTIONS.txt` first, then load `.agents-main/skills/gb-development/SKILL.md` and `.agents-main/skills/gb-rom-hacking/SKILL.md` from `agents-main.zip`. Treat the handoff as authoritative. BB2 v0.22 is frozen. BB1 v0.14 remains the promoted baseline (MD5 `85ad58cbabcc52e53cb250b2abaddcd6`, SHA-256 `546d9ac6c56904e9690bc6acbe33ee0a1266e0e84367e8e93230e1e6c9731fb6`). Stable-Retro/Gambatte now reproduces KLL1 round-start. Experimental v0.16-v0.18b identified several real ROM-data virtualization bugs, but none is promoted. The current frontier is a guarded v0.18b probe proving that control unexpectedly re-enters relocated BB1 startup `$4150` at frame 2094, with `SP=$DFFD` and top stack word `$41B1`; the normal candidate then clears `$C200` from round 3 (`2`) to 0 at frame 2095. Two jump-table guesses (`$29E3->$69E3` and `$2C7F->$6C7F`) did not change the reset. Resume by tracing the control edge to `$4150`, especially scheduler/context-return and indirect-jump paths; do not patch the startup clear itself. Use `BubbleBobbleDX-experimental-v0.18b-source.zip` only as unpromoted diagnostic scaffolding. After every tool call, send a short progress update before making another tool call.

## 2026-10-13 edgeprobe18b preparation — unpromoted / not executed

Static follow-up to the authoritative frame-2094 `$4150` startup re-entry frontier prepared a tighter discriminator on top of experimental v0.18b/startprobe18b. No ROM was built and no promoted code changed; BB1 v0.14 remains promoted and BB2 v0.22 remains frozen.

New diagnostic behavior after the existing KLL1 harness arms `$FFF9=$5A`:

- `$FFEB=$C1`: `host_context_ret` was about to resume logical `$0150`; `$FFE3-$FFE4` record the selected task SP, `$FFE6-$FFE7` its first word, and `$FFE8-$FFE9` the next word.
- `$FFEB=$C2`: `host_indirect_jp` was about to dispatch logical `$0150`; the same fields record the RST `$08` stack pointer, its return word (which identifies the JP-HL site), and the enclosing stack word.
- `$FFEB=$C4`: relocated startup `$4150` was reached without either earlier discriminator firing; this is the fallback startup-entry trap.

Why this discriminator matters: the previously captured `$41B1` at `$DFFD` may be an older call/interrupt return word exposed after a wrapper consumes or rewrites another return slot; it does not by itself prove a direct `CALL $4150`. In particular, `host_context_ret` can relocate a saved logical `$0150` to `$4150`, and `host_indirect_jp` can rewrite an RST `$08` return slot to `$4150` before `RET`.

The injected host assembly was syntax/layout validated with RGBDS v1.0.3 and links with `host_end=$20B8`, below the existing `$3E00` host limit. This is assembly-only evidence, not runtime validation.

Runtime execution is blocked in this session because the source rollover correctly omits ROMs. To rebuild/run the diagnostic, restore the exact patched inputs already required by the builder:

- `Classic Bubble Bobble (USA) [SMS physics & save patch by thisJUSTin816 v1.0].gbc` — MD5 `2c4c0b9cc0c106051fb195e4ed3365d9`
- `Bubble Bobble (USA, Europe) [Password save patch by thisJUSTin816 v1.0].gb` — MD5 `b093fd9aa903453c1b30703738159a49`
- `Bubble Bobble Part 2 (USA, Europe) [Tearing fix & save patch by thisJUSTin816 v1.1].gb` — MD5 `f2ef3b62b6859cc89bbb8494bb4057b2`

Exact next runtime step: build `edgeprobe18b`, replay the deterministic KLL1 Gambatte harness, and read `$FFEB`. A `$C1` result proves scheduler/context-return supplied `$0150`; `$C2` proves an indirect JP-HL path and its captured first word identifies which of `$080B/$0CB7/$29E2/$2C7E` invoked it; `$C4` narrows the remaining search to another/direct path (including RST `$00`). Do not promote from this diagnostic alone.
