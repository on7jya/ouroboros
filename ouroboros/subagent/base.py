"""Base classes for Ouroboros subagents — cooperative evolution protocol."""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("ouroboros.subagent")


class AgentRole(Enum):
    """Subagent roles in cooperative evolution."""
    PLANNER = "planner"
    CODER = "coder"
    TESTER = "tester"
    REFLECTOR = "reflector"


class MessageBus(ABC):
    """Abstract message bus for subagent communication."""

    @abstractmethod
    async def publish(self, channel: str, payload: Dict[str, Any]) -> None:
        """Publish a message to a channel."""
        raise NotImplementedError

    @abstractmethod
    async def subscribe(self, channel: str, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Subscribe to a channel."""
        raise NotImplementedError

    @abstractmethod
    async def close(self) -> None:
        """Close the bus."""
        raise NotImplementedError


@dataclass
class Proposal:
    """Evolution proposal from Planner to Coder."""
    id: str
    type: str  # "feature", "refactor", "fix", "evolution"
    description: str
    files_modified: List[str] = field(default_factory=list)
    impact: Dict[str, str] = field(default_factory=dict)


@dataclass
class Vote:
    """Vote from Coder/Testers on a proposal."""
    agent: str
    decision: bool  # True = approve, False = reject
    reason: Optional[str] = None


@dataclass
class ROI:
    """Return on investment — Reflector's evaluation."""
    tokens_spent: int
    capabilities_gained: List[str]
    drift_cycles_prevented: int = 0


class Subagent(ABC):
    """Base class for Ouroboros subagents."""

    def __init__(self, role: AgentRole):
        self.role = role
        self.name = f"ouroboros-{role.value}"
        self.running = False
        self.bus: Optional[MessageBus] = None

    async def connect(self, bus: MessageBus) -> None:
        """Connect to the message bus."""
        self.bus = bus
        logger.info(f"{self.name} connected to message bus")

    async def start(self) -> None:
        """Start the subagent's main loop."""
        self.running = True
        logger.info(f"{self.name} started")

    async def stop(self) -> None:
        """Stop the subagent."""
        self.running = False
        logger.info(f"{self.name} stopped")

    @abstractmethod
    async def handle_message(self, payload: Dict[str, Any]) -> None:
        """Handle an incoming message."""
        raise NotImplementedError

    async def broadcast(self, channel: str, payload: Dict[str, Any]) -> None:
        """Broadcast a message to all subagents."""
        if self.bus:
            await self.bus.publish(channel, payload)

    async def propose(self, proposal: Proposal) -> None:
        """Send a proposal to the Coder."""
        await self.broadcast("evolution", {
            "type": "proposal",
            "agent": self.name,
            "proposal_id": proposal.id,
            "payload": {
                "type": proposal.type,
                "description": proposal.description,
                "files_modified": proposal.files_modified,
                "impact": proposal.impact,
            },
        })

    async def vote(self, proposal_id: str, decision: bool, reason: Optional[str] = None) -> None:
        """Cast a vote for a proposal."""
        await self.broadcast("vote", {
            "type": "vote",
            "agent": self.name,
            "proposal_id": proposal_id,
            "decision": decision,
            "reason": reason,
        })

    async def log_roi(self, roi: ROI) -> None:
        """Log ROI for Reflector's evaluation."""
        await self.broadcast("roi", {
            "type": "roi",
            "agent": self.name,
            "payload": {
                "tokens_spent": roi.tokens_spent,
                "capabilities_gained": roi.capabilities_gained,
                "drift_cycles_prevented": roi.drift_cycles_prevented,
            },
        })


class KafkaMessageBus(MessageBus):
    """Message bus backed by Kafka (v6.8 protocol)."""

    def __init__(self, bootstrap_servers: str = "localhost:9092"):
        self.bootstrap_servers = bootstrap_servers
        self._consumers: Dict[str, Any] = {}
        self._producers: Dict[str, Any] = {}

    async def publish(self, channel: str, payload: Dict[str, Any]) -> None:
        """Publish a message to a Kafka topic."""
        if channel not in self._producers:
            from aiokafka import AIOKafkaProducer
            producer = AIOKafkaProducer(bootstrap_servers=self.bootstrap_servers)
            await producer.start()
            self._producers[channel] = producer

        try:
            await self._producers[channel].send(
                topic=channel,
                value=json.dumps(payload).encode()
            )
            await self._producers[channel].flush()
        except Exception as e:
            logger.error(f"Failed to publish to {channel}: {e}")

    async def subscribe(self, channel: str, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Subscribe to a Kafka topic."""
        if channel not in self._consumers:
            from aiokafka import AIOKafkaConsumer
            consumer = AIOKafkaConsumer(
                channel,
                bootstrap_servers=self.bootstrap_servers,
                group_id=f"subagent-{channel}",
            )
            await consumer.start()
            self._consumers[channel] = consumer

            async def listener():
                try:
                    async for msg in consumer:
                        try:
                            payload = json.loads(msg.value.decode())
                            await callback(payload)
                        except Exception as e:
                            logger.error(f"Error processing message: {e}")
                except Exception as e:
                    logger.critical(f"Consumer error on channel {channel}: {e}")

            asyncio.create_task(listener())

    async def close(self) -> None:
        """Close all connections."""
        for consumer in self._consumers.values():
            try:
                await consumer.stop()
            except Exception as e:
                logger.error(f"Error stopping consumer: {e}")
        self._consumers.clear()

        for producer in self._producers.values():
            try:
                await producer.stop()
            except Exception as e:
                logger.error(f"Error stopping producer: {e}")
        self._producers.clear()
