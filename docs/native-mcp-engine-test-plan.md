# Native MCP Engine — Validation Plan

Run from repository root with Python 3.12+:

```powershell
python -m unittest tests.test_native_mcp_engine -v
python -m unittest discover -s tests -v
```

## Required test cases

- inspect valid UTF-8 text and record SHA-256;
- diff equal and changed text files;
- represent binary diffs without decoding binary bytes as text;
- reject absolute paths and traversal outside a configured root;
- reject files above the configured size limit;
- prove copy preview creates no file;
- copy into a new destination and compare source/destination SHA-256;
- refuse to overwrite an existing destination and preserve its bytes;
- verify error output does not claim a write occurred.

## Gate labels

- **PASS:** command/test completed and the exact output is retained.
- **FAIL:** command/test ran and found a failure.
- **SKIPPED:** a required dependency or environment was intentionally unavailable.
- **UNKNOWN:** no run evidence exists, or the evidence cannot be tied to the tested commit.

Do not treat a green static test as proof of MCP protocol interoperability or remote security.
