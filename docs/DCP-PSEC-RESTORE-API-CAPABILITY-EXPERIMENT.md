# PSEC Disposable NTFS Restore API Capability Experiment

**Protocol family:** PSEC DACL Protocol v1  
**Status:** EXPERIMENTAL — exact-head Windows evidence pending  
**Target:** Newly created harness-owned NTFS files only  
**Production writer:** BLOCKED

## 1. Objective

Determine whether documented Windows file-security APIs can restore the original DACL descriptor state captured in immutable S0 after a DACL write changes the descriptor control word.

The experiment does not assume that any candidate API succeeds. Each candidate receives a new disposable file, an independent S0 snapshot, one controlled mutation to S1, and one candidate restoration attempt followed by an independent S2 read-back.

## 2. Candidate Matrix

| Candidate | API | Restore operation | Purpose |
|---|---|---|---|
| A | SetSecurityInfo | Handle-based DACL + UNPROTECTED flag | Test whether unprotecting recomputes the original control state |
| B | SetNamedSecurityInfoW | Name-based DACL + UNPROTECTED flag | Compare the documented name-based counterpart |
| C | SetFileSecurityW | Legacy DACL write with original protected control bit | Test whether the input descriptor control word can restore the original state |
| D | SetFileSecurityW | Legacy DACL write with AUTO_INHERIT_REQ set | Isolate the effect of the auto-inheritance request bit |

SetFileSecurityW is obsolete and is included only as a bounded compatibility probe. Microsoft recommends SetNamedSecurityInfo instead. A successful experiment result does not promote the legacy API to a production writer.

## 3. Per-Candidate Procedure

1. Create a unique temporary directory on NTFS.
2. Create one new file with an explicit non-NULL protected DACL.
3. Retain the original file handle; reject directory and reparse-point targets.
4. Capture S0 from that handle using identity-before/read/identity-after checks.
5. Verify the immutable snapshot digest before any mutation.
6. Apply the same controlled SetSecurityInfo DACL write to create S1.
7. Apply exactly one allowlisted restore candidate.
8. Read S2 independently through the retained handle.
9. Verify target identity and compare S2 to S0 with STRICT_DESCRIPTOR_EQUALITY.
10. Close the owned handle and remove the exact temporary file and directory.

Every candidate uses its own new object. No candidate inherits state from a prior candidate.

## 4. Evidence

Each result records:

- Candidate API name and return code.
- Transaction UUID and SHA-256 snapshot digest.
- Target volume serial and 128-bit file identity.
- S0, S1, and S2 control words.
- S0, S1, and S2 exact DACL bytes.
- Inherited ACE counts.
- API and read-back errors.
- Strict comparison result and mismatch dimensions.
- Cleanup verification.

An API success return code is not restoration success. Only an independently read-back S2 equal to S0 under STRICT_DESCRIPTOR_EQUALITY is RESTORED_EXACT.

## 5. Safety and Non-Regression

- No caller-supplied path is accepted.
- No production object is opened or modified.
- No SACL, owner, or group write is attempted.
- No privilege is enabled or expanded.
- No undocumented native API is used.
- No candidate is silently retried through a different API.
- The four existing DACL Comparison Profiles remain unchanged.
- Existing SetSecurityInfo strict round-trip failure remains visible.
- Native Writer and Transactional ACL Mutation remain BLOCKED.

## 6. API Documentation Leads

Microsoft documents SetSecurityInfo as the handle-based file-system API and SetNamedSecurityInfo as its name-based counterpart. Microsoft documents SetSecurityDescriptorControl as an in-memory security-descriptor control-bit operation, not an object persistence call. SetKernelObjectSecurity is explicitly not the API for file-system objects.

SetFileSecurityW is documented as obsolete. A Microsoft External Staff Moderator has described a possible difference in how SetFileSecurityW and SetNamedSecurityInfoW process auto-inheritance control bits. That report is treated only as a test lead, not as a guarantee.

References:

- SetSecurityInfo: https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-setsecurityinfo
- SetNamedSecurityInfoW: https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-setnamedsecurityinfow
- SetFileSecurityW: https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-setfilesecurityw
- SetSecurityDescriptorControl: https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-setsecuritydescriptorcontrol
- SECURITY_DESCRIPTOR_CONTROL: https://learn.microsoft.com/en-us/windows/win32/secauthz/security-descriptor-control
- Microsoft Q&A behavior lead: https://learn.microsoft.com/en-us/answers/questions/6008962/setfilesecurityw-changes-control-bits-from-0x8404

## 7. Acceptance

A candidate is considered experimentally capable for this tested scenario only if:

- Its API call succeeds.
- The retained target identity remains unchanged.
- The independent S2 read-back is structurally valid.
- STRICT_DESCRIPTOR_EQUALITY reports RESTORED_EXACT against immutable S0.
- Cleanup is verified.

A result on one Windows Server / NTFS build is not universal support evidence. Production use requires additional supported-build coverage, code review, security review, and a separate authorization gate.
