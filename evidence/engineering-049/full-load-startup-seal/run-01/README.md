# Official 0.4.7 startup and selected DC01 side view

Sealed on 2026-11-16 (UTC+08:00). This checkpoint binds official NeoForge
21.1.248, official MTR 4.1.0-beta.2, Memory Saver **0.4.7** and installed neutral
observer **1.0.2** to actual PID **58468**, created at
`2026-11-16T11:17:51.198Z`. The actual Win32 process query in `assessment-01/`
was acquired while that PID was still alive; subsequent assessments explicitly
reuse that retained historical receipt. This frozen startup checkpoint does
not derive final save or exit acceptance from later client activity.

`capture-01/` retains the exact initial snapshot, full log prefix, native epoch
and diagnostic streams, launch plan, launch receipt, options and original F2
image. Its core reads occurred at `11:27:07.324–11:27:07.358Z`; `freeze.json`
records individual byte counts, SHA-256 and unchanged source sizes before and
after those reads. The collector prefix contains **394** strictly advancing
native snapshots through `11:27:06.489324Z`, selected by actual capture time
at or before the freeze cutoff. Original collector reads and their retained
prefix boundaries are preserved separately.

## Accepted limited scope

`assessment-03/assessment.json` passes the initial uninterrupted native startup
window from `11:20:20.965025400Z` to `11:21:21.692182Z`: **60.727157 seconds**,
**60 samples**, maximum native timestamp gap **1.064498 seconds**, and maximum
capture delay **0.99428 seconds**. Every accepted window sample is in world,
unpaused, screen-null and natively settled, with pending work zero and observer
errors zero. The native registry reports **1,092 declarations / 1,091 distinct
IDs**; resource epoch 1 has paired HEAD/RETURN, nesting 1 and no in-flight work.
DC01 cab resources retain **5/6 floors and 10 doorways each**.

All sixteen original/installed pack pairs and all three actual installed mod
hashes matched the frozen plan during assessment; their bindings and original
source paths remain recorded. The pack files and large official MTR JAR are not
duplicated into this checkpoint. The copied companion JAR SHA-256 is
`e8b5b40230d0f44c541c12b32c8a30d4c2ea056b8a972335ae10166496837a99`.
The copied observer 1.0.2 JAR SHA-256 is
`1f5a3f9721bd7199cd952f4926afa8cf40996cf76fdc9484a9372f45d1664167`.

The frozen strict diagnostic consumer attributes the native `Invalid model!`
line to the exact official empty default-rail model/texture constructor and
actual fallback return. The account-property network error remains in the raw
log and contextual-review result. Diagnostic attribution grants no broader
visual or performance conclusion.

The independently inspected original image is
`capture-01/screenshots/2026-11-16_19.25.21.png` (SHA-256
`25537b27b8da9c6afa06b8c94bd7b03f4c96fbabc2238a6b5a661476311c0776`).
It shows the two silver DC01 side bodies, red stripe, windows, visible open
doors and car junction. Both outer noses are cropped and night detail is
limited. Only these selected visible features are accepted. The adjacent
native samples preserve the actual **ChatScreen → screen-null** transition:
`11:25:20.738012300Z` and `11:25:21.745584500Z`, both in world, unpaused,
settled, at rail progress 160, speed 0 and door value 1. The PNG has no chat
overlay. These body-context samples do not replace the earlier screen-null
startup window.

## Retained failures and source identity

The real collector error at `11:26:17.199589Z` is retained verbatim:
`PermissionError(13, '另一个程序正在使用此文件，进程无法访问。', None, 32)`.
It occurs after the accepted startup minute and selected PNG but before the
core freeze. **Whole-run collection is not error-free.**

`assessment-01/` preserves the first failure and exact failed script: its
predicate incorrectly required the entire collector to be error-free.
`assessment-02/` preserves the second failure and exact failed script: it
incorrectly required screen-null for both image-adjacent samples.
`assessment-03/` preserves the fresh successful execution and exact source,
with the actual error and UI transition kept visible.

`build-bindings/` preserves the rejected current-source-only binding.
`build-bindings-02/` binds **44 companion inputs and 25 observer inputs** to
exact manifest hashes. At binding time, current `build.gradle`,
`tools/probes/io/java/dev/abenli/probeio/AtomicSnapshot.java`, and
`tools/probes/neutral/observer.json` differ from installed observer 1.0.2 inputs.
Their exact historical inputs are explicitly resolved from the prior sealed
engineering-048 archive and copied here. The recorded current differences
remain visible. The current repaired observer is not attributed to this run.

No boarding/passenger interaction, interior/cab access, full consist geometry,
20 consecutive reloads, two-hour route, controlled performance or final-exit
acceptance follows from this checkpoint. The neutral observer supplies no
companion permit/workspace counters. Product code, games, original packs and
v6 status are not modified by this sealing task.

## Audit the retained files

`sha256-index.json` covers every payload in this directory except the index
itself. `verification-result.json` records an independent sealed-only check of
the frozen read receipts, collector prefix and startup statistics, explicit
process identity, exact installed artifacts, both build-input manifests and
the replayed frozen strict native diagnostic result. No current game or
workspace sources are read by that verification.

The capture/assessment/binding scripts are exact execution records; the
assessment command depends on its original instance, original packs and
then-current consumer sources. It should not be rerun over later instance or
source changes and treated as a replay of this checkpoint. For independent
inventory checks, hash each indexed relative path and compare both SHA-256
and byte count, using a fresh output path and leaving all retained receipts
unchanged.
