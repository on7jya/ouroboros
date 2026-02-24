# FastAPI based Kafka Event Translator Service
"""
This service reads messages from a source Kafka topic and forwards them to a destination Kafka topic.
It supports both same‑cluster and cross‑cluster scenarios.
Configuration is provided via environment variables.
"""

import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseSettings, Field
from typing import Optional
import asyncio

# We use aiokafka for async operation
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

app = FastAPI()

class Settings(BaseSettings):
    # Source Kafka configuration
    src_bootstrap_servers: str = Field(..., env="SRC_BOOTSTRAP_SERVERS")
    src_topic: str = Field(..., env="SRC_TOPIC")
    src_group_id: str = Field("translator-group", env="SRC_GROUP_ID")
    # Destination Kafka configuration
    dst_bootstrap_servers: str = Field(..., env="DST_BOOTSTRAP_SERVERS")
    dst_topic: str = Field(..., env="DST_TOPIC")
    # Optional: limit processing rate
    max_batch_size: int = Field(100, env="MAX_BATCH_SIZE")
    poll_timeout_ms: int = Field(500, env="POLL_TIMEOUT_MS")

settings = Settings()

consumer: Optional[AIOKafkaConsumer] = None
producer: Optional[AIOKafkaProducer] = None
running_task: Optional[asyncio.Task] = None

async def start_kafka_clients():
    global consumer, producer
    consumer = AIOKafkaConsumer(
        settings.src_topic,
        bootstrap_servers=settings.src_bootstrap_servers.split(","),
        group_id=settings.src_group_id,
        enable_auto_commit=True,
        auto_offset_reset="earliest",
    )
    producer = AIOKafkaProducer(bootstrap_servers=settings.dst_bootstrap_servers.split(","))
    await consumer.start()
    await producer.start()

async def stop_kafka_clients():
    global consumer, producer
    if consumer:
        await consumer.stop()
    if producer:
        await producer.stop()

async def translate_loop():
    try:
        async for msg in consumer:
            # Forward the message value (bytes) and key unchanged
            await producer.send_and_wait(settings.dst_topic, value=msg.value, key=msg.key)
    except Exception as e:
        # Log and stop loop – FastAPI will expose the error via /status
        raise e

@app.on_event("startup")
async def startup_event():
    await start_kafka_clients()
    global running_task
    running_task = asyncio.create_task(translate_loop())

@app.on_event("shutdown")
async def shutdown_event():
    if running_task:
        running_task.cancel()
        try:
            await running_task
        except asyncio.CancelledError:
            pass
    await stop_kafka_clients()

@app.get("/status")
async def status():
    return {
        "source": {
            "bootstrap_servers": settings.src_bootstrap_servers,
            "topic": settings.src_topic,
        },
        "destination": {
            "bootstrap_servers": settings.dst_bootstrap_servers,
            "topic": settings.dst_topic,
        },
        "running": not running_task.done() if running_task else False,
    }

# No additional HTTP endpoints – the service works as a background translator.
