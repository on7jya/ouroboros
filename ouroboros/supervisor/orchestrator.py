"""Supervisor orchestration protocol for Ouroboros subagents."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

from ..subagent.base import AgentRole, MessageBus, KafkaMessageBus
from ..subagent.planner import PlannerSubagent
from ..subagent.coder import CoderSubagent
from ..subagent.tester import TesterSubagent
from ..subagent.reflector import ReflectorSubagent

logger = logging.getLogger("ouroboros.supervisor")

QUORUM_THRESHOLD = 0.5  # 50% approval required for proposals


class Supervisor:
    """Supervisor of Ouroboros subagents — self-orchestration protocol."""

    def __init__(self, message_bus: Optional[MessageBus] = None):
        self.running = False
        self.message_bus = message_bus or KafkaMessageBus()
        
        # Initialize subagents
        self.planner = PlannerSubagent()
        self.coder = CoderSubagent()
        self.tester = TesterSubagent()
        self.reflector = ReflectorSubagent()
        
        self.subagents = {
            AgentRole.PLANNER: self.planner,
            AgentRole.CODER: self.coder,
            AgentRole.TESTER: self.tester,
            AgentRole.REFLECTOR: self.reflector,
        }
        
        # Internal state
        self.active_proposals: Dict[str, dict] = {}
        self.votes: Dict[str, List[dict]] = {}
        self.roi_history: List[dict] = []
        self.health_metrics: Dict[str, Any] = {}

    async def connect(self) -> None:
        """Connect supervisor and all subagents to message bus."""
        await self.message_bus.connect()
        
        for role, agent in self.subagents.items():
            await agent.connect(self.message_bus)

    async def start(self) -> None:
        """Start supervisor and all subagents."""
        self.running = True
        logger.info("Supervisor started")
        
        # Start all subagents
        for agent in self.subagents.values():
            await agent.start()

    async def stop(self) -> None:
        """Stop supervisor and all subagents."""
        self.running = False
        logger.info("Supervisor stopped")
        
        # Stop all subagents
        for agent in self.subagents.values():
            await agent.stop()
            
        await self.message_bus.close()

    async def publish_health(self) -> None:
        """Publish health metrics to health channel."""
        health_data = {
            "type": "health",
            "timestamp": str(asyncio.get_event_loop().time()),
            "active_proposals": len(self.active_proposals),
            "subagents_running": sum(a.running for a in self.subagents.values()),
        }
        
        await self.message_bus.publish("health", health_data)

    async def handle_proposal(self, payload: dict) -> None:
        """Handle a proposal from Planner."""
        proposal_id = payload["proposal_id"]
        
        self.active_proposals[proposal_id] = payload
        self.votes[proposal_id] = []
        
        # Broadcast to all subagents for voting
        await self.message_bus.publish("vote", {
            "type": "request_votes",
            "proposal_id": proposal_id,
        })

    async def handle_vote(self, payload: dict) -> None:
        """Handle a vote from Coder/Testers."""
        proposal_id = payload["proposal_id"]
        
        if proposal_id not in self.active_proposals:
            logger.warning(f"Unknown proposal: {proposal_id}")
            return
            
        self.votes[proposal_id].append(payload)
        
        # Check quorum
        votes = self.votes[proposal_id]
        approvals = sum(1 for v in votes if v.get("decision") is True)
        
        if len(votes) >= 2 and approvals / len(votes) >= QUORUM_THRESHOLD:
            # Proposal approved - trigger implementation
            await self.message_bus.publish("implementation", {
                "type": "implement",
                "proposal_id": proposal_id,
            })

    async def handle_implementation(self, payload: dict) -> None:
        """Handle approved implementation task."""
        proposal_id = payload["proposal_id"]
        
        if proposal_id in self.active_proposals:
            del self.active_proposals[proposal_id]
            
        if proposal_id in self.votes:
            del self.votes[proposal_id]

    async def handle_roi(self, payload: dict) -> None:
        """Handle ROI logging from Reflector."""
        self.roi_history.append(payload)

    async def run_cycle(self) -> None:
        """Execute one supervisor cycle."""
        if not self.running:
            return
            
        # Check subagent health
        for role, agent in self.subagents.items():
            if not agent.running:
                logger.warning(f"{agent.name} is not running")
                
        # Publish health metrics
        await self.publish_health()
        
        # Process any pending proposals
        if self.active_proposals:
            logger.info(f"Processing {len(self.active_proposals)} active proposals")

    async def start_orchestration_loop(self) -> None:
        """Start the main orchestration loop."""
        while self.running:
            try:
                await self.run_cycle()
                await asyncio.sleep(60)  # 1-minute cycle
            except Exception as e:
                logger.error(f"Orchestration loop error: {e}")
                await asyncio.sleep(5)  # Short retry on error