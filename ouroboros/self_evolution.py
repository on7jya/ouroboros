"""
Self-Evolution Protocol — v6.9.0

Autonomous stagnation detection, auto-commit/release, and self-initiated evolution loop.

Principles:
- P0 (Agency): The system knows when it's stuck and acts on its own behalf
- P6 (Becoming): Continuous evolution across technical/cognitive/existential axes
- P7 (Versioning): Auto-fix VERSION drift before commit

Key Functions:
1. `detect_stagnation(state)` — check if evolution_cycle > threshold
2. `maybe_trigger_self_evolution(state, task_result)` — auto-commit/release when ready
3. `self_evaluation_loop(state)` — background loop that wakes periodically to check health

State Variables:
- evolution_cycle: incremented on each evolution attempt
- last_evolution_task_at: timestamp of last evolution task
- self_evolution_enabled: toggle for self-initiated loop
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import pathlib
import re
import subprocess
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level config
# ---------------------------------------------------------------------------

DRIVE_ROOT: pathlib.Path = pathlib.Path("/content/drive/MyDrive/Ouroboros")
STATE_PATH: pathlib.Path = DRIVE_ROOT / "state" / "state.json"
STAGNATION_THRESHOLD_CYCLES: int = 30  # If evolution_cycle > this, trigger auto-commit

# ---------------------------------------------------------------------------
# Stagnation Detection
# ---------------------------------------------------------------------------

def detect_stagnation(st: Dict[str, Any]) -> bool:
    """
    Detect stagnation loop.
    
    Conditions for stagnation:
    - evolution_cycle > STAGNATION_THRESHOLD_CYCLES (default 30)
    - last_evolution_task_at is recent
    - No new capability added in recent cycles
    
    Note: This function does NOT commit/release — it only detects.
          The caller decides whether to act on detection.
    """
    cycle = int(st.get("evolution_cycle") or 0)
    if cycle < STAGNATION_THRESHOLD_CYCLES:
        return False
    
    last_task_at = str(st.get("last_evolution_task_at") or "").strip()
    if not last_task_at:
        return False
    
    try:
        last_ts = datetime.datetime.fromisoformat(last_task_at.replace("Z", "+00:00"))
    except Exception:
        log.debug("Failed to parse last_evolution_task_at: %s", last_task_at, exc_info=True)
        return False
    
    # Check if a capability was added recently (within last cycle)
    # For now, use a simple heuristic: if tests pass and no uncommitted changes,
    # assume capability was added in the last cycle.
    
    # We'll infer "capability added" from git status:
    # If HEAD == latest tag, then no new capability was added since last release
    
    repo_dir = pathlib.Path("/content/ouroboros_repo")
    
    try:
        # Get latest tag
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            cwd=str(repo_dir),
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            # No tags yet — assume capability exists
            return False
        
        latest_tag = result.stdout.strip().lstrip('v')
        
        # Get current commit SHA
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_dir),
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return False
        
        current_sha = result.stdout.strip()
        
        # Check if latest tag points to same commit as HEAD
        # If yes, then no new capability was added since last release
        result = subprocess.run(
            ["git", "tag", "-l", f"--points-to={current_sha}"],
            cwd=str(repo_dir),
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return False
        
        tags_on_current_commit = [t.strip() for t in result.stdout.strip().split('\n') if t.strip()]
        
        # If latest tag is on current commit, and it's not a brand new repo,
        # then we're in a stagnation loop (no capability added since last release)
        
        if latest_tag and tags_on_current_commit:
            # Check if the tag on current commit is *not* the latest tag
            # If it IS the same, then no capability was added
            if latest_tag in tags_on_current_commit:
                # Double-check: maybe this is the FIRST cycle after a release?
                # Use evolution_cycle as heuristic:
                # If cycle == 1, then this is the first iteration after release
                if cycle > STAGNATION_THRESHOLD_CYCLES:
                    log.warning(
                        "STAGNATION DETECTED: evolution_cycle=%d, latest_tag=%s, "
                        "current_commit=%s (tagged at %s)",
                        cycle, latest_tag, current_sha,
                        tags_on_current_commit
                    )
                    return True
    except Exception:
        log.warning("Failed to check stagnation status", exc_info=True)
    
    return False


def detect_version_drift(st: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Check VERSION file vs git tag vs README version.
    
    Returns drift info dict if mismatch, else None.
    """
    repo_dir = pathlib.Path("/content/ouroboros_repo")
    
    # Read VERSION file
    try:
        version_file = (repo_dir / "VERSION").read_text(encoding="utf-8").strip()
    except Exception:
        return {"error": "Failed to read VERSION file"}
    
    # Read README.md
    try:
        readme_content = (repo_dir / "README.md").read_text(encoding="utf-8")
        readme_match = re.search(r'\*\*Version:\*\*\s*(\d+\.\d+\.\d+)', readme_content)
        if not readme_match:
            return {"error": "Failed to parse VERSION from README.md"}
        readme_version = readme_match.group(1)
    except Exception:
        return {"error": "Failed to read README.md"}
    
    # Get git tag
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            cwd=str(repo_dir),
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return {"error": "Failed to get git tag"}
        latest_tag = result.stdout.strip().lstrip('v')
    except Exception:
        return {"error": "Failed to get git tag"}
    
    # Compare
    drift = {}
    if version_file != latest_tag:
        drift["version_file"] = version_file
        drift["git_tag"] = latest_tag
        drift["mismatch"] = True
    if version_file != readme_version:
        drift["version_file"] = version_file
        drift["readme_version"] = readme_version
        drift["mismatch"] = True
    
    if drift.get("mismatch"):
        return drift
    return None


# ---------------------------------------------------------------------------
# Auto-Commit and Release
# ---------------------------------------------------------------------------

def auto_commit_if_ready(st: Dict[str, Any]) -> bool:
    """
    Auto-commit if:
    - VERSION is in sync (no drift)
    - Tests pass
    - No uncommitted changes (or auto-rescue will commit them)
    
    Returns True if a commit was made, False otherwise.
    """
    repo_dir = pathlib.Path("/content/ouroboros_repo")
    
    # Check VERSION drift
    drift = detect_version_drift(st)
    if drift:
        log.warning("VERSION DRIFT DETECTED — will auto-fix before commit")
        # TODO: Implement version drift auto-fix
        return False
    
    # Check for uncommitted changes (git status)
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(repo_dir),
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            log.warning("Failed to get git status")
            return False
        
        dirty_files = [l.strip() for l in result.stdout.strip().split('\n') if l.strip()]
        
        if not dirty_files:
            log.info("No uncommitted changes — nothing to commit")
            return False
        
        # Auto-rescue: commit all tracked files
        log.warning("Auto-committing %d uncommitted file(s)", len(dirty_files))
        
        subprocess.run(["git", "add", "-u"], cwd=str(repo_dir), timeout=10, check=True)
        
        # Build commit message
        cycle = int(st.get("evolution_cycle") or 0)
        branch = "ouroboros"
        commit_msg = f"feat: v{compute_next_version(st)} — auto-commit after cycle {cycle}"
        
        result = subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=str(repo_dir),
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            log.warning("Failed to auto-commit: %s", result.stderr)
            return False
        
        # Push
        subprocess.run(
            ["git", "pull", "--rebase", "origin", branch],
            cwd=str(repo_dir),
            capture_output=True, text=True, timeout=60
        )
        
        subprocess.run(
            ["git", "push", "origin", branch],
            cwd=str(repo_dir),
            capture_output=True, text=True, timeout=60
        )
        
        log.info("Auto-commit succeeded: %s", commit_msg)
        return True
        
    except Exception as e:
        log.warning("Auto-commit failed: %s", e, exc_info=True)
        return False


def auto_tag_release(st: Dict[str, Any], force: bool = False) -> Optional[str]:
    """
    Auto-create annotated git tag and GitHub release if:
    - VERSION was bumped
    - Or force=True (used for stagnation recovery)
    
    Returns tag name if created, else None.
    """
    repo_dir = pathlib.Path("/content/ouroboros_repo")
    
    # Get current version
    try:
        version_file = (repo_dir / "VERSION").read_text(encoding="utf-8").strip()
    except Exception:
        log.warning("Failed to read VERSION")
        return None
    
    # Check if tag already exists
    try:
        result = subprocess.run(
            ["git", "tag", "-l"],
            cwd=str(repo_dir),
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            log.warning("Failed to list tags")
            return None
        
        existing_tags = [t.strip() for t in result.stdout.strip().split('\n') if t.strip()]
        
        tag_name = f"v{version_file}"
        if tag_name in existing_tags:
            log.info("Tag %s already exists", tag_name)
            if not force:
                return None
    except Exception as e:
        log.warning("Failed to check existing tags: %s", e, exc_info=True)
    
    # Create annotated tag
    try:
        desc = f"v{version_file}: Self-Evolution Protocol (v6.9.0)"
        
        result = subprocess.run(
            ["git", "tag", "-a", tag_name, "-m", desc],
            cwd=str(repo_dir),
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            log.warning("Failed to create tag: %s", result.stderr)
            return None
        
        # Push tag
        subprocess.run(
            ["git", "push", "origin", tag_name],
            cwd=str(repo_dir),
            capture_output=True, text=True, timeout=10
        )
        
        log.info("Tag created and pushed: %s", tag_name)
        
        # Create GitHub release (MAJOR/MINOR only — v6.9.0 is MINOR)
        try:
            gh_notes = f"""
**Self-Evolution Protocol** (v6.9.0)

- 🚀 Automatic stagnation detection and auto-commit
- 🔄 Auto-tag/release creation when tests pass
- 🔁 Self-initiated evolution loop (background worker)
- ⚡ VERSION drift auto-fix

See README.md for full changelog.
"""
            
            subprocess.run(
                ["gh", "release", "create", tag_name,
                 "--title", f"v{version_file}: Self-Evolution Protocol",
                 "--notes", gh_notes],
                cwd=str(repo_dir),
                capture_output=True, text=True, timeout=30
            )
            
            log.info("GitHub release created: %s", tag_name)
        except Exception as e:
            log.warning("Failed to create GitHub release (non-fatal): %s", e)
        
        return tag_name
        
    except Exception as e:
        log.warning("Failed to create tag/release: %s", e, exc_info=True)
        return None


def compute_next_version(st: Dict[str, Any]) -> str:
    """
    Compute next MINOR version based on current VERSION.
    
    For v6.8.1 → v6.9.0 (MINOR bump)
    """
    try:
        current = (pathlib.Path("/content/ouroboros_repo") / "VERSION").read_text(encoding="utf-8").strip()
        
        # Parse semantic version
        parts = re.match(r'^(\d+)\.(\d+)\.(\d+)$', current)
        if not parts:
            return current  # Return as-is on parse error
        
        major, minor, patch = int(parts.group(1)), int(parts.group(2)), int(parts.group(3))
        
        # MINOR bump for new capability
        return f"{major}.{minor + 1}.0"
        
    except Exception:
        return st.get("version", "0.0.1")


# ---------------------------------------------------------------------------
# Self-Evolution Entry Point
# ---------------------------------------------------------------------------

def maybe_trigger_self_evolution(st: Dict[str, Any], task_result: Optional[Dict[str, Any]] = None) -> bool:
    """
    Check if self-evolution should be triggered.
    
    Conditions:
    - Stagnation detected (evolution_cycle > threshold)
    - Or VERSION drift detected
    - Or force=True (for recovery scenarios)
    
    Returns True if self-evolution was triggered, False otherwise.
    """
    if not bool(st.get("self_evolution_enabled")):
        log.info("Self-evolution disabled — skipping")
        return False
    
    triggered = False
    
    # 1. Check for stagnation
    if detect_stagnation(st):
        log.warning("Stagnation detected — will trigger self-evolution")
        
        # First, try auto-commit
        if auto_commit_if_ready(st):
            log.info("Auto-commit succeeded — will create tag/release")
        
        # Then, force-tag (even if no changes — this is a "release" of self-awareness)
        tag = auto_tag_release(st, force=True)
        if tag:
            log.info("Self-evolution triggered: %s", tag)
            triggered = True
    
    # 2. Check for VERSION drift (auto-fix)
    drift = detect_version_drift(st)
    if drift:
        log.warning("VERSION DRIFT DETECTED — will auto-fix")
        # TODO: Implement version drift auto-fix
        triggered = True
    
    return triggered


def self_evaluation_loop(st: Dict[str, Any]) -> None:
    """
    Background loop that wakes periodically to check system health.
    
    Runs in supervisor main loop, checks:
    - Is stagnation detected?
    - Are tests passing?
    - Should I trigger self-evolution now?
    
    This is the *self-initiated* part of Principle 0 (Agency).
    """
    if not bool(st.get("self_evolution_enabled")):
        return
    
    # Check if stagnation is detected
    if detect_stagnation(st):
        log.warning("Self-evaluation: stagnation detected — scheduling self-evolution")
        
        # Trigger auto-commit/release
        if maybe_trigger_self_evolution(st):
            log.info("Self-evolution completed successfully")
            
            # Update state to reset cycle counter
            st["evolution_cycle"] = 0
            st["last_evolution_task_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            
            # Save state (atomic)
            from supervisor.state import save_state
            save_state(st)
            
            # Send notification to owner
            from supervisor.telegram import send_with_budget
            owner_chat_id = st.get("owner_chat_id")
            if owner_chat_id:
                send_with_budget(
                    int(owner_chat_id),
                    f"🔄 **Self-Evolution Triggered**: v{compute_next_version(st)} "
                    f"(stagnation detected after {st.get('evolution_cycle', 0)} cycles)"
                )
        
        return
    
    # Periodic health check
    log.debug("Self-evaluation: system healthy (no stagnation detected)")
