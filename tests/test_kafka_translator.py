import asyncio
import os

# Set required environment variables for Settings before importing
os.environ.setdefault('SOURCE_BOOTSTRAP_SERVERS', 'localhost:9092')
os.environ.setdefault('DEST_BOOTSTRAP_SERVERS', 'localhost:9092')
os.environ.setdefault('SOURCE_TOPIC', 'source-topic')
os.environ.setdefault('DEST_TOPIC', 'dest-topic')

from unittest.mock import AsyncMock, patch
import pytest
from fastapi.testclient import TestClient

# Mock aiokafka classes to avoid real network calls
@pytest.fixture(autouse=True)
def mock_aiokafka():
    with patch('services.kafka_translator.main.AIOKafkaConsumer') as mock_consumer_cls, \
         patch('services.kafka_translator.main.AIOKafkaProducer') as mock_producer_cls:
        
        # Create per-test mocks
        mock_consumer = AsyncMock()
        mock_producer = AsyncMock()
        
        # Set up async returns for start/stop
        async def async_ok(): pass
        
        mock_consumer.start.return_value = asyncio.create_task(async_ok())
        mock_producer.start.return_value = asyncio.create_task(async_ok())
        mock_consumer.stop.return_value = asyncio.create_task(async_ok())
        mock_producer.stop.return_value = asyncio.create_task(async_ok())
        
        # Mock getmany to return empty dict (no messages)
        mock_consumer.getmany.return_value = {}
        
        # Mock producer.send_and_wait to do nothing
        async def fake_send(*args, **kwargs): return None
        mock_producer.send_and_wait.side_effect = fake_send
        
        # Mock commit to do nothing
        mock_consumer.commit.return_value = asyncio.create_task(async_ok())
        
        # Return instances for the context manager
        mock_consumer_cls.return_value = mock_consumer
        mock_producer_cls.return_value = mock_producer
        
        yield {
            'consumer': mock_consumer,
            'producer': mock_producer,
            'consumer_cls': mock_consumer_cls,
            'producer_cls': mock_producer_cls,
        }


from services.kafka_translator.main import app, settings  # noqa: E402


client = TestClient(app)


def test_status_endpoint(mock_aiokafka):
    """Test /status endpoint returns correct metadata."""
    response = client.get('/status')
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data['running'], bool)
    assert data['source_topic'] == 'source-topic'
    assert data['dest_topic'] == 'dest-topic'


def test_settings_use_env_vars(mock_aiokafka):
    """Verify environment variables are read correctly."""
    assert settings.source_bootstrap_servers == 'localhost:9092'
    assert settings.dest_bootstrap_servers == 'localhost:9092'
    assert settings.source_topic == 'source-topic'
    assert settings.dest_topic == 'dest-topic'
    assert settings.group_id == 'ouroboros-translator'
