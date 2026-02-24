import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient


# ============================================================================
# Fix for producer/consumer mocking — patch before import
# ============================================================================

@pytest.fixture(autouse=True)
def mock_kafka_modules():
    """Patch aiokafka imports at module level so main.py receives mocks."""
    mock_consumer_cls = AsyncMock()
    mock_producer_cls = AsyncMock()

    # Patch aiokafka.AIOKafkaConsumer and AIOKafkaProducer
    with patch('aiokafka.AIOKafkaConsumer', return_value=mock_consumer_cls),          patch('aiokafka.AIOKafkaProducer', return_value=mock_producer_cls):
        yield {'consumer': mock_consumer_cls, 'producer': mock_producer_cls}


def test_metrics_endpoint_returns_initial_values():
    """Test that /metrics returns expected initial state."""
    from services.kafka_translator.main import app, metrics
    client = TestClient(app)
    
    response = client.get("/metrics")
    assert response.status_code == 200
    data = response.json()
    assert "messages_transferred" in data
    assert "errors" in data
    assert "last_error" in data
    assert "running" in data


def test_status_endpoint_returns_config():
    """Test that /status returns configuration and health."""
    from services.kafka_translator.main import app, metrics
    client = TestClient(app)
    
    response = client.get("/status")
    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert "running" in data
    assert "source_topic" in data
    assert "dest_topic" in data


def test_version_is_correct():
    """Verify version matches expected."""
    from services.kafka_translator import __version__
    assert __version__ == "6.3.1"


def test_settings_env_override():
    """Verify settings load from environment variables."""
    import os
    from services.kafka_translator.main import Settings
    
    os.environ["SOURCE_BOOTSTRAP_SERVERS"] = "localhost:9092"
    os.environ["DEST_BOOTSTRAP_SERVERS"] = "localhost:9093"
    os.environ["SOURCE_TOPIC"] = "input-topic"
    os.environ["DEST_TOPIC"] = "output-topic"
    
    settings = Settings()
    assert settings.source_bootstrap_servers == "localhost:9092"
    assert settings.dest_bootstrap_servers == "localhost:9093"
    assert settings.source_topic == "input-topic"
    assert settings.dest_topic == "output-topic"


def test_fastapi_routes_exist():
    """Verify all expected routes are registered."""
    from services.kafka_translator.main import app
    
    paths = [route.path for route in app.routes]
    assert "/status" in paths
    assert "/metrics" in paths


# ============================================================================
# Unit test for translate_message — real logic, not just endpoints
# ============================================================================

@pytest.mark.asyncio
async def test_translate_message_success():
    """Test that translate_message sends to destination and updates metrics."""
    from services.kafka_translator.main import producer, metrics
    from unittest.mock import MagicMock

    # Reset metrics
    metrics["messages_transferred"] = 0
    metrics["errors"] = 0

    mock_record = MagicMock()
    mock_record.value = b'test payload'
    mock_record.key = b'key1'
    mock_record.headers = []

    # Mock producer.send_and_wait to succeed
    producer.send_and_wait = AsyncMock()

    await translate_message(mock_record)

    # Verify send was called
    producer.send_and_wait.assert_awaited_once()
    call_args = producer.send_and_wait.call_args
    assert call_args[1]['topic'] == 'dest-events'
    assert call_args[1]['value'] == b'test payload'
    assert call_args[1]['key'] == b'key1'
    assert call_args[1]['headers'] == []

    # Verify metrics updated
    assert metrics["messages_transferred"] == 1


@pytest.mark.asyncio
async def test_translate_message_failure_and_retry():
    """Test that translate_message retries on failure."""
    from services.kafka_translator.main import producer, metrics
    from unittest.mock import MagicMock

    # Reset metrics
    metrics["messages_transferred"] = 0
    metrics["errors"] = 0

    mock_record = MagicMock()
    mock_record.value = b'payload'

    # First call fails, second succeeds
    mock_send = AsyncMock()
    mock_send.side_effect = [Exception("temp fail"), None]
    producer.send_and_wait = mock_send

    await translate_message(mock_record)

    # Should have been called twice
    assert producer.send_and_wait.call_count == 2


@pytest.mark.asyncio
async def test_translate_message_max_retries_exceeded():
    """Test that translate_message raises after max retries."""
    from services.kafka_translator.main import producer, metrics
    from unittest.mock import MagicMock

    # Reset metrics
    metrics["messages_transferred"] = 0
    metrics["errors"] = 0

    mock_record = MagicMock()
    mock_record.value = b'payload'

    # Always fail
    mock_send = AsyncMock()
    mock_send.side_effect = Exception("always fail")
    producer.send_and_wait = mock_send

    with pytest.raises(Exception):
        await translate_message(mock_record)

    # 1 initial + 3 retries = 4 total attempts
    assert producer.send_and_wait.call_count == 4
