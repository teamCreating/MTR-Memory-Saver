# Initial String-backed digest candidate

This first experimental v0.2.9 implementation wraps the original String directly in CharBuffer. Its actual-cache comparison passes all 8,534 real inputs, 85 synthetic cases, 64 concurrent reads and null checks, and rejects the unchanged-baseline allocation control. See digest-audit.json and digest-audit-result.json in this folder.

Eight hashes reduce ASCII allocation from 134,221,760 to 71,072 bytes and mixed text from 536,874,976 to 71,264 bytes. Small inputs remain unchanged. Single timings regress from 412 to 1071 ms for ASCII, 454 to 1083 ms for mixed text and 1518 to 2181 ms for Unicode. This regression motivated the array-backed revision; this artifact is preserved and was not installed.

SHA-256: db813fd95264f00a380aba619702b1548d67957a88907a3903767d05e7b15adf. The complete initial build sources and reports are preserved here; only ResourceTextDigest differs from the revised candidate. Source paths in the original build record refer to their original locations, with matching bytes in this archived src tree. No native gameplay or process-RAM acceptance is claimed.
