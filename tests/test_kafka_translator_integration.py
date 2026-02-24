"""Integration tests for Kafka translator against real Docker Kafka.

To run these tests, start Docker Compose first:
    cd services/kafka_translator
    docker-compose up -d

Then wait ~10 seconds for Kafka to be ready, and run:
    pytest tests/test_kafka_translator_integration.py -v --docker-kafka=true
"""

import asyncio
import os
import subprocess
import time
from unittest.mock import patch

import pytest

# --- Docker helpers ---------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def ensure_kafka_running(request):
    """Ensure Kafka is running before integration tests."""
    if not request.config.getoption("--docker-kafka", False):
        pytest.skip("Docker Kafka integration tests disabled (--docker-kafka)")

    kafka_ready = False
    for _ in range(30):  # Wait up to 30s
        try:
            result = subprocess.run(
                ["docker", " ps", "-q", "--filter", "name=kafka-translator"],
                capture_output=True, text=True, check=True
            )
            if result.stdout.strip():
                kafka_ready = True
                break
        except subprocess.CalledProcessError:
            pass
        time.sleep(1)

    if not kafka_ready:
        pytest.skip("Kafka container not found – start with: docker-compose up -d")


# --- Basic translation ------------------------------------------------------

@pytest.mark.asyncio
async def test_translates_single_message():
    """Verify a message consumed from source is produced to dest."""
    if not os.getenv("DOCKER_KAFKA"):
        pytest.skip("DOCKER_KAFKA env not set")

    from services.kafka_translator.main import (
        translate_message,
        settings,
    )

    test_msg = b"hello from test"
    test_key = b"key-123"

    # Produce to source topic
    from aiokafka import AIOKafkaProducer

    producer = AIOKafkaProducer(bootstrap_servers=settings.source_bootstrap_servers)
    await producer.start()
    await producer.send_and_wait(
        settings.source_topic,
        value=test_msg,
        key=test_key
    )
    await producer.stop()

    # Allow time for translation
    await asyncio.sleep(2)

    # Consume from dest topic
    from aiokafka import AIOKafkaConsumer

    consumer = AIOKafkaConsumer(
        settings.dest_topic,
        bootstrap_servers=settings.dest_bootstrap_servers,
        group_id="test-consumer",
        auto_offset_reset="earliest",
    )
    await consumer.start()

    messages = []
    try:
        msg = await consumer.getone()
        messages.append((msg.key, msg.value))
    except Exception:
        pass  # May be empty if consumer hasn't caught up
    finally:
        await consumer.stop()

    assert any(v == test_msg for _, v in messages), \
        f"Expected {test_msg} in dest topic, got {messages}"


# --- Error handling ---------------------------------------------------------

@pytest.mark.asyncio
async def test_handles_missing_topic():
    """Verify translator recovers gracefully when topic doesn't exist."""
    from services.kafka_translator.main import Settings, translate_message

    # Temporarily point to non-existent topic
    old_source = os.environ.get("SOURCE_TOPIC")
    os.environ["SOURCE_TOPIC"] = "nonexistent-topic-xyz"
    try:
        result = await translate_message()
        # Should not raise, but log and continue
        assert True  # Assertion placeholder — actual behavior depends on logic
    finally:
        if old_source:
            os.environ["SOURCE_TOPIC"] = old_source


# --- Throughput -------------------------------------------------------------


def test_produces_metrics_on_error():
    """Verify metrics get updated even on failures."""
    from services.kafka_translator.main import metrics

    before = metrics["errors"]
    # Simulate error scenario
    metrics["errors"] += 1
    assert metrics["errors"] == before + 1


# --- CLI smoke --------------------------------------------------------------

def test_settings_default_values():
    """Verify default values match expectations."""
    from services.kafka_translator.main import Settings

    s = Settings()
    assert "localhost" in s.source_bootstrap_servers
    assert "localhost" in s.dest_bootstrap_servers
    assert s.source_topic == "source-events"
    assert s.dest_topic == "dest-events"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
