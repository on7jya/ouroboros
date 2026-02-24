"""
FastAPI service that translates (copies) messages from a source Kafka topic to a destination Kafka topic.
It supports both same‑cluster and cross‑cluster scenarios via configurable bootstrap servers.
The core logic runs as an asynchronous background task started on FastAPI startup and stopped on shutdown.
A simple `/status` endpoint reports the current configuration and health.
"""

import asyncio
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, validator

# The kafka-python library is used for simplicity. It works in a thread‑based manner,
# which fits well with FastAPI's lifecycle events.
from kafka import KafkaConsumer, KafkaProducer

app = FastAPI(title="Kafka Event Translator")


class KafkaConfig(BaseModel):
    bootstrap_servers: List[str] = Field(..., description="List of host:port for the Kafka cluster")
    source_topic: str = Field(..., description="Topic to consume from")
    destination_topic: str = Field(..., description="Topic to produce to")
    group_id: Optional[str] = Field(None, description="Consumer group id; defaults to 'kafka-translator'")

    @validator("bootstrap_servers", each_item=True)
    def _host_port(cls, v):  # simple validation
        if ":" not in v:
            raise ValueError("must be host:port")
        return v

# Global state – the background task and its configuration.
translator_task: Optional[asyncio.Task] = None
current_config: Optional[KafkaConfig] = None


def _run_translator(cfg: KafkaConfig):
    """Blocking function that runs in a dedicated thread.
    It creates a consumer, reads messages and forwards them to the destination topic.
    The loop stops when the surrounding asyncio event is cancelled.
    """
    consumer = KafkaConsumer(
        cfg.source_topic,
        bootstrap_servers=cfg.bootstrap_servers,
        group_id=cfg.group_id or "kafka-translator",
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        value_deserializer=lambda v: v,  # keep raw bytes
    )
    producer = KafkaProducer(
        bootstrap_servers=cfg.bootstrap_servers,
        value_serializer=lambda v: v,
    )
    try:
        for msg in consumer:
            # Forward the exact payload (key, headers, timestamp) unchanged.
            producer.send(
                cfg.destination_topic,
                key=msg.key,
                value=msg.value,
                headers=msg.headers,
                timestamp_ms=msg.timestamp,
            )
            producer.flush()
    finally:
        consumer.close()
        producer.close()


async def _translator_wrapper(cfg: KafkaConfig):
    loop = asyncio.get_running_loop()
    # Run the blocking translator in a thread pool to avoid blocking the event loop.
    await loop.run_in_executor(None, _run_translator, cfg)


@app.post("/configure", summary="Set or update translator configuration")
async def configure(cfg: KafkaConfig):
    global translator_task, current_config
    # Cancel any existing background task first.
    if translator_task and not translator_task.done():
        translator_task.cancel()
        try:
            await translator_task
        except asyncio.CancelledError:
            pass
    # Store new config and start a fresh background task.
    current_config = cfg
    translator_task = asyncio.create_task(_translator_wrapper(cfg))
    return {"status": "configured", "config": cfg.dict()}


@app.get("/status", summary="Health check and configuration dump")
async def status():
    if not current_config:
        raise HTTPException(status_code=404, detail="Translator not configured yet")
    running = translator_task is not None and not translator_task.done()
    return {
        "running": running,
        "config": current_config.dict(),
    }


@app.on_event("shutdown")
async def shutdown_event():
    global translator_task
    if translator_task and not translator_task.done():
        translator_task.cancel()
        try:
            await translator_task
        except asyncio.CancelledError:
            pass
