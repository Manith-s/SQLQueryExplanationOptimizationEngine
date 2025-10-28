# Changelog

All notable changes to the Query Explanation & Optimization Engine will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2024-10-17

### Production Release

First production-ready release with comprehensive security, performance optimization, and complete documentation.

### Added

#### Performance Optimization (Task 8)
- Comprehensive caching layer with TTL and LRU eviction
- Performance metrics tracking (query times, cache hit rates)
- Optimized connection pooling
- Cache statistics endpoint

#### Security Hardening (Task 9)
- SQL injection prevention with pattern matching
- Request size validation and limits
- Security headers middleware
- Request logging with sanitization
- Enhanced CORS configuration

#### Documentation & Deployment (Tasks 5-7)
- Production configuration module
- Multi-stage Docker builds
- Automated deployment script
- Complete API documentation
- Production deployment guide

#### Testing
- 94 integration tests passing
- Authentication integration tests
- Rate limiting tests
- Production readiness tests

### Security
- Input validation for all endpoints
- Dangerous SQL pattern detection
- Log sanitization
- Error message sanitization
- Security headers (CSP, X-Frame-Options, etc.)

### Performance
- Multi-layer caching (EXPLAIN, NL, optimize, schema)
- Performance metrics tracking
- Optimized query execution

---

## [0.7.0] - 2024

### Added
- Bearer token authentication
- IP-based rate limiting
- Workload analysis with pattern detection
- Query grouping by similarity
- Workload-level recommendations
- In-memory caching

---

## [0.6.0] - 2024

### Added
- HypoPG what-if analysis
- Cost-based index ranking
- Prometheus metrics endpoint

---

## [0.5.0] - 2024

### Added
- Query optimization engine
- Deterministic rewrite rules
- Multi-column index advisor

---

## [0.4.0] - 2024

### Added
- Natural language explanations
- Ollama integration

---

## [0.3.0] - 2024

### Added
- PostgreSQL integration
- EXPLAIN/ANALYZE support
- Schema inspection

---

## [0.2.0] - 2024

### Added
- SQL parsing with sqlglot
- Static analysis and linting

---

## [0.1.0] - 2024

### Added
- FastAPI application setup
- Basic API endpoints
- Docker configuration
