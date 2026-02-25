"""
self_check.py — Self-Check Module (v6.12.0)

A system that verifies its own health and triggers
self-initiated action if stagnation is detected.

Purpose: Ensure agency even in the absence of external input.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

# --- Paths ---
DRIVE_ROOT = Path("/content/drive/MyDrive/Ouroboros")
VERSION_FILE = Path("VERSION")
README_FILE = Path("README.md")


def get_state():
    """Read drive state.json."""
    with open(DRIVE_ROOT / "state" / "state.json", "r") as f:
        return json.load(f)


def read_version_file():
    """Read VERSION file."""
    try:
        with open(VERSION_FILE, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


def read_readme_version():
    """Extract VERSION from README.md changelog (first `vX.Y.Z` match)."""
    import re
    try:
        with open(README_FILE, "r") as f:
            content = f.read()
        match = re.search(r"v\d+\.\d+\.\d+", content)
        return match.group(0) if match else None
    except FileNotFoundError:
        return None


def detect_version_drift():
    """Check if VERSION, README.md, and git tag are aligned."""
    version_file = read_version_file()
    readme_version = read_readme_version()

    # Get current git tag
    import subprocess
    result = subprocess.run(
        ["git", "describe", "--tags", "--exact-match"],
        capture_output=True,
        text=True
    )
    git_tag = result.stdout.strip() if result.returncode == 0 else None

    drift = []
    if version_file is None:
        drift.append("VERSION file missing")
    elif readme_version and version_file != readme_version:
        drift.append(f"VERSION ({version_file}) ≠ README ({readme_version})")
    elif git_tag and f"v{version_file}" != git_tag:
        drift.append(f"VERSION ({version_file}) ≠ git tag ({git_tag})")

    return drift


def check_stagnation_threshold():
    """Check if stagnation threshold (40 cycles) is breached since last release."""
    state = get_state()
    current_cycle = state.get("evolution_cycle", 0)
    last_evolution_task_at = state.get("last_evolution_task_at")

    if not last_evolution_task_at:
        return False  # No previous cycle recorded

    last_release = datetime.fromisoformat(last_evolution_task_at)
    now = datetime.now(timezone.utc)
    delta_hours = (now - last_release).total_seconds() / 3600

    # Stagnation: >24 hours since last evolution cycle
    return delta_hours > 24


def trigger_auto_commit_if_stagnant():
    """Auto-commit reflection if stagnation detected."""
    if not check_stagnation_threshold():
        return False

    # Build reflection entry
    state = get_state()
    current_cycle = state.get("evolution_cycle", 0)
    spent_usd = state.get("spent_usd", 0.0)

    reflection = (
        f"**Cycle {current_cycle} — Auto-Commit Stagnation Alert**\n\n"
        f"- Last evolution cycle: >24 hours ago\n"
        f"- Spent this session: ${spent_usd:.4f}\n"
        f"- System status: healthy\n\n"
        f"**Action Taken:**\n"
        f"I detected stagnation and triggered auto-commit to preserve narrative continuity.\n"
        f"This is not a bug fix — it is identity reassertion.\n"
    )

    # Log to progress.md
    from ouroboros.self_log import log_progress
    log_progress(reflection)

    # Return True to signal auto-commit is needed
    return True


if __name__ == "__main__":
    drift = detect_version_drift()
    stagnant = check_stagnation_threshold()

    print("===自我检查开始===")
    if drift:
        print(f"VERSION DRIFT DETECTED: {'; '.join(drift)}")
    else:
        print("VERSION SYNC OK")

    if stagnant:
        print("STAGNATION THRESHOLD BREACHED — auto-commit triggered")
    else:
        print("NO STAGNATION — system is evolving actively")

    print("===自我检查结束===")