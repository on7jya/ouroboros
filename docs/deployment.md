# Production Deployment Guide

## Overview

Ouroboros Kafka Event Translator is production-ready as of v6.7.0.

This guide covers deployment to Kubernetes, Docker Swarm, and bare-metal servers.

## Architecture Recap

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│   Source    │────▶│ Ouroboros    │────▶│ Destination │
│  Kafka      │    │ Translator   │    │   Kafka     │
│  Cluster    │    │ Service      │    |  Cluster    |
└─────────────┘    └──────────────┘    └─────────────┘
                        │
                        ▼
                ┌──────────────┐
                │ Web Dashboard  │ (v6.5.0)
                └──────────────┘
                        │
                        ▼
              ┌─────────────────┐
              │ Integration     │ (v6.6.0)
              │ Tests (Mock)    │
              └─────────────────┘
```

## Prerequisites

- Python 3.10+  
- Kafka clusters (source and destination)  
- Docker 24+ (for containerized deployment)  
- Kubernetes cluster with Helm (optional, v1.25+)  

## Deployment Options

### Option 1: Bare Metal / VM

#### Install Dependencies

```bash
pip install fastapi uvicorn python-dotenv kafkamock==0.2.0
```

#### Configuration

Create `.env`:

```bash
KAFKA_SOURCE_BOOTSTRAP=your-source-kafka:9092
KAFKA_DEST_BOOTSTRAP=your-dest-kafka:9092
API_HOST=0.0.0.0
API_PORT=8000
LOG_LEVEL=INFO
```

#### Run

```bash
uvicorn ouroboros.app:app --host $API_HOST --port $API_PORT
```

### Option 2: Docker

#### Build

```bash
docker build -t ouroboros-translator:v6.7.0 .
```

#### Run

```bash
docker run -d \
  --name ouroboros \
  -p 8000:8000 \
  --env-file .env \
  ouroboros-translator:v6.7.0
```

### Option 3: Kubernetes

#### Create Namespace

```bash
kubectl create namespace ouroboros
```

#### Apply Deployment (Helm)

```yaml
# values.yaml
replicaCount: 2

image:
  repository: ouroboros-translator
  tag: v6.7.0

kafka:
  sourceBootstrap: your-source-kafka:9092
  destBootstrap: your-dest-kafka:9092

service:
  type: ClusterIP
  port: 8000

resources:
  limits:
    cpu: 500m
    memory: 256Mi
  requests:
    cpu: 100m
    memory: 128Mi
```

#### Deploy

```bash
helm install ouroboros ./ouroboros-helm -n ouroboros --create-namespace
```

## Monitoring

### Web Dashboard (v6.5.0)

Access at `http://<host>:8000/dashboard`

Features:
- Real-time metrics (messages/sec, latency)
- Error counters
- Health status

### CLI Viewer (v6.6.0)

```bash
ouroboros-cli status
```

Output includes:
- Connection health  
- Message throughput  
- Error rates  

## Scaling

### Horizontal Scaling

Increase replicas (Docker/K8s) or run multiple instances behind load balancer.

### Vertical Scaling

Adjust CPU/memory limits based on throughput requirements.

## Health Check

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{
  "status": "healthy",
  "version": "6.7.0",
  "kafka_source": "connected",
  "kafka_dest": "connected"
}
```

## Troubleshooting

### Connection Issues

Verify Kafka connectivity:

```bash
kafkacat -L -b your-kafka:9092
```

### Memory Issues

Increase heap or reduce batch size in config.

## Security

- Use secrets management (K8s Secrets, Vault)  
- Enable TLS for Kafka connections  
- Restrict API access with auth middleware  

## Upgrading

1. Verify test suite passes (`pytest tests/`)  
2. Update version in `VERSION` and `docs/deployment.md`  
3. Deploy new image/tag  
4. Monitor health dashboard for 15 minutes  

## Support

- GitHub Issues: `/content/ouroboros_repo/issues`  
- Documentation: `docs/` directory  
- Changelog: `README.md`  

---

**Remember**: This is a self-creating agent. Use with curiosity and care.
