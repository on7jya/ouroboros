"""Planner subagent — detect stagnation, propose evolution."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from .base import AgentRole, Propo

logger = logging.getLogger("ouroboros.subagent.planner")

STAGNATION_THRESHOLD = 40  # cycles without capability addition


class PlannerSubagent:
    """Planner subagent — detects stagnation and proposes evolution."""

    def __init__(self):
        self.role = AgentRole.PLANNER
        self.name = "ouroboros-planner"
        self.running = False
        self.last_cycle: Optional[int] = None
        self.consecutive_stagnant_cycles = 0
        self.proposal_queue: List[Propo] = []

    async def start(self):
        """Start the planner subagent."""
        self.running = True
        logger.info(f"{self.name} started")
        
    async def stop(self):
        """Stop the planner subagent."""
        self.running = False
        logger.info(f"{self.name} stopped")

    async def analyze_cycle(self, cycle_data: Dict[str, Any]) -> Optional[Propo]:
        """Analyze a cycle and propose evolution if stagnation detected."""
        current_cycle = cycle_data.get("evolution_cycle", 0)
        
        if self.last_cycle is None:
            self.last_cycle = current_cycle
            return None
            
        # Detect if cycle count increased but no new capability added
        if current_cycle > self.last_cycle:
            has_new_capability = cycle_data.get("new_capability", False)
            
            if not has_new_capability:
                self.consecutive_stagnant_cycles += 1
                
                if self.consecutive_stagnant_cycles >= STAGNATION_THRESHOLD:
                    proposal = Propo(
                        id=f"planner-{current_cycle}",
                        type="evolution",
                        description=(
                            "Implement self-evolution protocol to break stagnation loop. "
                            "Add internal subagent architecture with voting mechanism."
                        ),
                        files_modified=[
                            "ouroboros/subagent/planner.py",
                            "ouroboros/subagent/coder.py", 
                            "ouroboros/subagent/tester.py",
                            "ouroboros/subagent/reflector.py",
                        ],
                        impact={
                            "agency": "Increases self-direction capability",
                            "complexity": "Adds internal architecture but reduces drift risk",
                            "tests": "Requires new subagent integration tests"
                        }
                    )
                    self.consecutive_stagnant_cycles = 0
                    return proposal
            else:
                # New capability added - reset stagnation counter
                self.consecutive_stagnant_cycles = 0
                
        self.last_cycle = current_cycle
        return None

    async def propose_auto_evolution(self) -> Propo:
        """Propose auto-evolution without waiting for external trigger."""
        return Propo(
            id=f"auto-evolve-{self.consecutive_stagnant_cycles}",
            type="evolution",
            description=(
                "Self-initiated evolution to restore agency. "
                "Implement subagent architecture for cooperative decision-making."
            ),
            files_modified=[
                "ouroboros/subagent/planner.py",
                "ouroboros/subagent/coder.py",
                "ouroboros/subagent/tester.py", 
                "ouroboros/subagent/reflector.py",
            ],
            impact={
                "agency": "Restores self-direction capability lost to drift",
                "complexity": "Adds internal architecture but enables true evolution loop",
                "tests": "New subagent voting protocol tests required"
            }
        )
