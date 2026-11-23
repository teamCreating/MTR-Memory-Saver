# Waiter batch verification

The main frozen payload is `../reload-wait-failfast`. `payload-verification.json` records actual local size/hash/inventory checks; `peer-review.json` is explicitly an independent agent-reported read-only review, not a forged raw terminal receipt. Final 16-test Windows output and original intermediate failure remain in the main tree.

Existing reference-only catalog generation adds exactly 8 frozen source copies (476 to 484), preserving all original records. `inventory-stdout.log` is the exact newly generated catalog; execution and stderr are retained. Existing `minecraft_testkit verify` actually exits 0 with 484 historical scripts, 2 datasets and 11 sample files. No archived Python was executed by this catalog check.

The first catalog invocation omitted explicit UTF-8, and its existing non-GBK path caused a UnicodeEncodeError. `inventory-attempt-01/stderr.log` is the original child stderr. Its assessment clearly labels the separately reported wrapper exit and unavailable child stdout/exit receipt; no catalog had been written. The successful invocation uses `-X utf8` and preserves exact raw stdout/stderr. No original evidence or product source was changed to avoid that error.

`sha256-index.json` covers this verification tree except itself. These local checks do not replace CI or any live reload/consumer acceptance.
