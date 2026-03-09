"""In-memory Kafka mock broker for Colab-compatible integration testing.

This provides a lightweight Kafka-like interface without requiring Docker,
enabling true integration tests in constrained environments like Colab.
"""
import asyncio
from collections import defaultdict
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import time


@dataclass
class Message:
    """Kafka-like message structure."""
    topic: str
    partition: int
    offset: int
    key: Optional[str] = None
    value: str = ""
    timestamp: float = 0.0


class KafkaMockBroker:
    """In-memory mock of a single-node Kafka cluster.
    
    Features:
    - Topic creation and listing
    - Message produce/consume with offsets
    - Consumer groups with independent offset tracking
    - Async-friendly API
    """
    
    def __init__(self):
        # topic_name -> list of messages
        self._topics: Dict[str, List[Message]] = defaultdict(list)
        
        # (group_id, topic) -> last consumed offset
        self._consumer_offsets: Dict[Tuple[str, str], int] = {}
        
        # Auto-create topics on produce if they don't exist
        self.auto_create_topics = True
        
        # Global message counter for partition assignment
        self._next_offset: Dict[str, int] = defaultdict(int)
    
    def create_topic(self, topic: str) -> None:
        """Create a topic explicitly."""
        if topic not in self._topics:
            self._topics[topic] = []
    
    def list_topics(self) -> List[str]:
        """Return all existing topic names."""
        return list(self._topics.keys())
    
    def produce(
        self,
        topic: str,
        value: str,
        key: Optional[str] = None
    ) -> Message:
        """Produce a message to a topic.
        
        Args:
            topic: Topic name
            value: Message payload (string)
            key: Optional message key
            
        Returns:
            Message with assigned partition and offset
        """
        if self.auto_create_topics and topic not in self._topics:
            self.create_topic(topic)
        
        partition = 0  # Single partition for simplicity
        offset = self._next_offset[topic]
        
        message = Message(
            topic=topic,
            partition=partition,
            offset=offset,
            key=key,
            value=value,
            timestamp=time.time()
        )
        
        self._topics[topic].append(message)
        self._next_offset[topic] += 1
        
        return message
    
    def consume(
        self,
        group_id: str,
        topic: str,
        from_offset: int = 0,
        timeout_ms: int = 1000
    ) -> List[Message]:
        """Consume messages from a topic for a consumer group.
        
        Args:
            group_id: Consumer group identifier
            topic: Topic to consume from
            from_offset: Starting offset (default=0 means latest)
            timeout_ms: Timeout in milliseconds (currently ignored for sync API)
            
        Returns:
            List of messages consumed
        """
        if topic not in self._topics:
            return []
        
        # Get or initialize consumer offset
        key = (group_id, topic)
        start_offset = self._consumer_offsets.get(key, from_offset)
        
        messages = self._topics[topic]
        
        # Filter messages since last offset
        result = [m for m in messages if m.offset >= start_offset]
        
        # Update consumer offset
        if result:
            self._consumer_offsets[key] = result[-1].offset + 1
        
        return result
    
    def get_message_count(self, topic: str) -> int:
        """Return number of messages in a topic."""
        return len(self._topics.get(topic, []))
    
    def reset_consumer_offset(self, group_id: str, topic: str) -> None:
        """Reset consumer offset to beginning."""
        self._consumer_offsets[(group_id, topic)] = 0
    
    def delete_topic(self, topic: str) -> None:
        """Delete a topic."""
        if topic in self._topics:
            del self._topics[topic]


class AsyncKafkaMockBroker(KafkaMockBroker):
    """Async wrapper around KafkaMockBroker."""
    
    async def produce_async(
        self,
        topic: str,
        value: str,
        key: Optional[str] = None
    ) -> Message:
        """Async produce wrapper."""
        return self.produce(topic, value, key)
    
    async def consume_async(
        self,
        group_id: str,
        topic: str,
        from_offset: int = 0
    ) -> List[Message]:
        """Async consume wrapper."""
        return self.consume(group_id, topic, from_offset)


# Global broker instance for pytest fixtures
_global_broker: Optional[KafkaMockBroker] = None


def get_mock_broker() -> KafkaMockBroker:
    """Get or create global mock broker instance."""
    global _global_broker
    if _global_broker is None:
        _global_broker = KafkaMockBroker()
    return _global_broker


def reset_mock_broker() -> None:
    """Reset global broker state."""
    global _global_broker
    _global_broker = None
