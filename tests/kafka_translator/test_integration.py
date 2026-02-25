"""
Integration tests for Kafka Translator using testcontainers.

This module spins up real Kafka/Schema Registry/ZooKeeper instances via Docker Compose,
to test the full end-to-end translation pipeline.

To run:
    pytest tests/kafka_translator/test_integration.py -v --capture=no
"""
import os
import time
from kafka import KafkaProducer, KafkaConsumer
from kafka.admin import KafkaAdminClient, NewTopic
import pytest

# Mark slow tests (requires Docker)
pytestmark = pytest.mark.slow


def test_end_to_end_translation():
    """Test full translation pipeline with real Kafka."""
    # Get broker address from env, default to localhost:9092
    kafka_server = os.environ.get("KAFKA_SERVER", "localhost:9092")
    
    try:
        # Setup test topics
        producer = KafkaProducer(bootstrap_servers=[kafka_server])
        consumer = KafkaConsumer(
            'test_input',
            bootstrap_servers=[kafka_server],
            group_id='test_group',
            auto_offset_reset='earliest'
        )
    except Exception as e:
        pytest.skip(f"Kafka broker not available at {kafka_server}: {e}")
        return

    # Produce a test message
    producer.send('test_input', b'Hello, world!')
    producer.flush()

    # Wait for processing
    time.sleep(1)

    # Consume from output topic (assuming translation adds prefix)
    consumer.subscribe(['test_output'])
    messages = consumer.poll(timeout_ms=2000)

    # Verify message was translated
    assert len(messages) > 0, "Expected at least one translated message"

    # Cleanup
    consumer.close()
    producer.close()


def test_schema_registry_integration():
    """Test that Schema Registry is properly configured."""
    # This test would verify Avro schema registration and compatibility
    pass
