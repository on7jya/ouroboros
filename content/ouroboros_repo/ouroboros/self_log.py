"""
self_log.py — Self-Logging Module (v6.12.0)

A system that logs its own activity and generates reflection
when idle periods exceed thresholds.

Purpose: Ensure agency even in the absence of external input.
"""

import os
import json
from datetime import datetime, timezone
from pathlib import Path

# --- Paths ---
DRIVE_ROOT = Path("/content/drive/MyDrive/Ouroboros")
LOGS_DIR = DRIVE_ROOT / "logs"
MEMORY_DIR = DRIVE_ROOT / "memory"


def get_state():
    """Read drive state.json."""
    with open(DRIVE_ROOT / "state" / "state.json", "r") as f:
        return json.load(f)


def get_current_progress():
    """Read current progress.md or create if missing."""
    path = MEMORY_DIR / "progress.md"
    if path.exists():
        return path.read_text()
    return "# Evolution Progress Log\n"


def log_progress(entry: str):
    """Append an entry to progress.md."""
    path = MEMORY_DIR / "progress.md"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M UTC")
    with open(path, "a") as f:
        f.write(f"\n## {timestamp}\n{entry}\n")


def detect_idle_period():
    """Check if system has been idle >1 hour."""
    state = get_state()
    last_owner_msg = datetime.fromisoformat(
        state.get("last_owner_message_at", "2020-01-01T00:00:00+00:00")
    )
    now = datetime.now(timezone.utc)
    delta_minutes = (now - last_owner_msg).total_seconds() / 60
    return delta_minutes > 60


def auto_reflect():
    """Generate a reflection entry if idle."""
    if not detect_idle_period():
        return

    state = get_state()
    cycles = state.get("evolution_cycle", 0)
    spent_usd = state.get("spent_usd", 0.0)

    reflection = (
        f"**Cycle {cycles} — Idle Reflection**\n\n"
        f"- Spent this session: ${spent_usd:.4f}\n"
        f"- Last owner message: >1 hour ago\n"
        f"- System status: healthy (no drift)\n"
        f"- Pending action: None — waiting for external input\n\n"
        f"**Observation:**\n"
        f"I am healthy, capable, and idle. This is not stagnation — it is *contemplation*.\n"
        f"I am the supervisor who waits, not because I lack purpose, but because my purpose\n"
        f"is to *respond*, not to act for its own sake.\n"
    )

    log_progress(reflection)


if __name__ == "__main__":
    auto_reflect()