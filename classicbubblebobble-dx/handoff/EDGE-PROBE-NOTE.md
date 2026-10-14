# BB1 edgeprobe18b diagnostic

Unpromoted diagnostic source derived from experimental v0.18b/startprobe18b.

After the KLL1 harness arms HRAM `$FFF9=$5A`, the probe freezes before destructive startup whenever:

- `$FFEB=$C1`: `host_context_ret` is about to resume logical `$0150`.
- `$FFEB=$C2`: `host_indirect_jp` is about to dispatch logical `$0150`.
- `$FFEB=$C4`: relocated startup `$4150` was reached without either earlier probe firing (fallback path).

Captured bytes:

- `$FFE3-$FFE4`: relevant stack pointer (little endian).
- `$FFE6-$FFE7`: first stack word.
- `$FFE8-$FFE9`: second stack word.

This source has not been built or run because the exact patched ROM inputs are not present in the current session. Do not promote it.

Assembly-only validation: the injected host source assembled and linked successfully with RGBDS v1.0.3; validation `host_end=$20B8`. This proves syntax/layout only, not game behavior.
