import asyncio
import os
from fastapi import FastAPI, HTTPException
from pydantic_settings import BaseSettings
from pydantic import Field
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

class Settings(BaseSettings):
    source_bootstrap_servers: str = Field(..., env='SOURCE_BOOTSTRAP_SERVERS')
    dest_bootstrap_servers: str = Field(..., env='DEST_BOOTSTRAP_SERVERS')
    source_topic: str = Field(..., env='SOURCE_TOPIC')
    dest_topic: str = Field(..., env='DEST_TOPIC')
    group_id: str = Field('ouroboros-translator', env='GROUP_ID')
    poll_timeout_ms: int = 5000
    max_batch_size: int = 1000
    client_id: str = 'translator'

settings = Settings()
app = FastAPI(title="Kafka Event Translator")

consumer: AIOKafkaConsumer | None = None
producer: AIOKafkaProducer | None = None
running = False

async def start_consumer_producer():
    global consumer, producer, running
    if running:
        return
    consumer = AIOKafkaConsumer(
        settings.source_topic,
        bootstrap_servers=settings.source_bootstrap_servers.split(','),
        group_id=settings.group_id,
        client_id=settings.client_id,
        enable_auto_commit=False,
        auto_offset_reset='earliest'
    )
    producer = AIOKafkaProducer(
        bootstrap_servers=settings.dest_bootstrap_servers.split(','),
        client_id=settings.client_id
    )
    await consumer.start()
    await producer.start()
    running = True
    asyncio.create_task(_translate_loop())

async def _translate_loop():
    try:
        while running:
            msgs = await consumer.getmany(timeout_ms=settings.poll_timeout_ms, max_records=settings.max_batch_size)
            for tp, records in msgs.items():
                for record in records:
                    await producer.send_and_wait(settings.dest_topic, record.value, key=record.key, headers=record.headers)
            if records:
                await consumer.commit()
    except Exception as e:
        # Log and stop
        print(f"Translator loop error: {e}")
        await shutdown()

@app.on_event("startup")
async def on_startup():
    await start_consumer_producer()

@app.on_event("shutdown")
async def on_shutdown():
    await shutdown()

async def shutdown():
    global running, consumer, producer
    running = False
    if consumer:
        await consumer.stop()
    if producer:
        await producer.stop()

@app.get("/status")
async def status():
    return {
        "running": running,
        "source_topic": settings.source_topic,
        "dest_topic": settings.dest_topic,
        "source_bootstrap_servers": settings.source_bootstrap_servers,
        "dest_bootstrap_servers": settings.dest_bootstrap_servers,
    }
