"""Kafka Event Translator Service — Reliable message relay between topics/clusters."""

import asyncio
import logging
import time
from typing import Optional

from fastapi import FastAPI
from pydantic import ConfigDict, Field
from pydantic_settings import BaseSettings

try:
    from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
except ImportError:
    raise ImportError(
        "aiokafka is required. Install with: pip install aiokafka"
    )

__version__ = "6.3.0"

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("kafka_translator")

# ============================================================================
# Configuration
# ============================================================================


class Settings(BaseSettings):
    """Configuration via environment variables."""

    model_config = ConfigDict(env_prefix="", extra="ignore")

    # Kafka cluster settings
    source_bootstrap_servers: str = Field(
        default="localhost:9092", description="Kafka bootstrap servers for source cluster"
    )
    dest_bootstrap_servers: str = Field(
        default="localhost:9092", description="Kafka bootstrap servers for destination cluster"
    )

    # Topics
    source_topic: str = Field(default="source-events", description="Source Kafka topic")
    dest_topic: str = Field(default="dest-events", description="Destination Kafka topic")

    # Consumer settings
    group_id: str = Field(default="ouroboros-translator", description="Consumer group ID")
    auto_offset_reset: str = Field(default="earliest", description="Where to start reading if no offset")
    poll_timeout_ms: int = Field(default=5000, description="Maximum time to wait for records")
    max_batch_size: int = Field(default=1000, description="Maximum number of records per poll")

    # Producer settings
    client_id: str = Field(default="translator", description="Client identifier")
    enable_idempotence: bool = Field(default=True, description="Enable exactly-once semantics")
    max_in_flight: int = Field(default=5, description="Max in-flight requests per broker connection")

    # Security (optional)
    security_protocol: str = Field(default="PLAINTEXT", description="Security protocol: PLAINTEXT, SASL_PLAINTEXT, SASL_SSL")
    sasl_mechanism: str = Field(default="PLAIN", description="SASL mechanism: PLAIN, SCRAM-SHA-256, SCRAM-SHA-512")
    sasl_username: Optional[str] = Field(default=None, description="SASL username")
    sasl_password: Optional[str] = Field(default=None, description="SASL password")

    # Retry policy
    max_retries: int = Field(default=3, description="Max retry attempts on transient failures")
    retry_backoff_ms: int = Field(default=1000, description="Backoff between retries in milliseconds")

    # Health check interval (seconds)
    health_check_interval: int = Field(default=60, description="Interval between health checks")


settings = Settings()

# ============================================================================
# Global state
# ============================================================================

consumer: Optional[AIOKafkaConsumer] = None
producer: Optional[AIOKafkaProducer] = None
running: bool = False

# Metrics (thread-safe via asyncio)
metrics = {
    "messages_transferred": 0,
    "errors": 0,
    "last_error": None,
    "start_time": None,
    "bytes_transferred": 0,
}

app = FastAPI(
    title="Kafka Event Translator",
    description=f"Reliable Kafka-to-Kafka message translation v{__version__}",
    version=__version__,
)


# ============================================================================
# Helpers
# ============================================================================


def _build_consumer_kwargs() -> dict:
    """Build kwargs for AIOKafkaConsumer."""
    kwargs = {
        "bootstrap_servers": settings.source_bootstrap_servers.split(","),
        "group_id": settings.group_id,
        "client_id": settings.client_id,
        "enable_auto_commit": False,
        "auto_offset_reset": settings.auto_offset_reset,
    }
    if settings.security_protocol in ("SASL_SSL", "SASL_PLAINTEXT"):
        kwargs["security_protocol"] = settings.security_protocol
        kwargs["sasl_mechanism"] = settings.sasl_mechanism
        if settings.sasl_username:
            kwargs["sasl_plain_username"] = settings.sasl_username
        if settings.sasl_password:
            kwargs["sasl_plain_password"] = settings.sasl_password
    return kwargs


def _build_producer_kwargs() -> dict:
    """Build kwargs for AIOKafkaProducer."""
    kwargs = {
        "bootstrap_servers": settings.dest_bootstrap_servers.split(","),
        "client_id": settings.client_id,
    }
    if settings.enable_idempotence:
        kwargs["enable_idempotence"] = True
        # For idempotent mode, set max_in_flight_requests_per_connection=1 to preserve order
        kwargs["max_in_flight_requests_per_connection"] = 1
    else:
        kwargs["max_in_flight_requests_per_connection"] = settings.max_in_flight

    if settings.security_protocol in ("SASL_SSL", "SASL_PLAINTEXT"):
        kwargs["security_protocol"] = settings.security_protocol
        kwargs["sasl_mechanism"] = settings.sasl_mechanism
        if settings.sasl_username:
            kwargs["sasl_plain_username"] = settings.sasl_username
        if settings.sasl_password:
            kwargs["sasl_plain_password"] = settings.sasl_password
    return kwargs


async def _safe_commit(consumer: AIOKafkaConsumer) -> None:
    """Commit with error handling."""
    try:
        await consumer.commit()
        logger.debug("Offset commit successful")
    except Exception as e:
        logger.error(f"Failed to commit offsets: {e}")
        metrics["errors"] += 1
        metrics["last_error"] = str(e)


async def translate_message(record) -> None:
    """Translate and send a single record with exponential backoff.

    This is the core transformation unit. It:
      1. Sends the record to the destination topic
      2. Retries on failure with exponential backoff
      3. Raises after max_retries to signal batch should not be committed

    If the function returns without raising, the record is considered delivered.
    """
    try:
        # Send message (preserve key, headers, and raw bytes value)
        await producer.send_and_wait(
            topic=settings.dest_topic,
            value=record.value,
            key=record.key,
            headers=record.headers,
        )
        metrics["messages_transferred"] += 1
        if record.value:
            metrics["bytes_transferred"] += len(record.value)
    except Exception as e:
        logger.warning(f"Send error: {e}")
        metrics["errors"] += 1
        metrics["last_error"] = str(e)
        if not await _handle_send_error(e, {"topic": settings.dest_topic}):
            # Max retries exceeded
            raise


async def _handle_send_error(error: Exception, record_data: dict) -> bool:
    """Handle send errors with exponential backoff.

    Returns True if retry succeeded, False if max retries exceeded.
    """
    global running
    if not running:
        return False

    tries = 0
    while running and tries < settings.max_retries:
        delay_ms = settings.retry_backoff_ms * (2**tries)
        logger.warning(
            f"Send error ({error}). Retry {tries + 1}/{settings.max_retries} in {delay_ms}ms"
        )
        await asyncio.sleep(delay_ms / 1000.0)
        tries += 1

    if running:
        logger.error(
            f"Message delivery failed after {settings.max_retries} retries: {record_data}"
        )
    return False


# ============================================================================
# Lifecycle
# ============================================================================


async def create_consumer() -> AIOKafkaConsumer:
    """Create and return a consumer instance."""
    logger.info(f"Creating consumer for topic '{settings.source_topic}'")
    return AIOKafkaConsumer(settings.source_topic, **_build_consumer_kwargs())


async def create_producer() -> AIOKafkaProducer:
    """Create and return a producer instance."""
    logger.info("Creating producer")
    return AIOKafkaProducer(**_build_producer_kwargs())


async def start_services() -> None:
    """Start consumer and producer."""
    global consumer, producer, running

    if running:
        logger.warning("Services already started")
        return

    try:
        logger.info("Starting Kafka services...")
        consumer = await create_consumer()
        producer = await create_producer()

        logger.info("Starting consumer...")
        await consumer.start()
        logger.info(f"Consumer started — listening on {settings.source_topic}")

        logger.info("Starting producer...")
        await producer.start()
        logger.info(f"Producer started — sending to {settings.dest_topic}")

        running = True
        metrics["start_time"] = time.time()
        logger.info("Starting translation loop")
        asyncio.create_task(translate_loop())

    except Exception as e:
        logger.critical(f"Failed to start services: {e}")
        metrics["errors"] += 1
        metrics["last_error"] = str(e)
        raise


async def stop_services() -> None:
    """Stop consumer and producer gracefully."""
    global running

    if not running:
        logger.warning("Services already stopped")
        return

    logger.info("Stopping Kafka services...")
    running = False

    # Wait for any in-flight messages
    await asyncio.sleep(0.5)

    if producer:
        try:
            logger.info("Flushing producer...")
            await producer.flush()
            logger.info("Producer flushed")
        except Exception as e:
            logger.warning(f"Flush failed (non-fatal): {e}")
        finally:
            try:
                await producer.stop()
                logger.info("Producer stopped")
            except Exception as e:
                logger.error(f"Error stopping producer: {e}")

    if consumer:
        try:
            await _safe_commit(consumer)
        finally:
            try:
                await consumer.stop()
                logger.info("Consumer stopped")
            except Exception as e:
                logger.error(f"Error stopping consumer: {e}")

    logger.info("All services stopped")


@app.on_event("startup")
async def on_startup() -> None:
    """FastAPI startup hook."""
    await start_services()


@app.on_event("shutdown")
async def on_shutdown() -> None:
    """FastAPI shutdown hook."""
    await stop_services()


# ============================================================================
# Core translation loop
# ============================================================================


async def translate_loop() -> None:
    """Main message consumption and translation loop.

    Strategy: consume in batches, try to deliver each record.
    Only commit offsets if *all* records in the batch succeed.
    """
    global running, metrics

    retry_count = 0
    while running:
        try:
            # Poll for messages
            msgs = await consumer.getmany(
                timeout_ms=settings.poll_timeout_ms,
                max_records=settings.max_batch_size,
            )

            for tp, records in msgs.items():
                if not records:
                    continue

                # Try to deliver ALL records in this partition
                batch_success = True
                for record in records:
                    try:
                        await translate_message(record)
                    except Exception as e:
                        # One failure is enough to fail the whole batch
                        logger.error(f"Batch failed: record could not be delivered after retries")
                        batch_success = False
                        break

                # Only commit if the whole batch succeeded
                if batch_success:
                    await _safe_commit(consumer)

            retry_count = 0

        except Exception as e:
            logger.error(f"Unexpected error in translate loop: {e}")
            metrics["errors"] += 1
            metrics["last_error"] = str(e)

            if running and retry_count < settings.max_retries:
                delay_ms = settings.retry_backoff_ms * (2**retry_count)
                logger.info(f"Retrying in {delay_ms}ms ({retry_count + 1}/{settings.max_retries})")
                await asyncio.sleep(delay_ms / 1000.0)
                retry_count += 1
            else:
                logger.critical("Max retries exceeded — shutting down")
                await stop_services()
                return


# ============================================================================
# API Endpoints
# ============================================================================


@app.get("/status", tags=["info"])
async def status() -> dict:
    """Return service status and configuration summary."""
    return {
        "running": running,
        "version": __version__,
        "uptime_seconds": round(time.time() - metrics["start_time"], 2)
        if metrics["start_time"]
        else None,
        "messages_transferred": metrics["messages_transferred"],
        "bytes_transferred": metrics["bytes_transferred"],
        "errors": metrics["errors"],
        "last_error": metrics["last_error"],
        "source_topic": settings.source_topic,
        "dest_topic": settings.dest_topic,
        "source_bootstrap_servers": settings.source_bootstrap_servers,
        "dest_bootstrap_servers": settings.dest_bootstrap_servers,
        "group_id": settings.group_id,
    }


@app.get("/metrics", tags=["monitoring"])
async def metrics_endpoint() -> dict:
    """Return metrics in Prometheus-like format."""
    return {
        "messages_transferred": metrics["messages_transferred"],
        "bytes_transferred": metrics["bytes_transferred"],
        "errors": metrics["errors"],
        "last_error": metrics["last_error"],
        "uptime_seconds": round(time.time() - metrics["start_time"], 2)
        if metrics["start_time"]
        else None,
        "running": running,
    }


@app.get("/health", tags=["monitoring"])
async def health() -> dict:
    """Simple health check."""
    return {
        "status": "healthy" if running else "starting",
        "version": __version__,
    }


# ============================================================================
# CLI entrypoint
# ============================================================================


if __name__ == "__main__":
    import uvicorn

    logger.info(f"Starting Kafka Translator v{__version__}")
    logger.info(f"Listening on 0.0.0.0:8000")

    uvicorn.run(app, host="0.0.0.0", port=8000)
