# Neutral observer 1.0.2 live native attribution

Captured 2026-11-16 14:21:51–14:22:14 (UTC+08:00). This is an independently frozen **live startup prefix** from PID 41800, not a final process-exit archive, gameplay acceptance, or performance qualification.

`capture-02/diagnostic-review.json` passes the committed fail-closed native diagnostic consumer. All raw log lines remain in `capture-02/logs/latest.log`. Exactly one completed native reload contains one paired `before_native_invalid_log` / `native_fallback_return` call. Empty model and texture strings enter the official generated default `RailResource(String,String,ResourceProvider)` constructor, and the native call returns `org.mtr.model.BlockbenchModelLoader`. The pair accounts for the exact `Invalid model!` line 118. No unreviewed native errors remain in this prefix. The independent `Failed to fetch user properties` error at line 79 remains classified as requiring contextual review.

The actual JVM was created at `2026-11-16T06:10:21.0898600Z`, observed independently before and after capture using `Win32_Process`. Both receipts retain PID, executable, full command line and UTC creation time. Launch-receipt PID and plan hash match. The installed mods are:

| Role | Artifact | SHA-256 |
| --- | --- | --- |
| Official MTR | `MTR-neoforge-4.1.0-beta.2+1.21.1.jar` | `ff2b753d03f2bcc000d053a9014e4250c8ba720daa9b69b6899fe7dc26be1efa` |
| Companion | `mtr-memory-saver-official-nf248-0.4.6.jar` | `dd47f6ae4daa4139b9ada9196d757db634a79ebdd7fa5f06083719d764285997` |
| Observer | `mtr-native-observer-official-nf248-1.0.2.jar` | `1f5a3f9721bd7199cd952f4926afa8cf40996cf76fdc9484a9372f45d1664167` |

`capture-02/capture.json` records each of the 16 source-pack and installed-pack hashes, all equal to the launch plan; it also records all 28 observer class hashes and all 25 exact observer build-input checks. All build inputs match, as do the launcher source and captured options. The observer metadata is extracted from the actual installed JAR. Consumer sources, review contract, observer build receipt and build inputs are preserved under `capture-02/`, so later source edits do not silently change this classification. Referenced source/runtime proofs in the reviewed contract remain repository-relative and are checked by hash during replay.

Six raw reads preserve three advancing snapshot timestamps (`06:22:09.348122700Z`, `06:22:10.395111700Z`, `06:22:11.396208800Z`) and their natural duplicate reads. Each reports `in_world=true`, `screen=null`, `window_active=true`, `mouse_grabbed=true`, registrations `1091 / 1092 declarations`, `native_pending=0`, one started/completed resource epoch, one started/completed native diagnostic, and zero observation errors. Repeated reads of an unchanged one-second published snapshot are retained; they are not independent runtime samples.

## Keyboard-path finding and limits

`bytecode/receipt.json` pins the actual installed NeoForge 21.1.248 patched-client JAR, `javap.exe`, dump commands and all three installed mods' mixin descriptors. `capture-02/capture.json` also pins the exact `KeyboardHandler` and `Minecraft` class bytes. The raw `javap` output is preserved. These are the distributed patched-class bytes; no live redefinition or UI operation was performed by this review.

- `KeyboardHandler.keyPress` checks the GLFW window handle at offsets 0–12. F2 uses the screenshot binding and returns at offsets 297–345, before ordinary screen/key dispatch.
- `keyPress` determines the current-screen gates at offsets 594–662. ESC calls `Minecraft.pauseGame` at offsets 750–763. `pauseGame` gates on `screen`, and does **not** test `overlay`. Therefore an overlay alone does not explain an ignored ESC with a null screen.
- Ordinary key mappings are set/clicked at offsets 883–910. `Minecraft.tick` calls `handleKeybinds` only with null overlay and null screen (offsets 339–366). Within `handleKeybinds`, chat is consumed at offsets 526–545 and the command binding has another screen/overlay gate at offsets 548–579. `charTyped` also checks `getOverlay()`.
- `isWindowActive()` simply returns the tracked window-active field. The captured true active/grabbed fields exclude an inactive/ungrabbed state at those specific timestamps. They do not prove delivery of a particular external T, slash, W or ESC event. Observer 1.0.2 does not expose the overlay object. No overlay presence/absence or input-delivery cause is claimed from `screen=null` or a successful F2 screenshot.

## Reproduction and preserved failed attempt

Run `python -X utf8 evidence/engineering-048/neutral-runtime-02-review/replay_review.py` from the repository. It imports the frozen consumers, verifies their sources and all observer build inputs, verifies the full raw startup-header/prefix witness, checks repository proof hashes, and reproduces the saved attribution result exactly. `replay-result.json` preserves the completed replay.

`capture_review.py --instance <existing-instance> --output <new-directory> --pid <actual-pid>` is read-only with respect to the instance. It fails if the output exists, retains evidence on failure, queries process identity before/after, hashes exact mods/source packs/installed packs, preserves all sampled snapshots, and runs attribution only after settled observations. The capture itself sends no key, attach, launch, export, stop or world mutation request.

`capture-01/` preserves the first failed attempt, including its exact script and every raw byte captured. That script incorrectly required all four observations to have different timestamps; its final read occurred inside the observer's one-second publication period and legitimately repeated the third snapshot. The corrected capture retains every duplicate, requires monotonic non-regression and at least three distinct observed timestamps within a bounded 15-second sampling window. The failed attempt is not removed or relabeled as a successful capture.

`sha256.json` indexes all evidence payloads except itself. The parent task owns full process-exit sealing, UI/input diagnosis and any further gameplay or performance validation. MTR v6 remains outside this review.
