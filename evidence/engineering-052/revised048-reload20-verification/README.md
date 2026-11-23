# Reload audit execution receipts

Both actual offline audit subprocesses exited zero. Receipt 01 binds the initial
635-payload draft and its original verifier/index before documentary additions
and explicit pack/heap/installed-file scope checks. Receipt 02 binds the final
638-payload seal. Each retains its actual argv, wait result, stdout/stderr,
verifier/helper bytes and index snapshot; source and index were unchanged during
each run. These directories are execution receipts, not separate standalone
copies of the complete proof tree. Use the sibling revised048-reload20 verifier
for the final replay. No game, process wait API or recording is reopened by that
verifier.
