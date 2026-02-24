import asyncio
import logging
import time
from typing import Optional

from fastapi import FastAPI
from pydantic import Field, ConfigDict
from pydantic_settings import BaseSettings
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

__version__ = "6.3.0"

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
logger = logging.getLogger("kafka_translator")

class Settings(BaseSettings):
    model_config = ConfigDict(env_prefix="", extra="ignore")
    
    source_bootstrap_servers: str = Field(default="localhost:9092", description="Kafka bootstrap servers for source cluster")
    dest_bootstrap_servers: str = Field(default="localhost:9092", description="Kafka bootstrap servers for destination cluster")
    source_topic: str = Field(default="source-events", description="Source Kafka topic")
    dest_topic: str = Field(default="dest-events", description="Destination Kafka topic")
    group_id: str = "ouroboros-translator"
    poll_timeout_ms: int = 5000
    max_batch_size: int = 1000
    auto_offset_reset: str = "earliest"
    client_id: str = "translator"
    security_protocol: str = "PLAINTEXT"
    sasl_mechanism: str = "PLAIN"
    sasl_username: Optional[str] = None
    sasl_password: Optional[str] = None
    max_retries: int = 5
    retry_backoff_ms: int = 1000

settings = Settings()

consumer = None
producer = None
running = False
metrics = {"messages_transferred": 0, "errors": 0, "last_error": None, "start_time": None}

app = FastAPI(title="Kafka Event Translator", description=f"Reliable Kafka-to-Kafka message translation v{__version__}", version=__version__)

async def create_consumer():
    kwargs = {"bootstrap_servers": settings.source_bootstrap_servers.split(","), "group_id": settings.group_id,
              "client_id": settings.client_id, "enable_auto_commit": False, "auto_offset_reset": settings.auto_offset_reset}
    if settings.security_protocol in ("SASL_SSL", "SASL_PLAINTEXT"):
        kwargs["security_protocol"] = settings.security_protocol
        kwargs["sasl_mechanism"] = settings.sasl_mechanism
        if settings.sasl_username: kwargs["sasl_plain_username"] = settings.sasl_username
        if settings.sasl_password: kwargs["sasl_plain_password"] = settings.sasl_password
    return AIOKafkaConsumer(settings.source_topic, **kwargs)

async def create_producer():
    kwargs = {"bootstrap_servers": settings.dest_bootstrap_servers.split(","), "client_id": settings.client_id}
    if settings.security_protocol in ("SASL_SSL", "SASL_PLAINTEXT"):
        kwargs["security_protocol"] = settings.security_protocol
        kwargs["sasl_mechanism"] = settings.sasl_mechanism
        if settings.sasl_username: kwargs["sasl_plain_username"] = settings.sasl_username
        if settings.sasl_password: kwargs["sasl_plain_password"] = settings.sasl_password
    return AIOKafkaProducer(**kwargs)

async def start_services():
    global consumer, producer, running
    if running:
        logger.warning("Services already started")
        return
    try:
        logger.info("Starting Kafka services...")
        consumer = await create_consumer()
        producer = await create_producer()
        await consumer.start()
        logger.info(f"Consumer started — listening on {settings.source_topic}")
        await producer.start()
        logger.info(f"Producer started — sending to {settings.dest_topic}")
        running = True
        metrics["start_time"] = time.time()
        asyncio.create_task(translate_loop())
    except Exception as e:
        logger.error(f"Failed to start services: {e}")
        metrics["errors"] += 1
        metrics["last_error"] = str(e)
        raise

async def stop_services():
    global running
    if not running:
        return
    logger.info("Stopping Kafka services...")
    running = False
    await asyncio.sleep(0.5)
    if producer:
        try: await producer.flush()
        except Exception as e: logger.warning(f"Flush failed (non-fatal): {e}")
    if consumer:
        try: await consumer.commit()
        except Exception as e: logger.warning(f"Commit failed (non-fatal): {e}")
    if consumer: await consumer.stop()
    if producer: await producer.stop()
    logger.info("Producer stopped")

async def translate_loop():
    retries = 0
    while running:
        try:
            msgs = await consumer.getmany(timeout_ms=settings.poll_timeout_ms, max_records=settings.max_batch_size)
            batch_count = 0
            for tp, records in msgs.items():
                if not records: continue
                for record in records:
                    try:
                        await producer.send_and_wait(topic=settings.dest_topic, value=record.value,
                                                     key=record.key, headers=record.headers)
                        batch_count += 1
                    except Exception as retry_err:
                        await _handle_send_error(retry_err)
                if records: await consumer.commit()
            if batch_count > 0:
                metrics["messages_transferred"] += batch_count
                logger.info(f"Transferred {batch_count} messages")
            retries = 0
        except Exception as e:
            logger.error(f"Unexpected error in translate loop: {e}")
            metrics["errors"] += 1
            metrics["last_error"] = str(e)
            if running and retries < settings.max_retries:
                delay_ms = settings.retry_backoff_ms * (2 ** retries)
                logger.info(f"Retrying in {delay_ms}ms ({retries + 1}/{settings.max_retries})")
                await asyncio.sleep(delay_ms / 1000.0)
                retries += 1
            else:
                logger.critical("Max retries exceeded — shutting down")
                await stop_services()
                return

async def _handle_send_error(error):
    global running
    if not running: return
    logger.warning(f"Send error (will retry): {error}")
    retries = 0
    while running and retries < settings.max_retries:
        delay_ms = settings.retry_backoff_ms * (2 ** retries)
        logger.info(f"Retry {retries + 1}/{settings.max_retries} in {delay_ms}ms")
        await asyncio.sleep(delay_ms / 1000.0)
        retries += 1
    else:
        if running: logger.error(f"Message delivery failed after {settings.max_retries} retries")

@app.on_event("startup")
async def on_startup(): await start_services()

@app.on_event("shutdown")
async def on_shutdown(): await stop_services()

@app.get("/status")
async def status():
    return {"running": running, "version": __version__,
            "uptime_seconds": round(time.time() - metrics["start_time"], 2) if metrics["start_time"] else None,
            "messages_transferred": metrics["messages_transferred"], "errors": metrics["errors"],
            "last_error": metrics["last_error"], "source_topic": settings.source_topic,
            "dest_topic": settings.dest_topic, "source_bootstrap_servers": settings.source_bootstrap_servers,
            "dest_bootstrap_servers": settings.dest_bootstrap_servers}

@app.get("/metrics")
async def metrics_endpoint():
    return {"messages_transferred": metrics["messages_transferred"], "errors": metrics["errors"],
            "last_error": metrics["last_error"], "uptime_seconds": round(time.time() - metrics["start_time"], 2) if metrics["start_time"] else None,
            "running": running}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
