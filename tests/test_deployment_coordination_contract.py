from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WINDOWS = ROOT / "scripts" / "windows"


def _read(name: str) -> str:
    return (WINDOWS / name).read_text(encoding="utf-8")


def test_managed_deployment_owns_coordination_marker_and_tasks() -> None:
    script = _read("Invoke-PDPOneManagedFastDeployment.ps1")

    assert "Global\\PDP-One-Deployment-Coordinator" in script
    assert "deployment-in-progress.json" in script
    assert "Suspend-PDPOneCompetingTasks" in script
    assert "Restore-PDPOneCompetingTasks" in script
    assert "Stop-ScheduledTask" in script
    assert "Disable-ScheduledTask" in script
    assert "Enable-ScheduledTask" in script

    marker_remove = script.rfind("Remove-PDPOneCoordinationMarker")
    task_restore = script.rfind("Restore-PDPOneCompetingTasks")
    assert marker_remove < task_restore


def test_startup_defers_while_deployment_is_active() -> None:
    script = _read("Start-PDPOne.ps1")

    marker_check = script.index("if (Test-PDPOneDeploymentInProgress)")
    startup_mutex = script.index("Global\\PDP-One-Stable-Startup")
    disk_guard = script.index("Invoke-PDPOneDiskGuard.ps1")

    assert marker_check < startup_mutex < disk_guard
    assert "deployment-in-progress.json" in script


def test_mcp_self_heal_is_registry_only_and_deployment_aware() -> None:
    script = _read("Ensure-PDPOneMcpHealthy.ps1")

    assert "deployment-in-progress.json" in script
    assert "docker compose build mcp" not in script
    assert "local_image_build_performed = $false" in script
    assert "--no-build" in script
    assert "--pull never" in script


def test_target_images_remain_pinned_until_active_state_is_committed() -> None:
    script = _read("Invoke-PDPOneRegistryFastDeployment.ps1")

    assert "pdp-one-deploy-pin-" in script
    assert "New-PDPOneImagePin" in script
    assert "image_pins_left_for_recovery" in script

    state_commit = script.index("Set-Content -LiteralPath $lastStatePath")
    pin_removal = script.index("Remove-PDPOneImagePins", state_commit)
    assert state_commit < pin_removal


def test_coordination_never_prunes_volumes() -> None:
    combined = "\n".join(
        _read(name)
        for name in (
            "Invoke-PDPOneManagedFastDeployment.ps1",
            "Invoke-PDPOneRegistryFastDeployment.ps1",
            "Start-PDPOne.ps1",
            "Ensure-PDPOneMcpHealthy.ps1",
        )
    ).lower()

    assert "docker volume prune" not in combined
    assert "volume prune" not in combined
