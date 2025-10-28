# Production Deployment Guide

Complete guide for deploying QEO (Query Explanation & Optimization Engine) to production.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Environment Configuration](#environment-configuration)
- [Deployment Methods](#deployment-methods)
- [Security Configuration](#security-configuration)
- [Performance Tuning](#performance-tuning)
- [Monitoring](#monitoring)
- [Backup and Recovery](#backup-and-recovery)
- [Troubleshooting](#troubleshooting)

## Prerequisites

### System Requirements

- **Operating System**: Linux (Ubuntu 20.04+ recommended), macOS, or Windows with WSL2
- **Docker**: 20.10+ with Docker Compose 2.0+
- **Memory**: Minimum 2GB RAM (4GB+ recommended)
- **CPU**: 2+ cores recommended
- **Disk**: 10GB+ available space
- **Network**: Ports 8000 (API) and 5432/5433 (PostgreSQL) available

### Software Dependencies

- Git
- Docker Desktop (includes Docker Compose)
- Optional: curl for health checks
- Optional: gh CLI for GitHub operations

## Environment Configuration

### 1. Create Production Environment File

```bash
# Copy example environment file
cp .env.example .env
```

### 2. Configure Required Variables

Edit `.env` with production values:

```bash
# Database Configuration
DB_URL=postgresql+psycopg2://postgres:STRONG_PASSWORD_HERE@db:5432/queryexpnopt

# Security
AUTH_ENABLED=true
API_KEY=GENERATE_STRONG_API_KEY_HERE  # Use openssl rand -base64 32
ALLOWED_HOSTS=your-domain.com,api.your-domain.com
CORS_ORIGINS=https://your-frontend.com,https://app.your-domain.com

# Performance
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
WORKER_COUNT=4
REQUEST_TIMEOUT_SECONDS=30

# What-If Analysis (HypoPG)
WHATIF_ENABLED=true
WHATIF_MAX_TRIALS=8
WHATIF_MIN_COST_REDUCTION_PCT=5

# Optimization Settings
OPT_MIN_ROWS_FOR_INDEX=10000
OPT_MAX_INDEX_COLS=3
OPT_TOP_K=10
OPT_TIMEOUT_MS_DEFAULT=10000

# Logging
LOG_LEVEL=INFO
LOG_JSON=true  # Enable structured JSON logging for production

# Monitoring (Optional)
METRICS_ENABLED=true
SENTRY_DSN=https://your-sentry-dsn@sentry.io/project-id

# LLM Provider
LLM_PROVIDER=dummy  # or 'ollama' if you have Ollama running
```

### 3. Generate Secure API Key

```bash
# Linux/macOS
openssl rand -base64 32

# Windows PowerShell
$bytes = New-Object byte[] 32
[Security.Cryptography.RNGCryptoServiceProvider]::Create().GetBytes($bytes)
[Convert]::ToBase64String($bytes)
```

## Deployment Methods

### Method 1: Docker Compose (Recommended)

#### Quick Start

```bash
# Navigate to project directory
cd queryexpnopt

# Build and start services
docker compose up -d --build

# Check service status
docker compose ps

# View logs
docker compose logs -f api
```

#### Using Deployment Script

```bash
# Make script executable (Linux/macOS)
chmod +x deploy.sh

# Run deployment
./deploy.sh
```

The deployment script will:
1. ✅ Verify `.env` configuration
2. ✅ Build Docker images
3. ✅ Start database with health checks
4. ✅ Verify HypoPG extension
5. ✅ Start API service
6. ✅ Run smoke tests
7. ✅ Display service status

#### Production Docker Compose Configuration

The included `docker-compose.yml` has production-ready settings:

```yaml
api:
  restart: unless-stopped  # Auto-restart on failure
  deploy:
    resources:
      limits:
        cpus: '2.0'
        memory: 2G
      reservations:
        cpus: '0.5'
        memory: 512M
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
    interval: 10s
    timeout: 3s
    retries: 30
```

### Method 2: Standalone Docker

#### Build Images

```bash
# Build database image
docker build -f docker/db.Dockerfile -t qeo-db:latest .

# Build API image
docker build -t qeo-api:latest .
```

#### Run Containers

```bash
# Create network
docker network create qeo-network

# Start database
docker run -d \
  --name qeo-db \
  --network qeo-network \
  -e POSTGRES_PASSWORD=your_password \
  -e POSTGRES_DB=queryexpnopt \
  -p 5433:5432 \
  -v qeo-postgres-data:/var/lib/postgresql/data \
  qeo-db:latest

# Wait for database to be ready
sleep 10

# Start API
docker run -d \
  --name qeo-api \
  --network qeo-network \
  --env-file .env \
  -e DB_URL=postgresql+psycopg2://postgres:your_password@qeo-db:5432/queryexpnopt \
  -p 8000:8000 \
  qeo-api:latest
```

### Method 3: Kubernetes (Advanced)

For Kubernetes deployment, create the following manifests:

#### ConfigMap (configmap.yaml)

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: qeo-config
data:
  WHATIF_ENABLED: "true"
  METRICS_ENABLED: "true"
  LOG_LEVEL: "INFO"
  WORKER_COUNT: "4"
```

#### Secret (secret.yaml)

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: qeo-secrets
type: Opaque
stringData:
  API_KEY: your-api-key-here
  DB_URL: postgresql+psycopg2://postgres:password@postgres-service:5432/queryexpnopt
```

#### Deployment (deployment.yaml)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: qeo-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: qeo-api
  template:
    metadata:
      labels:
        app: qeo-api
    spec:
      containers:
      - name: qeo-api
        image: qeo-api:latest
        ports:
        - containerPort: 8000
        envFrom:
        - configMapRef:
            name: qeo-config
        - secretRef:
            name: qeo-secrets
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
```

## Security Configuration

### 1. Enable Authentication

```bash
# In .env
AUTH_ENABLED=true
API_KEY=your-secure-key-here
```

### 2. Configure CORS

```bash
# Restrict to your domains
CORS_ORIGINS=https://your-frontend.com,https://app.your-domain.com

# Or allow all (not recommended for production)
CORS_ORIGINS=*
```

### 3. Enable Security Headers

Security headers are automatically enabled in production. Configure in `.env`:

```bash
SECURE_HEADERS=true
```

This enables:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Strict-Transport-Security: max-age=31536000`
- `Content-Security-Policy: default-src 'self'`

### 4. Database Security

```bash
# Use strong password
POSTGRES_PASSWORD=use_strong_password_here

# Restrict network access
# Only allow API container to connect (via Docker network)
# Don't expose port 5432 externally in production
```

### 5. Rate Limiting

Rate limits are automatically enforced:
- `/api/v1/optimize`: 10 requests/minute per IP
- Other endpoints: 100 requests/minute per IP

Adjust if needed by modifying `src/app/routers/optimize.py`.

## Performance Tuning

### Database Pool Configuration

```bash
# In .env
DB_POOL_SIZE=10          # Number of persistent connections
DB_MAX_OVERFLOW=20       # Additional connections on demand
```

### Worker Configuration

```bash
# Number of Uvicorn workers (CPU cores × 2-4)
WORKER_COUNT=4

# Or set in docker-compose.yml:
command: uvicorn app.main:app --workers 4 --host 0.0.0.0
```

### Resource Limits

Adjust in `docker-compose.yml`:

```yaml
deploy:
  resources:
    limits:
      cpus: '4.0'      # Increase for high traffic
      memory: 4G       # Increase if needed
    reservations:
      cpus: '1.0'
      memory: 1G
```

### Query Timeouts

```bash
# Default timeout for EXPLAIN operations
OPT_TIMEOUT_MS_DEFAULT=10000  # 10 seconds

# Request timeout
REQUEST_TIMEOUT_SECONDS=30
```

### Caching

Workload analysis results are cached for 5 minutes by default. Adjust in `src/app/routers/workload.py`:

```python
_CACHE_TTL_SECONDS = 300  # Modify as needed
```

## Monitoring

### Health Checks

```bash
# Basic health check
curl http://localhost:8000/health

# Expected response
{
  "status": "healthy",
  "database": "connected",
  "hypopg": "available"
}
```

### Prometheus Metrics

Enable metrics in `.env`:

```bash
METRICS_ENABLED=true
```

Access metrics at:
```
http://localhost:8000/metrics
```

Key metrics:
- `qeo_requests_total`: Total requests by route and status
- `qeo_request_latency_seconds`: Request latency histogram
- `qeo_db_explain_seconds`: Database EXPLAIN query duration
- `qeo_whatif_trials_total`: HypoPG trial count
- `qeo_whatif_trial_seconds`: HypoPG trial duration

### Sentry Integration

For error tracking, configure Sentry:

```bash
SENTRY_DSN=https://your-key@sentry.io/project-id
```

### Log Aggregation

Enable structured JSON logging:

```bash
LOG_JSON=true
LOG_LEVEL=INFO
```

View logs:

```bash
# Real-time logs
docker compose logs -f api

# Last 100 lines
docker compose logs --tail=100 api

# Filter by level
docker compose logs api | grep ERROR
```

## Backup and Recovery

### Database Backup

```bash
# Create backup
docker compose exec -T db pg_dump -U postgres queryexpnopt > backup_$(date +%Y%m%d).sql

# Automated daily backup (cron)
0 2 * * * cd /path/to/queryexpnopt && docker compose exec -T db pg_dump -U postgres queryexpnopt > /backups/qeo_$(date +\%Y\%m\%d).sql
```

### Database Restore

```bash
# Stop API
docker compose stop api

# Restore from backup
cat backup_20231215.sql | docker compose exec -T db psql -U postgres queryexpnopt

# Restart API
docker compose start api
```

### Volume Backup

```bash
# Backup PostgreSQL data volume
docker run --rm \
  -v queryexpnopt_postgres_data:/data \
  -v $(pwd):/backup \
  busybox tar czf /backup/postgres_data_backup.tar.gz /data
```

## Troubleshooting

### Service Won't Start

```bash
# Check logs
docker compose logs api
docker compose logs db

# Check environment variables
docker compose config

# Verify port availability
netstat -tuln | grep 8000
```

### Database Connection Issues

```bash
# Test database connectivity
docker compose exec api sh -c 'psql $DB_URL -c "SELECT 1"'

# Check database is running
docker compose ps db

# Restart database
docker compose restart db
```

### HypoPG Not Available

```bash
# Check extension installed
docker compose exec db psql -U postgres -d queryexpnopt \
  -c "SELECT * FROM pg_extension WHERE extname='hypopg';"

# Install extension manually
docker compose exec db psql -U postgres -d queryexpnopt \
  -c "CREATE EXTENSION IF NOT EXISTS hypopg;"
```

### Performance Issues

```bash
# Check resource usage
docker stats

# Check active connections
docker compose exec db psql -U postgres -d queryexpnopt \
  -c "SELECT count(*) FROM pg_stat_activity;"

# Check slow queries
docker compose exec db psql -U postgres -d queryexpnopt \
  -c "SELECT query, calls, total_time/calls as avg_time FROM pg_stat_statements ORDER BY avg_time DESC LIMIT 10;"
```

### Rate Limit Issues

If legitimate traffic is being rate limited:

1. Adjust limits in `src/app/main.py` (default) and `src/app/routers/optimize.py` (optimize endpoint)
2. Implement Redis-based rate limiting for distributed deployments
3. Use API keys to identify trusted clients

### Memory Issues

```bash
# Increase memory limit in docker-compose.yml
deploy:
  resources:
    limits:
      memory: 4G  # Increase from 2G

# Or reduce pool size
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10
```

## Production Checklist

Before deploying to production, verify:

- [ ] `.env` file configured with production values
- [ ] Strong passwords and API keys generated
- [ ] `AUTH_ENABLED=true` for security
- [ ] `CORS_ORIGINS` restricted to your domains
- [ ] `LOG_LEVEL=INFO` or `WARNING` (not `DEBUG`)
- [ ] `METRICS_ENABLED=true` for monitoring
- [ ] Database backup strategy in place
- [ ] Health check endpoint accessible
- [ ] SSL/TLS configured (via reverse proxy)
- [ ] Firewall rules configured
- [ ] Resource limits appropriate for traffic
- [ ] Monitoring and alerting configured
- [ ] Documentation shared with team

## Scaling

### Horizontal Scaling

For high traffic, run multiple API instances:

```yaml
# docker-compose.yml
api:
  deploy:
    replicas: 3  # Run 3 instances
```

Or use Kubernetes with multiple replicas.

### Load Balancing

Use nginx or cloud load balancer:

```nginx
upstream qeo_api {
    server api1:8000;
    server api2:8000;
    server api3:8000;
}

server {
    listen 80;
    location / {
        proxy_pass http://qeo_api;
    }
}
```

### Database Scaling

For read-heavy workloads:
- Use PostgreSQL read replicas
- Point read-only queries to replicas
- Keep write operations on primary

## Security Best Practices

1. **Never commit `.env` files** - Use `.env.example` as template
2. **Rotate API keys regularly** - Every 90 days recommended
3. **Use HTTPS in production** - Configure reverse proxy with SSL
4. **Limit database exposure** - Don't expose port 5432 externally
5. **Monitor authentication failures** - Set up alerts for 403 responses
6. **Keep dependencies updated** - Run `pip install -U` periodically
7. **Use secrets management** - AWS Secrets Manager, HashiCorp Vault, etc.
8. **Enable audit logging** - Track all API key usage
9. **Implement IP allowlisting** - For highly sensitive deployments
10. **Regular security scans** - Use tools like Trivy for container scanning

## Next Steps

- Review [API.md](API.md) for complete API documentation
- See [README.md](../README.md) for development setup
- Join our community for support and updates

## Support

For production deployment assistance:
- Open an issue on GitHub
- Check existing documentation
- Review logs and metrics for insights
