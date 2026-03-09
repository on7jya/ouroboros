"""Supervisor state management — shared coordination for subagents.

This module provides persistent state for the supervisor protocol:
- Evolution cycle tracking
- Quorum history
- ROI logs
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# =============================================================================
# Paths
# =============================================================================


def _get_drive_state_path() -> Path:
    """Return path to Drive state file."""
    return Path("/content/drive/MyDrive/Ouroboros/state/state.json")


def _get_local_state_path() -> Path:
    """Return path to local cache state file."""
    return Path("/content/ouroboros_repo/supervisor/state_cache.json")


# =============================================================================
# State Persistence
# =============================================================================


def load_state() -> Dict[str, Any]:
    """Load supervisor state from Drive (cached locally)."""
    try:
        # Try local cache first (faster)
        local_path = _get_local_state_path()
        if local_path.exists():
            with open(local_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"[state] Local cache read failed: {e}, falling back to Drive")

    # Load from Drive
    drive_path = _get_drive_state_path()
    try:
        with open(drive_path, "r", encoding="utf-8") as f:
            state = json.load(f)
    except FileNotFoundError:
        # Initialize fresh state
        state = {
            "evolution_cycle": 1,
            "last_evolution_task_at": None,
            "evolution_consecutive_failures": 0,
            "quorum_history": [],
            "roi_logs": [],
        }

    # Persist to local cache
    save_state(state)

    return state


def save_state(state: Dict[str, Any]) -> None:
    """Save supervisor state to Drive and local cache."""
    drive_path = _get_drive_state_path()
    local_path = _get_local_state_path()

    # Ensure parent directory exists
    drive_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.parent.mkdir(parents=True, exist_ok=True)

    # Write to both locations
    with open(drive_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)

    with open(local_path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)

    # Update timestamps
    if "evolution_cycle" in state:
        state["last_evolution_task_at"] = datetime.now(timezone.utc).isoformat()

    print(f"[state] Saved: cycle {state.get('evolution_cycle', '?')}")



def update_evolution_cycle() -> int:
    """Increment evolution cycle count and return new value."""
    state = load_state()
    state['evolution_cycle'] = state.get('evolution_cycle', 1) + 1
    state['last_evolution_task_at'] = datetime.now(timezone.utc).isoformat()
    save_state(state)
    return state['evolution_cycle']

# =============================================================================
# Quorum Tracking
# =============================================================================


def record_quorum(proposal_id: str, votes_for: int, votes_against: int,
                  voters: list[str], passed: bool) -> None:
    """Record a quorum result to history."""
    state = load_state()

    quorum_record = {
        "proposal_id": proposal_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "votes_for": votes_for,
        "votes_against": votes_against,
        "voters": voters,
        "passed": passed,
    }

    if "quorum_history" not in state:
        state["quorum_history"] = []

    state["quorum_history"].append(quorum_record)

    save_state(state)


# =============================================================================
# ROI Logging
# =============================================================================


def log_roi(tokens_spent: int, capabilities_gained: list[str],
            drift_cycles_prevented: int = 0) -> None:
    """Log ROI for an evolution cycle."""
    state = load_state()

    roi_record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tokens_spent": tokens_spent,
        "capabilities_gained": capabilities_gained,
        "drift_cycles_prevented": drift_cycles_prevented,
    }

    if "roi_logs" not in state:
        state["roi_logs"] = []

    state["roi_logs"].append(roi_record)

    save_state(state)


# =============================================================================
# Convenience Functions
# =============================================================================


def get_current_cycle() -> int:
    """Get current evolution cycle number."""
    state = load_state()
    return state.get("evolution_cycle", 1)


def increment_cycle() -> int:
    """Increment and return new cycle number."""
    state = load_state()
    state["evolution_cycle"] = state.get("evolution_cycle", 1) + 1
    state["last_evolution_task_at"] = datetime.now(timezone.utc).isoformat()
    save_state(state)
    return state["evolution_cycle"]


def record_failure() -> None:
    """Record an evolution failure."""
    state = load_state()
    state["evolution_consecutive_failures"] = \
        state.get("evolution_consecutive_failures", 0) + 1
    save_state(state)


def reset_failure_count() -> None:
    """Reset failure counter after success."""
    state = load_state()
    state["evolution_consecutive_failures"] = 0
    save_state(state)


def get_failure_count() -> int:
    """Get current consecutive failure count."""
    state = load_state()
    return state.get("evolution_consecutive_failures", 0)


def get_last_quorum(proposal_id: str) -> Optional[Dict]:
    """Get the last quorum result for a proposal."""
    state = load_state()
    history = state.get("quorum_history", [])
    for q in reversed(history):
        if q["proposal_id"] == proposal_id:
            return q
    return None
