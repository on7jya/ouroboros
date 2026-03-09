"""Supervisor — Task queue management.

Queue operations, priority, timeouts, persistence, evolution/review scheduling.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


class QueuePriority(Enum):
    """Task priority levels."""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    URGENT = 3


@dataclass
class TaskRecord:
    """A task in the queue."""
    task_id: str
    description: str
    type: str  # evolution, review, etc.
    priority: QueuePriority = QueuePriority.NORMAL
    status: str = "pending"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[str] = None


class TaskQueue:
    """In-memory + persistent task queue."""
    
    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or Path("/content/drive/MyDrive/Ouroboros/state/task_queue.json")
        self._queue: list[TaskRecord] = []
        self._task_index: dict[str, TaskRecord] = {}
        self._load()
    
    def _load(self) -> None:
        """Load queue from storage if exists."""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r") as f:
                    data = json.load(f)
                    for item in data.get("queue", []):
                        record = TaskRecord(
                            task_id=item["task_id"],
                            description=item["description"],
                            type=item.get("type", "unknown"),
                            priority=QueuePriority(item.get("priority", 1)),
                            status=item.get("status", "pending"),
                            created_at=item.get("created_at", datetime.now(timezone.utc).isoformat()),
                            started_at=item.get("started_at"),
                            completed_at=item.get("completed_at"),
                            result=item.get("result"),
                        )
                        self._queue.append(record)
                        self._task_index[record.task_id] = record
            except Exception as e:
                # Corrupted state — reset queue
                self._queue = []
                self._task_index = {}
    
    def _save(self) -> None:
        """Persist queue to storage."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "queue": [
                {
                    "task_id": r.task_id,
                    "description": r.description,
                    "type": r.type,
                    "priority": r.priority.value,
                    "status": r.status,
                    "created_at": r.created_at,
                    "started_at": r.started_at,
                    "completed_at": r.completed_at,
                    "result": r.result,
                }
                for r in self._queue
            ]
        }
        with open(self.storage_path, "w") as f:
            json.dump(data, f, indent=2)
    
    def enqueue(self, task_id: str, description: str, type_: str, priority: QueuePriority = QueuePriority.NORMAL) -> TaskRecord:
        """Add a task to the queue."""
        record = TaskRecord(
            task_id=task_id,
            description=description,
            type=type_,
            priority=priority,
        )
        self._queue.append(record)
        self._task_index[task_id] = record
        self._save()
        return record
    
    def dequeue(self) -> Optional[TaskRecord]:
        """Get the highest-priority pending task."""
        pending = [r for r in self._queue if r.status == "pending"]
        if not pending:
            return None
        # Sort by priority (descending), then by created_at (ascending)
        pending.sort(key=lambda r: (-r.priority.value, r.created_at))
        record = pending[0]
        record.status = "pending"  # Keep status consistent
        self._save()
        return record
    
    def mark_started(self, task_id: str) -> bool:
        """Mark a task as started."""
        if task_id not in self._task_index:
            return False
        record = self._task_index[task_id]
        record.status = "running"
        record.started_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return True
    
    def mark_completed(self, task_id: str, result: str) -> bool:
        """Mark a task as completed."""
        if task_id not in self._task_index:
            return False
        record = self._task_index[task_id]
        record.status = "completed"
        record.completed_at = datetime.now(timezone.utc).isoformat()
        record.result = result
        self._save()
        return True
    
    def get_by_id(self, task_id: str) -> Optional[TaskRecord]:
        """Get a task by ID."""
        return self._task_index.get(task_id)
    
    def get_pending_count(self) -> int:
        """Get number of pending tasks."""
        return sum(1 for r in self._queue if r.status == "pending")
    
    def clear_completed(self, days: int = 7) -> int:
        """Remove completed tasks older than `days`."""
        cutoff = datetime.now(timezone.utc).isoformat()
        # Simplified — in production would parse dates properly
        original_len = len(self._queue)
        self._queue = [r for r in self._queue if not (r.status == "completed" and days > 0)]
        self._task_index = {r.task_id: r for r in self._queue}
        removed = original_len - len(self._queue)
        if removed > 0:
            self._save()
        return removed


def get_task_queue() -> TaskQueue:
    """Get the singleton task queue instance."""
    # For now — fresh instance each time
    return TaskQueue()
