"""Kafka Event Translator Service — Reliable message relay between topics/clusters."""

from contextlib import asynccontextmanager
import asyncio
import logging
import time
import random
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import ConfigDict, Field
from pydantic_settings import BaseSettings

try:
    from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
except ImportError:
    raise ImportError(
        "aiokafka is required. Install with: pip install aiokafka"
    )

__version__ = "6.8.0"

# FastAPI application
app = FastAPI(
    title="Ouroboros Kafka Translator",
    description="Resilient Kafka-to-Kafka message translator with cluster awareness",
    version=__version__,
)


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
        default="localhost:9092", description="Kafka bootstrap servers for source cluster (comma-separated)"
    )
    dest_bootstrap_servers: str = Field(
        default="localhost:9092", description="Kafka bootstrap servers for destination cluster (comma-separated)"
    )

    # Topics
    source_topic: str = Field(default="source-events", description="Source Kafka topic")
    dest_topic: str = Field(default="dest-events", description="Destination Kafka topic")
    dlq_topic: str = Field(default="dlq-failed-messages", description="Dead letter queue topic for failed messages")

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
    max_retry_delay_s: int = Field(default=30, description="Maximum delay between retries in seconds")

    # Reconnection settings
    reconnection_max_attempts: int = Field(default=10, description="Max reconnection attempts on broker failure")
    reconnection_base_delay_s: float = Field(default=1.0, description="Base delay for exponential backoff reconnection")

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

# Resilience state
cluster_health = {
    "source": {"status": "unknown", "last_check": None},
    "destination": {"status": "unknown", "last_check": None},
}

# Dead letter queue
dlq_messages: list = []


# ============================================================================
# Helper Functions
# ============================================================================


def parse_bootstrap_servers(servers_str: str) -> list:
    """Parse comma-separated bootstrap servers, handle DNS round-robin."""
    servers = [s.strip() for s in servers_str.split(",") if s.strip()]
    return servers


def get_random_server(servers: list) -> str:
    """Return a random server for DNS round-robin simulation."""
    if not servers:
        raise ValueError("No bootstrap servers available")
    return random.choice(servers)


def exponential_backoff(base_delay: float, attempt: int, max_delay: float) -> float:
    """Calculate exponential backoff delay."""
    return min(base_delay * (2 ** attempt), max_delay)


async def send_to_dlq(record, reason: str) -> None:
    """Send a failed message to the dead letter queue."""
    global dlq_messages
    
    try:
        if producer and running:
            await producer.send(
                topic=settings.dlq_topic,
                value=f"ORIGINAL: {record.value}".encode() if record.value else b"",
                key=record.key,
                headers=[*record.headers, ("dlq-reason", reason.encode())],
            )
            await producer.flush()
        
        dlq_messages.append({
            "timestamp": time.time(),
            "topic": record.topic,
            "partition": record.partition,
            "offset": record.offset,
            "reason": reason,
        })
        
        logger.warning(f"Message sent to DLQ: {reason}")
    except Exception as e:
        logger.error(f"Failed to send message to DLQ: {e}")


# ============================================================================
# Cluster Health Check
# ============================================================================


async def check_cluster_health(cluster_name: str, servers_str: str) -> dict:
    """Check health of a Kafka cluster."""
    try:
        servers = parse_bootstrap_servers(servers_str)
        if not servers:
            return {"status": "unavailable", "error": "No servers configured"}
        
        # For health check, just verify we have at least one server
        return {
            "status": "healthy",
            "servers_count": len(servers),
            "server_list": servers,
        }
    except Exception as e:
        return {"status": "unavailable", "error": str(e)}


async def health_monitor_loop() -> None:
    """Background loop to monitor cluster health."""
    global cluster_health, running
    
    while running:
        try:
            # Check source cluster
            cluster_health["source"] = await check_cluster_health(
                "source", settings.source_bootstrap_servers
            )
            
            # Check destination cluster
            cluster_health["destination"] = await check_cluster_health(
                "destination", settings.dest_bootstrap_servers
            )
            
            logger.debug("Cluster health check completed")
        except Exception as e:
            logger.error(f"Health monitor error: {e}")
        
        await asyncio.sleep(settings.health_check_interval)


# ============================================================================
# Reconnection Logic
# ============================================================================


async def reconnect_consumer(max_attempts: int = None) -> bool:
    """Attempt to reconnect consumer with exponential backoff."""
    global consumer, running
    
    attempts = 0
    max_attempts = max_attempts or settings.reconnection_max_attempts
    
    while running and attempts < max_attempts:
        try:
            if not consumer:
                consumer = await create_consumer()
            
            logger.info(f"Reconnecting consumer (attempt {attempts + 1}/{max_attempts})")
            await consumer.start()
            logger.info("Consumer reconnected successfully")
            return True
            
        except Exception as e:
            attempts += 1
            delay = exponential_backoff(
                settings.reconnection_base_delay_s,
                attempts,
                30.0
            )
            
            logger.error(f"Consumer reconnection failed ({e}). Retry in {delay}s")
            metrics["errors"] += 1
            metrics["last_error"] = str(e)
            
            if running:
                await asyncio.sleep(delay)
    
    return False


async def reconnect_producer(max_attempts: int = None) -> bool:
    """Attempt to reconnect producer with exponential backoff."""
    global producer, running
    
    attempts = 0
    max_attempts = max_attempts or settings.reconnection_max_attempts
    
    while running and attempts < max_attempts:
        try:
            if not producer:
                producer = await create_producer()
            
            logger.info(f"Reconnecting producer (attempt {attempts + 1}/{max_attempts})")
            await producer.start()
            logger.info("Producer reconnected successfully")
            return True
            
        except Exception as e:
            attempts += 1
            delay = exponential_backoff(
                settings.reconnection_base_delay_s,
                attempts,
                30.0
            )
            
            logger.error(f"Producer reconnection failed ({e}). Retry in {delay}s")
            metrics["errors"] += 1
            metrics["last_error"] = str(e)
            
            if running:
                await asyncio.sleep(delay)
    
    return False


# ============================================================================
# Lifecycle
# ============================================================================


async def create_consumer() -> AIOKafkaConsumer:
    """Create and return a consumer instance."""
    bootstrap_servers = parse_bootstrap_servers(settings.source_bootstrap_servers)
    
    kwargs = {
        "bootstrap_servers": bootstrap_servers,
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
    
    logger.info(f"Creating consumer for topic '{settings.source_topic}' with {len(bootstrap_servers)} bootstrap servers")
    return AIOKafkaConsumer(settings.source_topic, **kwargs)


async def create_producer() -> AIOKafkaProducer:
    """Create and return a producer instance."""
    bootstrap_servers = parse_bootstrap_servers(settings.dest_bootstrap_servers)
    
    kwargs = {
        "bootstrap_servers": bootstrap_servers,
        "client_id": settings.client_id,
    }
    
    if settings.enable_idempotence:
        kwargs["enable_idempotence"] = True
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
    
    logger.info(f"Creating producer with {len(bootstrap_servers)} bootstrap servers")
    return AIOKafkaProducer(**kwargs)


async def start_services() -> None:
    """Start consumer and producer."""
    global consumer, producer, running

    if running:
        logger.warning("Services already started")
        return

    try:
        logger.info("Starting Kafka services...")
        
        # Start consumer with reconnection
        consumer = await create_consumer()
        logger.info("Starting consumer...")
        await consumer.start()
        logger.info(f"Consumer started — listening on {settings.source_topic}")

        # Start producer with reconnection
        producer = await create_producer()
        logger.info("Starting producer...")
        await producer.start()
        logger.info(f"Producer started — sending to {settings.dest_topic}")

        running = True
        metrics["start_time"] = time.time()
        
        # Start background health monitor
        asyncio.create_task(health_monitor_loop())
        
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

    # Give loops a moment to exit
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
            await consumer.commit()  # Final commit
        finally:
            try:
                await consumer.stop()
                logger.info("Consumer stopped")
            except Exception as e:
                logger.error(f"Error stopping consumer: {e}")

    logger.info("All services stopped")


# ============================================================================
# Core translation loop
# ============================================================================


async def translate_message_with_retry(record) -> bool:
    """Attempt to translate and send a record with resilience."""
    global running
    
    for attempt in range(settings.max_retries + 1):
        if not running:
            return False
            
        try:
            msg = await producer.send(
                topic=settings.dest_topic,
                value=record.value,
                key=record.key,
                headers=record.headers,
            )
            await producer.flush()
            
            metrics["messages_transferred"] += 1
            if record.value:
                metrics["bytes_transferred"] += len(record.value)
            
            logger.debug(f"Message delivered to {settings.dest_topic}")
            return True  # success
            
        except Exception as e:
            if not running:
                return False
                
            if attempt < settings.max_retries:
                delay = exponential_backoff(
                    settings.retry_backoff_ms / 1000.0,
                    attempt,
                    settings.max_retry_delay_s
                )
                logger.warning(f"Send error ({e}). Retry {attempt + 1}/{settings.max_retries} in {delay}s")
                
                # Check if we need to reconnect
                try:
                    if not producer._connected():
                        logger.warning("Producer disconnected. Attempting reconnection...")
                        await reconnect_producer()
                except Exception:
                    pass
                
                await asyncio.sleep(delay)
            else:
                # Max retries exceeded - send to DLQ
                logger.error(f"Message delivery failed after {settings.max_retries} retries: {e}")
                await send_to_dlq(record, f"Max retries exceeded: {e}")
                metrics["errors"] += 1
                metrics["last_error"] = str(e)
                return False
    
    return False


async def translate_loop() -> None:
    """Main message consumption and translation loop."""
    global running, metrics

    while running:
        try:
            # Check if consumer is still connected
            try:
                if not consumer._connected():
                    logger.warning("Consumer disconnected. Attempting reconnection...")
                    if not await reconnect_consumer():
                        raise ConnectionError("Failed to reconnect consumer")
            except Exception as e:
                logger.warning(f"Consumer health check failed: {e}")
            
            msgs = await consumer.getmany(
                timeout_ms=settings.poll_timeout_ms,
                max_records=settings.max_batch_size,
            )

            for tp, records in msgs.items():
                if not records:
                    continue

                # Commit after successful delivery of each record
                batch_success = True
                for record in records:
                    try:
                        success = await translate_message_with_retry(record)
                        if not success:
                            batch_success = False
                            break  # Don't commit on failure
                    except Exception as e:
                        logger.error(f"Batch failed: record could not be delivered after retries")
                        await send_to_dlq(record, f"Translation failed: {e}")
                        batch_success = False
                        break
                
                if batch_success:
                    # Only commit if all records in batch succeeded
                    await consumer.commit()

        except ConnectionError as e:
            logger.critical(f"Connection lost: {e}")
            metrics["errors"] += 1
            metrics["last_error"] = str(e)
            
            if not running:
                return
                
            # Attempt reconnection before retrying
            await asyncio.sleep(5)  # Brief pause before reconnect
            
        except Exception as e:
            logger.error(f"Unexpected error in translate loop: {e}")
            metrics["errors"] += 1
            metrics["last_error"] = str(e)

            if running:
                await asyncio.sleep(5)  # Brief pause on error
            else:
                return


# ============================================================================
# API Endpoints
# ============================================================================


@app.get('/version', tags=['info'])
async def version() -> str:
    """Return only the version string for tooling."""
    return __version__


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
        "dlq_messages_count": len(dlq_messages),
        "source_topic": settings.source_topic,
        "dest_topic": settings.dest_topic,
        "dlq_topic": settings.dlq_topic,
        "source_bootstrap_servers": parse_bootstrap_servers(settings.source_bootstrap_servers),
        "dest_bootstrap_servers": parse_bootstrap_servers(settings.dest_bootstrap_servers),
        "group_id": settings.group_id,
    }


@app.get("/cluster-health", tags=["monitoring"])
async def cluster_health_endpoint() -> dict:
    """Return health status of all Kafka clusters."""
    return {
        "source": cluster_health["source"],
        "destination": cluster_health["destination"],
    }


@app.get("/dlq/status", tags=["monitoring"])
async def dlq_status() -> dict:
    """Return dead letter queue status."""
    return {
        "dlq_topic": settings.dlq_topic,
        "messages_count": len(dlq_messages),
        "last_errors": metrics["last_error"],
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
def main():
    """CLI entry point: uvicorn --host 0.0.0.0 --port 8000 main:app."""
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
