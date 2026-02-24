import os
import asyncio
from unittest.mock import AsyncMock, patch

# Set required environment variables for Settings
os.environ.setdefault('SOURCE_BOOTSTRAP_SERVERS', 'localhost:9092')
os.environ.setdefault('DEST_BOOTSTRAP_SERVERS', 'localhost:9092')
os.environ.setdefault('SOURCE_TOPIC', 'source-topic')
os.environ.setdefault('DEST_TOPIC', 'dest-topic')

# Import after env is set
from fastapi.testclient import TestClient

# Mock aiokafka classes to avoid real network calls
mock_consumer = AsyncMock()
mock_producer = AsyncMock()
mock_consumer.start.return_value = asyncio.Future()
mock_consumer.start.return_value.set_result(None)
mock_producer.start.return_value = asyncio.Future()
mock_producer.start.return_value.set_result(None)
mock_consumer.stop.return_value = asyncio.Future()
mock_consumer.stop.return_value.set_result(None)
mock_producer.stop.return_value = asyncio.Future()
mock_producer.stop.return_value.set_result(None)

with patch('services.kafka_translator.main.AIOKafkaConsumer', return_value=mock_consumer), \
     patch('services.kafka_translator.main.AIOKafkaProducer', return_value=mock_producer):
    from services.kafka_translator.main import app, settings
    client = TestClient(app)
    response = client.get('/status')
    assert response.status_code == 200
    data = response.json()
    # The translator should not be running yet in test client context because startup runs but mocked loop does nothing
    assert isinstance(data['running'], bool)
    assert data['source_topic'] == settings.source_topic
    assert data['dest_topic'] == settings.dest_topic
    assert data['source_bootstrap_servers'] == settings.source_bootstrap_servers
    assert data['dest_bootstrap_servers'] == settings.dest_bootstrap_servers
