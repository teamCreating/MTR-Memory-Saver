# External verification receipt

The actual project-venv subprocess exited 0 and reconstructed the failed reload/diagnostic result exactly from 95 indexed payloads. `execution.json` preserves argv/time/exit and before/after verifier SHA plus the seal index fingerprint; stdout/stderr are original subprocess bytes. `verification-result.json` proves preservation of a stopped, unaccepted attempt, not successful game input or reload. It does not read the live process, growing native snapshots or omitted JFR binary.
