# Revised 0.4.8: twenty real full-pack reloads

**Passed on NF248**, candidate SHA
`943b3d455fa3ce9d3ede74bc1a2071ece7bf70b09d9b7f829027347b53a9b588`.
Source implementation is a632149. JVM 65404 started at
2026-11-17T16:51:14.481Z (2026-11-18T00:51:14.481+08:00), with all sixteen
catalogue packs, 3072 MiB maximum/512 MiB initial heap, observer 1.0.3,
full-history JFR and NMT summary. No heap limit or acceptance gate was relaxed.
The acceptance-enable property has no production-source consumer; no acceptance
fixture/probe JAR was installed in this full-pack instance.

Twenty actual CUA F3+T receipts map to twenty distinct, consecutive native epochs
2–21. Startup epoch 1 is excluded. The original main consumer ended automatically
with status reloads_verified, passed=true, verified count=20 and longest run=20.
It retained all 1016 samples, including 417 verified observations; render-thread
reload intervals also contain ineligible/stale observations and are not described
as uniformly valid samples. Native registration remained 1091 distinct IDs and
1092 declarations. No OOM or unreviewed native error occurred. The known official
generated-default rail diagnostic is individually attributed by the unchanged
frozen native-call review, rather than hidden by a new whitelist.

The first nineteen original interim checks each measured at least sixty seconds
in both independent consumer time and native time before the next input. After
the main consumer accepted twenty, a separate startup observer on the same JVM
passed fourteen of fourteen samples: 64.99617919995217 consumer seconds and
65.4464114 native seconds, with native started=completed=21 and no in-flight work.
The recorder then stopped normally after 2458 captures and closed its process
handle. Normal Alt+F4 shutdown produced actual owned JVM and collector exit zero.

Before input 20, an inactive-window guard refused before sending any key; the
window was freshly rehydrated and activated before the successful receipt. The
explicitly parent-reported note is not an invented input receipt. The first
normal-close call was also refused after user input; fresh get_window_state and
a separately named successful retry are both retained. These are not extra
reloads or omitted confirmation attempts.

## Literal replay closure

All twenty original input-attempt directories and their literal journal prefixes,
the complete recorder journal, main and post20 sample streams, native epochs,
diagnostics and rolling-log receipt/segment dependencies are retained. Forty
selected record closures cover every input-before record, nineteen original
ready records and the final post20 publication. Redundant record payloads are
omitted; native-log receipts are followed by their actual references, without
assuming recorder and log capture ordinals coincide.

Read-time copy receipts preserve source bytes and before/after modification times.
Nineteen installed files (three mods plus sixteen packs) were independently hashed
after normal shutdown and matched the original launch plan. This is a closed-file
check; launch preflight separately checked installed bytes before creation.
The 191350424-byte JFR was actually summarized with exit zero and hashed as
`1c315f00babdb00b2b85e2bcc3628a1b683e4a296d79773229911d0a9aa32787`.
Its binary and the large collector snapshot stream are not copied or reopened by
the offline verifier. Their original recorded metadata remains. MTR, pack, world
and dependency binaries are omitted. The named candidate JAR is read from its
existing engineering-051 seal.

Run `python -X utf8 evidence/engineering-052/revised048-reload20/verify_sealed.py`.
It reuses the exact frozen producer importer and canonical reload/diagnostic
algorithms, checks all literal input attempts and nineteen bounded prefixes,
and reproduces final and post20 results. Recorded Windows paths are compared
lexically with PureWindowsPath; original instance metadata, process/wait APIs
and JFR are not queried. Only sealed files and the named tracked candidate are
read. The new constructor also reproduced the old failed seventh-reload session
exactly with zero accepted reloads; that failure retains its own artifact identity.
An initial successful replay preceded documentary additions and explicit pack,
heap and installed-hash scope checks; its original source/index/output are kept
in the sibling verification evidence. Runtime producers and acceptance gates
were not changed.

This establishes NF248 reload endurance only. NF265 packaged checks are separate;
NF265 full-pack interaction, a two-hour route and controlled performance are not
claimed here. Independent frame qualification and actual performance trials
remain unavailable, so this is not complete release acceptance.
