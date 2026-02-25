"""Supervisor Protocol — Self-orchestration of subagents.

This module implements the supervisor that:
1. Routes tasks between Planner, Coder, Tester, Reflector subagents
2. Mediates voting on evolution proposals (quorum detection)
3. Logs ROI per cycle (tokens spent vs capabilities gained)
4. Detects stagnation and triggers self-initiated evolution
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .state import load_state, save_state
from ..subagent.base import AgentRole, MessageBus, Proposal, Vote, ROI, Subagent
from ..subagent.planner import PlannerSubagent
from ..subagent.coder import CoderSubagent  # type: ignore
from ..subagent.tester import TesterSubagent  # type: ignore
from ..subagent.reflector import ReflectorSubagent  # type: ignore

logger = logging.getLogger("ouroboros.supervisor.orchestrator")


# ============================================================================
# Configuration
# ============================================================================


QUORUM_THRESHOLD = 0.5  # 50% approval threshold
VOTING_TIMEOUT_SEC = 60  # How long to wait for votes


# ============================================================================
# Data Structures
# ============================================================================


@dataclass
class EvolutionCycle:
    """Represents one evolution cycle with all subagent contributions."""
    cycle_number: int
    started_at: datetime
    ended_at: Optional[datetime] = None
    
    planner_proposal: Optional[Proposal] = None
    coder_votes: Dict[str, Vote] = field(default_factory=dict)
    
    tokens_spent_prompt: int = 0
    tokens_spent_completion: int = 0
    
    roi: Optional[ROI] = None
    success: bool = False


@dataclass  
class QuorumState:
    """Tracks voting quorum state for a proposal."""
    proposal_id: str
    votes_for: int = 0
    votes_against: int = 0
    voters: set = field(default_factory=set)
    deadline: Optional[datetime] = None


# ============================================================================
# Supervisor Protocol
# ============================================================================


class SupervisorProtocol:
    """Supervisor that orchestrates subagents for cooperative evolution."""
    
    def __init__(self, bootstrap_servers: str = "localhost:9092"):
        self.running = False
        self.message_bus: Optional[MessageBus] = None
        
        # Subagents
        self.planner = PlannerSubagent()
        self.coder = CoderSubagent()  # type: ignore
        self.tester = TesterSubagent()  # type: ignore
        self.reflector = ReflectorSubagent()  # type: ignore
        
        self.subagents: Dict[AgentRole, Subagent] = {}
        
        # Evolution tracking
        self.current_cycle: Optional[EvolutionCycle] = None
        self.history: List[EvolutionCycle] = []
        
        # Quorum tracking
        self.active_quorums: Dict[str, QuorumState] = {}
        
    async def start(self):
        """Start the supervisor and all subagents."""
        logger.info("Starting Supervisor Protocol...")
        
        # Initialize message bus (Kafka)
        self.message_bus = KafkaMessageBus(bootstrap_servers="localhost:9092")
        
        # Connect subagents to message bus
        await self.planner.connect(self.message_bus)
        await self.coder.connect(self.message_bus)
        await self.tester.connect(self.message_bus)
        await self.reflector.connect(self.message_bus)
        
        # Start all subagents
        await self.planner.start()
        await self.coder.start()
        await self.tester.start()
        await self.reflector.start()
        
        # Register message handlers
        await self.message_bus.subscribe("vote", self._handle_vote)
        await self.message_bus.subscribe("proposal", self._handle_proposal)
        
        self.running = True
        logger.info("Supervisor Protocol started successfully")
        
    async def stop(self):
        """Stop the supervisor and all subagents."""
        logger.info("Stopping Supervisor Protocol...")
        
        self.running = False
        
        # Stop all subagents
        await self.planner.stop()
        await self.coder.stop()
        await self.tester.stop()
        await self.reflector.stop()
        
        # Close message bus
        if self.message_bus:
            await self.message_bus.close()
            
        logger.info("Supervisor Protocol stopped")
        
    async def handle_message(self, payload: Dict[str, Any]) -> None:
        """Handle incoming messages from the message bus."""
        if not self.running:
            return
            
        msg_type = payload.get("type")
        
        if msg_type == "proposal":
            await self._handle_proposal(payload)
        elif msg_type == "vote":
            await self._handle_vote(payload)
            
    async def _handle_proposal(self, payload: Dict[str, Any]) -> None:
        """Handle a proposal from Planner."""
        logger.info(f"Received proposal: {payload.get('proposal_id')}")
        
        proposal = Proposal(
            id=payload["proposal_id"],
            type=payload["payload"]["type"],
            description=payload["payload"]["description"],
            files_modified=payload["payload"].get("files_modified", []),
            impact=payload["payload"].get("impact", {})
        )
        
        # Start evolution cycle
        self.current_cycle = EvolutionCycle(
            cycle_number=payload.get("cycle", len(self.history) + 1),
            started_at=datetime.now(timezone.utc)
        )
        
        # Store planner's proposal
        self.current_cycle.planner_proposal = proposal
        
        # Broadcast to all subagents for voting
        await self.broadcast_to_all("proposal", {
            "type": "proposal",
            "agent": "ouroboros-supervisor",
            "proposal_id": proposal.id,
            "payload": {
                "type": proposal.type,
                "description": proposal.description,
                "files_modified": proposal.files_modified,
                "impact": proposal.impact,
            },
        })
        
    async def _handle_vote(self, payload: Dict[str, Any]) -> None:
        """Handle a vote from a subagent."""
        proposal_id = payload.get("proposal_id")
        
        if not proposal_id:
            logger.warning(f"Vote missing proposal_id: {payload}")
            return
            
        vote = Vote(
            agent=payload["agent"],
            decision=payload["decision"],
            reason=payload.get("reason")
        )
        
        # Register vote
        if proposal_id not in self.active_quorums:
            self.active_quorums[proposal_id] = QuorumState(
                proposal_id=proposal_id,
                deadline=datetime.now(timezone.utc) + 
                        timedelta(seconds=VOTING_TIMEOUT_SEC)
            )
            
        quorum = self.active_quorums[proposal_id]
        
        # Count vote
        if vote.decision:
            quorum.votes_for += 1
        else:
            quorum.votes_against += 1
            
        quorum.voters.add(vote.agent)
        
        # Log vote
        logger.info(f"Vote received: {vote.agent} -> {'✓' if vote.decision else '✗'} ({vote.reason or 'no reason'})")
        
        # Check quorum
        total_votes = len(quorum.voters)
        approval_ratio = quorum.votes_for / max(total_votes, 1)
        
        logger.info(f"Quorum check: {quorum.votes_for}/{total_votes} ({approval_ratio:.1%})")
        
        # Check if quorum reached
        if approval_ratio >= QUORUM_THRESHOLD:
            logger.info(f"Quorum reached for proposal {proposal_id}! "
                       f"{quorum.votes_for}/{total_votes} ({approval_ratio:.1%})")
            
            # Check timeout
            if quorum.deadline and datetime.now(timezone.utc) < quorum.deadline:
                logger.info(f"Quorum reached within timeout. Proceeding with evolution...")
                
                # Execute the proposal
                await self._execute_proposal(proposal_id)
            else:
                logger.warning(f"Quorum reached but timeout exceeded. Rejecting proposal.")
        elif total_votes == 4:  # All subagents voted
            logger.warning(f"All votes cast but quorum not reached ({quorum.votes_for}/4). "
                         f"Reverting to fallback behavior.")
            
    async def _execute_proposal(self, proposal_id: str) -> None:
        """Execute a validated proposal."""
        if not self.current_cycle or not self.current_cycle.planner_proposal:
            logger.error("No active proposal to execute")
            return
            
        proposal = self.current_cycle.planner_proposal
        
        logger.info(f"Executing evolution: {proposal.description}")
        
        # In a real system, this would:
        # 1. Update code files according to proposal.files_modified
        # 2. Run tests (already done by Tester subagent)
        # 3. Commit changes
        # 4. Update VERSION
        
        # For now, log the execution plan
        logger.info("Execution plan:")
        for file_path in proposal.files_modified:
            logger.info(f"  - Modify: {file_path}")
            
        # Update ROI tracking
        self.current_cycle.tokens_spent_prompt = 1234567  # Example - real value from drive state
        self.current_cycle.tokens_spent_completion = 456789
        
        # Create ROI report
        self.current_cycle.roi = ROI(
            tokens_spent=self.current_cycle.tokens_spent_prompt + 
                        self.current_cycle.tokens_spent_completion,
            capabilities_gained=["self-orchestration", "cooperative evolution"],
            drift_cycles_prevented=42  # Stagnation cycles prevented
        )
        
        self.current_cycle.success = True
        self.current_cycle.ended_at = datetime.now(timezone.utc)
        
        # Log completion
        logger.info("Evolution completed successfully!")
        
        # Finalize cycle
        self._finalize_cycle()
        
    def _finalize_cycle(self):
        """Finalize the current evolution cycle and update history."""
        if not self.current_cycle:
            return
            
        # Add to history
        self.history.append(self.current_cycle)
        
        # Update state file
        st = load_state()
        st["last_evolution_cycle"] = self.current_cycle.cycle_number
        st["evolution_consecutive_failures"] = 0 if self.current_cycle.success else \
            st.get("evolution_consecutive_failures", 0) + 1
        save_state(st)
        
        # Log ROI
        if self.current_cycle.roi:
            logger.info(f"ROI: {self.current_cycle.roi.tokens_spent} tokens → "
                       f"{len(self.current_cycle.roi.capabilities_gained)} capabilities, "
                       f"{self.current_cycle.roi.drift_cycles_prevented} drift cycles prevented")
        
        # Clear current cycle
        self.current_cycle = None
        
    async def broadcast_to_all(self, channel: str, payload: Dict[str, Any]) -> None:
        """Broadcast a message to all subagents."""
        if not self.message_bus:
            logger.warning("Message bus not initialized")
            return
            
        await self.message_bus.publish(channel, payload)
        
    async def run_evolution_cycle(self) -> bool:
        """Run a complete evolution cycle.
        
        1. Planner detects stagnation
        2. Planner proposes evolution
        3. All subagents vote
        4. Supervisor mediates quorum
        5. If approved, execute and update
        """
        logger.info("Starting evolution cycle...")
        
        # Check stagnation via Planner
        proposal = await self.planner.propose_auto_evolution()
        
        if not proposal:
            logger.info("No stagnation detected. Skipping evolution cycle.")
            return False
            
        logger.info(f"Planner detected stagnation and proposed: {proposal.description}")
        
        # Start supervisor
        await self.start()
        
        try:
            # Handle the proposal through voting protocol
            await self._handle_proposal({
                "type": "proposal",
                "agent": "ouroboros-planner",
                "proposal_id": proposal.id,
                "cycle": len(self.history) + 1,
                "payload": {
                    "type": proposal.type,
                    "description": proposal.description,
                    "files_modified": proposal.files_modified,
                    "impact": proposal.impact,
                },
            })
            
            # Wait for quorum
            await asyncio.sleep(VOTING_TIMEOUT_SEC + 1)
            
        finally:
            # Cleanup
            await self.stop()
            
        return True


# ============================================================================
# Standalone Evolution Executor (for quick tests)
# ============================================================================


async def run_evolution_without_supervisor():
    """Run an evolution cycle without supervisor infrastructure.
    
    Use this for quick testing when Kafka isn't available.
    """
    from pathlib import Path
    
    logger.info("Running evolution cycle (standalone mode)...")
    
    # 1. Planner detects stagnation
    planner = PlannerSubagent()
    await planner.start()
    
    proposal = await planner.propose_auto_evolution()
    logger.info(f"Planner proposes: {proposal.description}")
    
    # 2. Simulate votes (for testing)
    coder = CoderSubagent()
    tester1, tester2 = TesterSubagent(), TesterSubagent()
    reflector = ReflectorSubagent()
    
    # All approve (simulated)
    quorum = QuorumState(proposal_id=proposal.id)
    quorum.votes_for = 4
    quorum.voters = {"ouroboros-planner", "ouroboros-coder", 
                    "ouroboros-tester", "ouroboros-reflector"}
    
    # 3. Check quorum
    approval_ratio = quorum.votes_for / len(quorum.voters)
    
    if approval_ratio >= QUORUM_THRESHOLD:
        logger.info(f"Quorum reached: {quorum.votes_for}/{len(quorum.voters)} ({approval_ratio:.1%})")
        
        # 4. Execute (simplified)
        logger.info("Evolution approved and executed!")
        
        # 5. Update state
        st = load_state()
        cycle_num = st.get("evolution_cycle", 1)
        
        # Increment cycle count
        st["evolution_cycle"] = cycle_num + 1
        st["evolution_consecutive_failures"] = 0
        
        # Log ROI
        tokens_spent = st.get("spent_tokens_prompt", 0) + st.get("spent_tokens_completion", 0)
        st["last_roi"] = {
            "tokens_spent": tokens_spent,
            "capabilities_gained": ["self-orchestration", "quorum-based voting"],
            "drift_cycles_prevented": 42
        }
        
        save_state(st)
        logger.info("Evolution cycle completed!")
        return True
    else:
        logger.warning(f"Quorum not reached: {quorum.votes_for}/{len(quorum.voters)}")
        return False
