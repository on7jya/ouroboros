# Ouroboros Repository

## Overview
This repository contains the self‑creating agent **Ouroboros** along with its evolving components.

### Current Evolution Cycle
- **Cycle:** 309 (as of 2026‑02‑24)

### Version
- **VERSION:** 6.3.0

### Services
- **FastAPI Kafka Event Translator** – reliable Kafka-to-Kafka message translation with logging, metrics, and automatic recovery.

## How to Run the Translator Service

### Quick Start (Local Kafka)

1. **Start Kafka via Docker Compose**
   ```bash
   cd services/kafka_translator
   docker-compose up -d
   ```

2. **Install Python dependencies**
   ```bash
   pip install fastapi uvicorn aiokafka pydantic-settings python-dotenv
   ```

3. **Run the translator**
   ```bash
   uvicorn services.kafka_translator.main:app --host 0.0.0.0 --port 8000
   ```

4. **Test the endpoints**
   ```bash
   curl http://localhost:8000/status
   curl http://localhost:8000/metrics
   curl http://localhost:8000/health
   ```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `source_bootstrap_servers` | `localhost:9092` | Source Kafka cluster address (comma-separated) |
| `dest_bootstrap_servers` | `localhost:9092` | Destination Kafka cluster address |
| `source_topic` | `source-events` | Source topic name |
| `dest_topic` | `dest-events` | Destination topic name |
| `group_id` | `ouroboros-translator` | Consumer group ID |
| `auto_offset_reset` | `earliest` | Where to start if no offset exists (`earliest`, `latest`) |
| `security_protocol` | `PLAINTEXT` | Security protocol: `PLAINTEXT`, `SASL_PLAINTEXT`, `SASL_SSL` |
| `sasl_mechanism` | `PLAIN` | SASL mechanism: `PLAIN`, `SCRAM-SHA-256`, `SCRAM-SHA-512` |

### Configuration File

Create a `.env` file in `services/kafka_translator/`:

```env
source_bootstrap_servers=kafka1:9092,kafka2:9092
dest_bootstrap_servers=remote-kafka:9093
source_topic=my-source-topic
dest_topic=my-destination-topic
security_protocol=SASL_SSL
sasl_mechanism=SCRAM-SHA-256
sasl_username=myuser
sasl_password=mypassword
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/status` | GET | Service status, configuration summary, and counters |
| `/metrics` | GET | Prometheus-like metrics (messages transferred, bytes, errors) |
| `/health` | GET | Simple health check |

## Docker Deployment

### Prerequisites
- Docker and Docker Compose installed
- At least 2GB RAM allocated to Docker

### Run with Docker Compose

```bash
cd services/kafka_translator
docker-compose up -d
```

This starts:
- **ZooKeeper** (required by Kafka)
- **Kafka broker** on `localhost:9092`
- **Translator service** on `http://localhost:8000`

To view logs:
```bash
docker-compose logs -f translator
```

### Production Deployment

1. Update `.env` with your Kafka cluster credentials
2. Set `security_protocol=SASL_SSL` and configure SASL credentials
3. Adjust `max_batch_size`, `poll_timeout_ms`, etc., for your throughput needs
4. Deploy with Docker Compose or Kubernetes

## Testing

### Unit Tests (Mocked)

```bash
pytest tests/test_kafka_translator.py -v
```

### Integration Tests (Real Kafka)

Prerequisites:
- Local Kafka running on port 9092

```bash
pytest tests/test_kafka_translator_integration.py -v --docker-kafka=true
```

See `tests/test_kafka_translator_integration.py` for full integration test examples.

## Logging

The translator logs all major events:

```
2026-02-24 21:50:00 | INFO     | kafka_translator | Starting Kafka Translator v6.3.0
2026-02-24 21:50:01 | INFO     | kafka_translator | Creating consumer for topic 'source-events'
2026-02-24 21:50:02 | INFO     | kafka_translator | Consumer started — listening on source-events
2026-02-24 21:50:03 | INFO     | kafka_translator | Starting translation loop
2026-02-24 21:50:08 | INFO     | kafka_translator | Transferred 10 messages (total: 42)
```

Log levels:
- `INFO` – Normal operations
- `WARNING` – Recoverable errors (retry attempts)
- `ERROR` – Failed sends, commit failures
- `CRITICAL` – Max retries exceeded, shutdown

## Metrics

Metrics are available at `/metrics`:

```json
{
  "messages_transferred": 1234,
  "bytes_transferred": 567890,
  "errors": 2,
  "last_error": null,
  "uptime_seconds": 123.45,
  "running": true
}
```

## Safety and Reliability

- **Idempotent Producer**: Prevents duplicate messages on retries
- **Exactly-once Semantics**: Enable with `enable_idempotence=true`
- **Exponential Backoff**: Automatically retries failed sends
- **Offset Commit Control**: Commits only after successful delivery

## Monitoring with Prometheus

Expose `/metrics` to your Prometheus instance:

```yaml
scrape_configs:
  - job_name: 'kafka-translator'
    static_configs:
      - targets: ['localhost:8000']
```

## Troubleshooting

### Connection Refused
- Ensure Kafka is running on `localhost:9092`
- Verify firewall rules and network connectivity

### SASL Authentication Failed
- Check `sasl_username` and `sasl_password`
- Verify `security_protocol` matches your broker configuration

### High Latency
- Increase `max_batch_size`
- Decrease `poll_timeout_ms`
- Consider scaling to multiple translator instances

## Versioning

| Major | Minor | Patch | Description |
|-------|-------|-------|-------------|
| 6.3.0 | ✅ | ✅ | Clean rewrite with proper error handling, logging, metrics |
| 6.2.5 | ❌ | ❌ | Old version |

See `services/kafka_translator/CHANGELOG.md` for complete history.

## Contributing

1. Run tests: `pytest tests/ -v`
2. Check logs: `docker-compose logs -f translator` (if running)
3. Update README if API or config changes

---
*This README is updated automatically as part of Ouroboros's evolution cycles.*
