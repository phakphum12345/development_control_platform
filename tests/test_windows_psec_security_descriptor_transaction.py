from __future__ import annotations

import unittest
from dataclasses import replace

from tools.local_runner_agent.windows_psec_native_handles import HandleIdentity
from tools.local_runner_agent.windows_psec_security_descriptor_transaction import (
    DescriptorCandidate,
    DescriptorSnapshot,
    NativeSecurityDescriptorTransaction,
    NativeSecurityDescriptorTransactionError,
    TransactionTarget,
)


PACKAGE_SID = "S-1-15-2-123-456-789"
IDENTITY_A = HandleIdentity(1, "00" * 16, True, 0x10, 0)
IDENTITY_B = HandleIdentity(1, "11" * 16, False, 0x80, 0)
ORIGINAL = DescriptorSnapshot(True, False, b"ACL-ORIGINAL-BYTES", 0x1000, 1, 2, 1)


class FakeHandleSecurityApi:
    def __init__(self):
        self.identities = {10: IDENTITY_A, 11: IDENTITY_B}
        self.states = {10: ORIGINAL, 11: ORIGINAL}
        self.writes = []
        self.fail_read_for = set()
        self.fail_write_for = set()
        self.write_then_raise_for = set()
        self.fail_rollback_for = set()
        self.fail_plan_for = set()
        self.identity_override = {}

    def query_identity(self, handle):
        return self.identity_override.get(handle, self.identities[handle])

    def read_dacl(self, handle):
        if handle in self.fail_read_for:
            self.fail_read_for.remove(handle)
            raise RuntimeError("injected read failure")
        return self.states[handle]

    def build_candidate(self, snapshot, target, package_sid):
        if target.handle in self.fail_plan_for:
            raise RuntimeError("injected plan failure")
        return DescriptorCandidate(
            True, False, snapshot.dacl_bytes + b"|PACKAGE-ACE|",
            snapshot.dacl_control_flags, 1, 2, snapshot.ace_count + 1,
        )

    def write_dacl(self, handle, state):
        self.writes.append((handle, state))
        if handle in self.fail_write_for:
            self.fail_write_for.remove(handle)
            raise RuntimeError("injected write failure")
        self.states[handle] = (
            state if isinstance(state, DescriptorSnapshot) else state.as_snapshot()
        )
        if handle in self.write_then_raise_for:
            self.write_then_raise_for.remove(handle)
            raise RuntimeError("injected ambiguous write failure")
        if handle in self.fail_rollback_for and isinstance(state, DescriptorSnapshot):
            raise RuntimeError("injected rollback failure")


def targets():
    return [
        TransactionTarget("root", 10, IDENTITY_A, 0x20),
        TransactionTarget("workspace-file", 11, IDENTITY_B, 0x001200A9),
    ]


class NativeSecurityDescriptorTransactionTests(unittest.TestCase):
    def test_applies_all_candidates_and_verifies_read_back(self):
        api = FakeHandleSecurityApi()
        result = NativeSecurityDescriptorTransaction(api).apply(targets(), PACKAGE_SID)
        self.assertEqual(result.state, "APPLIED_VERIFIED")
        self.assertEqual(result.attempted_targets, 2)
        self.assertEqual(result.verified_targets, 2)
        self.assertEqual(len(api.writes), 2)

    def test_completes_all_preflight_before_first_write(self):
        api = FakeHandleSecurityApi()
        api.fail_plan_for.add(11)
        result = NativeSecurityDescriptorTransaction(api).apply(targets(), PACKAGE_SID)
        self.assertEqual(result.state, "PREFLIGHT_REJECTED_BLOCKED")
        self.assertEqual(api.writes, [])

    def test_apply_failure_rolls_back_in_reverse_order(self):
        api = FakeHandleSecurityApi()
        api.fail_write_for.add(11)
        result = NativeSecurityDescriptorTransaction(api).apply(targets(), PACKAGE_SID)
        self.assertEqual(result.state, "ROLLED_BACK_VERIFIED")
        self.assertEqual([handle for handle, _ in api.writes], [10, 11, 11, 10])
        self.assertEqual(api.states, {10: ORIGINAL, 11: ORIGINAL})

    def test_ambiguous_write_failure_is_included_in_rollback_journal(self):
        api = FakeHandleSecurityApi()
        api.write_then_raise_for.add(11)
        result = NativeSecurityDescriptorTransaction(api).apply(targets(), PACKAGE_SID)
        self.assertEqual(result.state, "ROLLED_BACK_VERIFIED")
        self.assertEqual(api.states, {10: ORIGINAL, 11: ORIGINAL})
        self.assertEqual([handle for handle, _ in api.writes], [10, 11, 11, 10])

    def test_rollback_failure_is_fatal_and_blocks_success(self):
        api = FakeHandleSecurityApi()
        api.fail_write_for.add(11)
        api.fail_rollback_for.add(10)
        result = NativeSecurityDescriptorTransaction(api).apply(targets(), PACKAGE_SID)
        self.assertEqual(result.state, "ROLLBACK_INCOMPLETE_BLOCKED")
        self.assertTrue(result.rollback_errors)
        self.assertNotEqual(result.state, "APPLIED_VERIFIED")

    def test_identity_drift_before_write_causes_preflight_rejection(self):
        api = FakeHandleSecurityApi()
        api.identity_override[11] = replace(IDENTITY_B, file_id="22" * 16)
        result = NativeSecurityDescriptorTransaction(api).apply(targets(), PACKAGE_SID)
        self.assertEqual(result.state, "PREFLIGHT_REJECTED_BLOCKED")
        self.assertEqual(api.writes, [])

    def test_identity_drift_immediately_before_apply_rolls_back_prior_target(self):
        api = FakeHandleSecurityApi()
        # The first preflight query is valid; subsequent query for handle 11 drifts.
        original_query = api.query_identity
        calls = {10: 0, 11: 0}

        def changing_query(handle):
            calls[handle] += 1
            if handle == 11 and calls[handle] >= 2:
                return replace(IDENTITY_B, file_id="33" * 16)
            return original_query(handle)

        api.query_identity = changing_query
        result = NativeSecurityDescriptorTransaction(api).apply(targets(), PACKAGE_SID)
        self.assertEqual(result.state, "ROLLED_BACK_VERIFIED")
        self.assertEqual([handle for handle, _ in api.writes], [10, 10])

    def test_dacl_drift_after_preflight_blocks_target_write(self):
        api = FakeHandleSecurityApi()
        original_read = api.read_dacl
        calls = {10: 0, 11: 0}

        def changing_read(handle):
            calls[handle] += 1
            if handle == 11 and calls[handle] == 2:
                changed = replace(ORIGINAL, dacl_bytes=b"CONCURRENT-CHANGE")
                api.states[handle] = changed
                return changed
            return original_read(handle)

        api.read_dacl = changing_read
        result = NativeSecurityDescriptorTransaction(api).apply(targets(), PACKAGE_SID)
        self.assertEqual(result.state, "ROLLED_BACK_VERIFIED")
        self.assertEqual([handle for handle, _ in api.writes], [10, 10])
        self.assertEqual(api.states[10], ORIGINAL)
        self.assertEqual(api.states[11].dacl_bytes, b"CONCURRENT-CHANGE")

    def test_read_back_failure_rolls_back_target_and_previous_targets(self):
        api = FakeHandleSecurityApi()
        # Preflight reads are first; fail the second read for handle 11 (read-back).
        original_read = api.read_dacl
        calls = {10: 0, 11: 0}

        def changing_read(handle):
            calls[handle] += 1
            if handle == 11 and calls[handle] == 2:
                raise RuntimeError("injected read-back failure")
            return original_read(handle)

        api.read_dacl = changing_read
        result = NativeSecurityDescriptorTransaction(api).apply(targets(), PACKAGE_SID)
        self.assertEqual(result.state, "ROLLED_BACK_VERIFIED")
        self.assertEqual(api.states, {10: ORIGINAL, 11: ORIGINAL})

    def test_rejects_control_flags_outside_native_word(self):
        for flags in (-1, 0x10000, True):
            with self.subTest(flags=flags):
                malformed = replace(ORIGINAL, dacl_control_flags=flags)
                with self.assertRaisesRegex(NativeSecurityDescriptorTransactionError, "DACL control flags"):
                    malformed.validate(max_descriptor_bytes=1024, max_aces=16)

    def test_rejects_null_dacl_candidate(self):
        api = FakeHandleSecurityApi()
        api.build_candidate = lambda snapshot, target, sid: DescriptorCandidate(
            True, True, b"", snapshot.dacl_control_flags
        )
        result = NativeSecurityDescriptorTransaction(api).apply(targets(), PACKAGE_SID)
        self.assertEqual(result.state, "PREFLIGHT_REJECTED_BLOCKED")
        self.assertEqual(api.writes, [])

    def test_rejects_duplicate_handle_and_file_identity(self):
        api = FakeHandleSecurityApi()
        duplicate = targets() + [TransactionTarget("duplicate", 10, IDENTITY_A, 1)]
        result = NativeSecurityDescriptorTransaction(api).apply(duplicate, PACKAGE_SID)
        self.assertEqual(result.state, "PREFLIGHT_REJECTED_BLOCKED")
        self.assertEqual(api.writes, [])

    def test_rejects_invalid_package_sid_without_adapter_calls(self):
        api = FakeHandleSecurityApi()
        result = NativeSecurityDescriptorTransaction(api).apply(targets(), "S-1-5-18")
        self.assertEqual(result.state, "PREFLIGHT_REJECTED_BLOCKED")
        self.assertEqual(api.writes, [])

    def test_rejects_reparse_point_target_before_mutation(self):
        api = FakeHandleSecurityApi()
        reparse = replace(IDENTITY_B, attributes=0x400)
        result = NativeSecurityDescriptorTransaction(api).apply(
            [targets()[0], TransactionTarget("reparse", 11, reparse, 1)], PACKAGE_SID
        )
        self.assertEqual(result.state, "PREFLIGHT_REJECTED_BLOCKED")
        self.assertEqual(api.writes, [])


if __name__ == "__main__":
    unittest.main()
