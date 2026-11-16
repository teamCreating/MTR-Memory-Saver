# Prepared recorder/consumer commands; not executed by this batch

Run from `C:\Users\ben_l\Documents\Coding\resoucepack update\vehicle-memory` in two PowerShell 7 terminals. Both output directories must be new. The 1091 distinct IDs and 1092 declarations are the expectations recorded for this exact owned049c launch, not reader defaults. These commands observe only; an actual input controller must still apply the normal focus/screen and published-before guards. A paused/ineligible screen must not trigger input.

Recorder terminal:

```powershell
.\.venv\Scripts\python.exe -X utf8 tools/reload_before_recorder.py record --instance .cache/acceptance/official-nf248-owned-049c --output .cache/acceptance/owned-049c-reload-recorder-attempt05 --expected-count 1091 --expected-declarations 1092 --interval-seconds 1 --log-prefix-witness evidence/engineering-050/neutral103-startup/capture-01/observation/native-log-at-completion.log
```

Consumer terminal, after the recorder has successfully initialized:

```powershell
.\.venv\Scripts\python.exe -X utf8 tools/observe_packaged_client.py reloads --instance .cache/acceptance/official-nf248-owned-049c --output .cache/acceptance/owned-049c-reload-observation-attempt05 --expected-count 1091 --expected-declarations 1092 --duration 7200 --interval 5 --stable-seconds 60 --require-world --unpaused --reload-recorder .cache/acceptance/owned-049c-reload-recorder-attempt05 --require-reloads 20 --log-prefix-witness evidence/engineering-050/neutral103-startup/capture-01/observation/native-log-at-completion.log
```

After each actual guarded F3+T input has produced its original external receipt, confirm that exact receipt. Replace the example receipt path with the actual one; do not run confirmation if input was rejected or no receipt exists:

```powershell
.\.venv\Scripts\python.exe -X utf8 tools/reload_before_recorder.py confirm --output .cache/acceptance/owned-049c-reload-recorder-attempt05 --receipt .cache/acceptance/actual-input-receipt.json
```

Every attempted input must remain in the ledger, including failures. The consumer requires 20 consecutive verified full native reloads; issuing or confirming inputs alone cannot grant completion. Stop requests use a new `stop-request` file in the relevant output directory. Preserve the session's actual terminal exit and summary/session-end; these observation stop requests do not stop the game JVM.
