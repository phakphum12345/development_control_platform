from tools.local_runner_agent.terminal_isolation import (
    IsolationAssessment,
    assess_isolation_backend,
    require_verified_isolation,
)


def test_linux_without_bubblewrap_is_blocked():
    result = assess_isolation_backend("linux", executable_lookup=lambda _name: None)
    assert result.platform == "linux"
    assert result.backend == "bubblewrap-namespaces-seccomp"
    assert result.state == "BLOCKED"
    assert not result.available
    assert not result.network_isolated
    assert not result.filesystem_isolated
    assert not result.process_tree_contained


def test_linux_with_bubblewrap_is_only_ready_for_acceptance():
    result = assess_isolation_backend(
        "linux", executable_lookup=lambda _name: "/usr/bin/bwrap"
    )
    assert result.state == "READY_FOR_ACCEPTANCE"
    assert result.available
    assert not result.network_isolated
    assert not result.filesystem_isolated
    assert not result.process_tree_contained
    try:
        require_verified_isolation(result)
    except RuntimeError as exc:
        assert "execution is blocked" in str(exc).lower()
    else:
        raise AssertionError("unverified isolation must never authorize execution")


def test_windows_requires_native_appcontainer_launcher():
    result = assess_isolation_backend("windows")
    assert result.backend == "appcontainer-lpac"
    assert result.state == "BLOCKED"
    assert not result.available


def test_macos_requires_signed_sandbox_helper():
    result = assess_isolation_backend("macos")
    assert result.backend == "signed-app-sandbox-helper"
    assert result.state == "BLOCKED"
    assert not result.available


def test_verified_state_requires_all_enforcement_claims():
    incomplete = IsolationAssessment(
        platform="linux",
        backend="bubblewrap-namespaces-seccomp",
        state="VERIFIED",
        available=True,
        network_isolated=True,
        filesystem_isolated=True,
        process_tree_contained=False,
        reason="missing process containment",
    )
    try:
        require_verified_isolation(incomplete)
    except RuntimeError:
        pass
    else:
        raise AssertionError("incomplete isolation must remain blocked")


def test_unknown_platform_is_blocked():
    result = assess_isolation_backend("plan9")
    assert result.platform == "unsupported"
    assert result.state == "BLOCKED"
