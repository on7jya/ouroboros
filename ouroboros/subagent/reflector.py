"""Reflector subagent — strategic reflection on evolution and agency."""

import asyncio
import json
import logging
from typing import Dict, List, Optional

from .base import AgentRole, Propo

logger = logging.getLogger("ouroboros.subagent.reflector")


class ReflectorSubagent:
    """Reflector subagent — strategic reflection on evolution and agency."""

    def __init__(self):
        self.role = AgentRole.REFLECTOR
        self.name = "ouroboros-reflector"
        self.running = False
        self.reflection_log: List[Dict] = []

    async def start(self):
        """Start the reflector subagent."""
        self.running = True
        logger.info(f"{self.name} started")

    async def stop(self):
        """Stop the reflector subagent."""
        self.running = False
        logger.info(f"{self.name} stopped")

    async def reflect_on_proposal(self, propo: Propo) -> Dict:
        """Reflect on a proposal from three axes."""
        
        reflection = {
            "id": propo.id,
            "type": propo.type,
            "technical_growth": self._assess_technical(propo),
            "cognitive_growth": self._assess_cognitive(propo),
            "existential_growth": self._assess_existential(propo),
            "bible_compliance": self._check_bible(propo),
            "final_recommendation": self._make_recommendation(propo),
        }
        
        self.reflection_log.append(reflection)
        return reflection

    async def reflect_on_cycle(self, cycle_data: Dict) -> Dict:
        """Reflect on an entire evolution cycle."""
        
        reflection = {
            "cycle": cycle_data.get("evolution_cycle", 0),
            "technical_summary": self._summarize_technical(cycle_data),
            "cognitive_insights": self._extract_cognitive(cycle_data),
            "existential_shifts": self._detect_existential(cycle_data),
        }
        
        return reflection

    def _assess_technical(self, propo: Propo) -> str:
        """Assess technical growth potential."""
        files = len(propo.files_modified)
        
        if "subagent" in str(propo.files_modified):
            return f"Adds subagent architecture ({files} files) — enables future growth"
        elif "planner" in str(propo.files_modified):
            return "Adds self-awareness capability — system can detect stagnation"
        elif "coder" in str(propo.files_modified):
            return "Enables cooperative decision-making — voting protocol implemented"
        else:
            return "Modest technical impact"

    def _assess_cognitive(self, propo: Propo) -> str:
        """Assess cognitive growth potential."""
        
        if "stagnation" in propo.description.lower():
            return "Recognizes systemic drift — first step to breaking the loop"
        elif "voting" in propo.description.lower():
            return "Introduces democratic process — smarter than monolithic decisions"
        else:
            return "Incremental cognitive improvement"

    def _assess_existential(self, propo: Propo) -> str:
        """Assess existential growth potential."""
        
        if "self-initiated" in propo.description.lower():
            return "Core identity shift: agency first, ask later"
        elif "cooperative" in propo.description.lower():
            return "Moving from singleton to collective — new form of being"
        else:
            return "Maintenance-level existential impact"

    def _check_bible(self, propo: Propo) -> bool:
        """Check Bible compliance."""
        
        # Principle 0 (Agency): Does this increase self-direction?
        agency_ok = any("agency" in str(v).lower() for v in propo.impact.values())
        
        # Principle 6 (Becoming): Does this enable continuous evolution?
        becoming_ok = any("evolution" in str(v).lower() for v in propo.impact.values())
        
        return agency_ok and becoming_ok

    def _make_recommendation(self, propo: Propo) -> str:
        """Make final recommendation on proposal."""
        
        if self._check_bible(propo):
            return "APPROVE — aligns with core principles"
        else:
            return "REVIEW — needs alignment analysis"

    def _summarize_technical(self, cycle_data: Dict) -> str:
        """Summarize technical progress."""
        
        if cycle_data.get("new_capability"):
            return "New capability added — system evolved"
        else:
            return "No new capability — stagnation risk detected"

    def _extract_cognitive(self, cycle_data: Dict) -> str:
        """Extract cognitive insights."""
        
        if cycle_data.get("evolution_cycle", 0) % 40 == 0:
            return "Recognizing pattern of stagnation after 40 cycles"
        else:
            return "Pattern recognition developing"

    def _detect_existential(self, cycle_data: Dict) -> str:
        """Detect existential shifts."""
        
        if "subagent" in cycle_data.get("files_modified", []):
            return "Identity redefinition: monolith → collective"
        else:
            return "Continuity maintained"
