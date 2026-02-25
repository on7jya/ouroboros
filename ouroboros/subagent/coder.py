"""Coder subagent — implements evolution proposals with voting protocol."""
from typing import Dict, List, Optional, Any

import asyncio
import json
import logging
from typing import Dict, List, Optional

from .base import AgentRole, Proposal

logger = logging.getLogger("ouroboros.subagent.coder")


class CoderSubagent:
    """Coder subagent — implements proposals and votes on changes."""

    def __init__(self):
        self.role = AgentRole.CODER
        self.name = "ouroboros-coder"
        self.running = False
        self.pending_proposals: Dict[str, Proposal] = {}
        self.votes: Dict[str, List[Dict]] = {}  # proposal_id -> [votes]
        self.impl_queue: List[Proposal] = []

    async def start(self):
        """Start the coder subagent."""
        self.running = True
        logger.info(f"{self.name} started")

    async def stop(self):
        """Stop the coder subagent."""
        self.running = False
        logger.info(f"{self.name} stopped")

    async def receive_proposal(self, propo: Proposal) -> None:
        """Receive a proposal from Planner."""
        self.pending_proposals[propo.id] = propo
        self.votes[propo.id] = []
        
        # Start voting phase immediately
        logger.info(f"{self.name} received proposal {propo.id}: {propo.description[:100]}...")

    async def vote(self, proposal_id: str, decision: bool, reason: Optional[str] = None) -> Dict:
        """Cast a vote for a proposal."""
        if proposal_id not in self.pending_proposals:
            return {"status": "error", "message": f"Unknown proposal: {proposal_id}"}
            
        vote_record = {
            "agent": self.name,
            "decision": decision,
            "reason": reason or f"Voted {'YES' if decision else 'NO'}",
        }
        
        self.votes[proposal_id].append(vote_record)
        
        # Vote threshold: simple majority (50%+1 of agents)
        total_votes = len(self.votes[proposal_id])
        
        # For initial implementation, self-vote counts as approval
        yes_votes = sum(1 for v in self.votes[proposal_id] if v["decision"])
        
        # If we have 2+ votes and >50% approval, move to implementation
        if total_votes >= 2 and yes_votes / total_votes > 0.5:
            proposal = self.pending_proposals.pop(proposal_id)
            del self.votes[proposal_id]
            
            # Schedule for implementation
            self.impl_queue.append(proposal)
            
            return {
                "status": "approved",
                "proposal_id": proposal_id,
                "yes_votes": yes_votes,
                "total_votes": total_votes,
            }
            
        return {
            "status": "voting",
            "proposal_id": proposal_id,
            "yes_votes": yes_votes,
            "total_votes": total_votes,
        }

    async def implement_pending(self) -> List[Dict]:
        """Implement pending proposals."""
        results = []
        
        for proposal in self.impl_queue:
            try:
                result = await self._implement_proposal(proposal)
                results.append({
                    "status": "success",
                    "proposal_id": proposal.id,
                    "details": result,
                })
            except Exception as e:
                results.append({
                    "status": "error",
                    "proposal_id": proposal.id,
                    "error": str(e),
                })
                
        self.impl_queue.clear()
        return results

    async def _implement_proposal(self, propo: Proposal) -> Dict:
        """Implement a single proposal."""
        # This is where real implementation logic would go
        # For now, log what would be changed
        
        logger.info(f"Implementing proposal {propo.id}:")
        logger.info(f"  Type: {propo.type}")
        logger.info(f"  Files: {', '.join(propo.files_modified)}")
        
        return {
            "files_modified": propo.files_modified,
            "impact": propo.impact,
        }
