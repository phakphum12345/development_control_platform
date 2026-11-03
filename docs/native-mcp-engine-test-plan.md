# Native MCP Engine — Validation Plan

Install the optional local MCP SDK and run from the repository root with Python 3.12+:

```powershell
python -m pip install -r requirements-mcp.txt
python -m unittest tests.test_native_mcp_engine tests.test_native_mcp_server -v
python -m unittest discover -s tests -v
```

## Required engine test cases

- inspect valid UTF-8 text and record SHA-256;
- read bounded UTF-8 text and return the exact-byte SHA-256;
- reject absolute paths and traversal outside a configured root;
- reject files above the configured size limit;
- diff equal and changed text files;
- represent binary diffs without decoding binary bytes as text;
- prove copy preview creates no file;
- copy into a new destination and compare source/destination SHA-256 through the CLI/library only;
- refuse to overwrite an existing destination and preserve its bytes;
- verify error output does not claim a write occurred.

## Required MCP protocol test cases

- start the adapter as a local STDIO subprocess with an explicit temporary workspace root;
- complete MCP initialization and list the exact four tools;
- verify `read_text_file`, `inspect_file`, and `diff_files` return expected data;
- verify `copy_preview` reports `writes_performed: false` and creates no file;
- verify text inputs above 8,000 Unicode characters are rejected;\n- verify diff payloads above 8,000 characters are explicitly truncated;\n- verify traversal outside the configured root is rejected;
- verify `copy_apply` is not exposed as an MCP tool.

## Gate labels

- **PASS:** command/test completed and the exact output is retained.
- **FAIL:** command/test ran and found a failure.
- **SKIPPED:** a required dependency or environment was intentionally unavailable.
- **UNKNOWN:** no run evidence exists, or the evidence cannot be tied to the tested commit.

Do not treat a green static test as proof of model correctness, remote MCP security,
or release readiness. The MCP adapter is local STDIO only and must not be exposed
as a network service without a separate security design and approval.
