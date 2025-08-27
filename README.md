# FastEx

FastEx — lightweight extensions and utilities for building FastAPI applications faster.

## Features

- **Rate Limiting**: High-performance rate limiting with multiple backend support
- **Logging**: Structured logging with Loguru integration
- **Backend Flexibility**: Redis, In-Memory, and Composite backends
- **High Availability**: Circuit breaker patterns and automatic failover
- **Customizable**: Extensible architecture with custom scripts and behaviors

## Installation

```bash
pip3 install git+https://github.com/HoPHNiDev/fastex.git
```

## Quick Start

### Basic Rate Limiting

```python
from fastapi import FastAPI, Depends
from fastex.limiter import configure_limiter, RateLimiter, RedisLimiterBackend
from fastex.limiter.backend.redis.schemas import RedisLimiterBackendConnectConfig

# Configure rate limiter
async def setup_limiter():
    backend = RedisLimiterBackend()
    await backend.connect(
        RedisLimiterBackendConnectConfig(
            redis_client="redis://localhost:6379/0"
        )
    )
    await configure_limiter(backend)

# Use in FastAPI
app = FastAPI()

@app.on_event("startup")
async def startup():
    await setup_limiter()

@app.get("/api/data")
async def get_data(
    rate_limiter: RateLimiter = Depends(RateLimiter(times=10, seconds=60))
):
    return {"data": "your data here"}
```

### Multiple Rate Limits

```python
@app.get("/api/sensitive")
async def sensitive_endpoint(
    # 5 requests per minute
    rate_limiter_1: RateLimiter = Depends(RateLimiter(times=5, minutes=1)),
    # 1 request per second
    rate_limiter_2: RateLimiter = Depends(RateLimiter(times=1, seconds=1))
):
    return {"message": "sensitive data"}
```

## Backend Types

### Redis Backend

High-performance rate limiting using Redis with Lua scripting.

```python
from fastex.limiter.backend.redis import RedisLimiterBackend
from fastex.limiter.backend.redis.schemas import RedisLimiterBackendConnectConfig

backend = RedisLimiterBackend()
await backend.connect(
    RedisLimiterBackendConnectConfig(
        redis_client="redis://localhost:6379/0",
        fallback_mode=FallbackMode.ALLOW  # Allow requests if Redis is down
    )
)
```

**Customization Options:**
- Custom Redis client configuration
- Fallback modes (ALLOW, RAISE, DENY)
- Custom Lua scripts for different algorithms
- Connection pooling and retry logic

### In-Memory Backend

Lightweight backend for development and single-instance applications.

```python
from fastex.limiter.backend.memory import InMemoryLimiterBackend
from fastex.limiter.backend.memory.schemas import MemoryLimiterBackendConnectConfig

backend = InMemoryLimiterBackend(
    cleanup_interval_seconds=300,  # Cleanup every 5 minutes
    max_keys=10000  # Memory protection limit
)
await backend.connect(
    MemoryLimiterBackendConnectConfig(
        cleanup_interval_seconds=300,
        max_keys=10000
    )
)
```

**Customization Options:**
- Configurable cleanup intervals
- Memory protection limits
- Thread-safe operations
- Automatic cleanup of expired entries

### Composite Backend

High-availability backend with automatic failover between primary and fallback.

```python
from fastex.limiter.backend.composite import CompositeLimiterBackend
from fastex.limiter.backend.composite.enums import SwitchingStrategy

# Primary: Redis, Fallback: In-Memory
composite = CompositeLimiterBackend(
    primary=RedisLimiterBackend(),
    fallback=InMemoryLimiterBackend(),
    strategy=SwitchingStrategy.CIRCUIT_BREAKER,
    failure_threshold=5,
    recovery_timeout_seconds=60
)

await composite.connect(
    primary_config=RedisLimiterBackendConnectConfig(
        redis_client="redis://localhost:6379/0"
    ),
    fallback_config=MemoryLimiterBackendConnectConfig()
)
```

**Switching Strategies:**

1. **Circuit Breaker** (Default): Automatically switches to fallback after consecutive failures
2. **Health Check**: Uses periodic health checks to determine backend availability
3. **Fail Fast**: Immediately tries fallback if primary is unavailable

**Customization Options:**
- Configurable failure thresholds
- Recovery timeouts
- Health check intervals
- Manual backend switching
- Comprehensive statistics and monitoring

## Advanced Usage

### Custom Rate Limit Keys

```python
async def custom_identifier(request: Request) -> str:
    # Use user ID for rate limiting
    user_id = request.headers.get("X-User-ID", "anonymous")
    return f"user:{user_id}"

@app.get("/api/user-data")
async def get_user_data(
    rate_limiter: RateLimiter = Depends(
        RateLimiter(
            times=10, 
            seconds=60,
            identifier=custom_identifier
        )
    )
):
    return {"user_data": "..."}
```

### Custom Callbacks

```python
async def custom_callback(request: Request, response: Response, result: RateLimitResult):
    # Log rate limit violations
    logger.warning(f"Rate limit exceeded: {result}")
    # Add custom headers
    response.headers["X-RateLimit-RetryAfter"] = str(result.retry_after_ms)

@app.get("/api/limited")
async def limited_endpoint(
    rate_limiter: RateLimiter = Depends(
        RateLimiter(
            times=5, 
            seconds=60,
            callback=custom_callback
        )
    )
):
    return {"message": "limited data"}
```

### Custom Lua Scripts

```python
from fastex.limiter.backend.redis.scripts import LuaScript

class CustomScript(LuaScript):
    def get_script(self) -> str:
        return """
        -- Your custom Lua script here
        local key = KEYS[1]
        local limit = tonumber(ARGV[1])
        local window = tonumber(ARGV[2])
        
        -- Custom rate limiting logic
        return {retry_after_ms, current_count}
        """
    
    def extra_params(self) -> list[str]:
        return []
    
    def parse_result(self, result) -> tuple[int, int]:
        return result[0], result[1]

# Use custom script
backend = RedisLimiterBackend()
await backend.connect(
    RedisLimiterBackendConnectConfig(
        redis_client="redis://localhost:6379/0",
        lua_script=CustomScript()
    )
)
```

## Configuration

### Environment Variables

```bash
# Redis configuration
REDIS_URL=redis://localhost:6379/0

# Rate limiter settings
FALLBACK_MODE=ALLOW
DEFAULT_TIMES=10
DEFAULT_WINDOW_SECONDS=60
```

### Settings Class

```python
from fastex.limiter.config import limiter_settings

# Access settings
print(limiter_settings.FALLBACK_MODE)
print(limiter_settings.DEFAULT_TIMES)
```

## Monitoring and Statistics

### Backend Statistics

```python
# Get composite backend stats
stats = composite.get_stats()
print(f"Primary requests: {stats['primary_requests']}")
print(f"Fallback requests: {stats['fallback_requests']}")
print(f"Circuit state: {stats['circuit_state']}")

# Get memory backend stats
memory_stats = memory_backend.get_stats()
print(f"Total keys: {memory_stats['total_keys']}")
print(f"Memory usage: {memory_stats['total_entries']}")
```

### Health Checks

```python
# Check backend health
if composite.is_connected():
    print("Composite backend is healthy")
    
# Force switch backends (for maintenance)
await composite.force_switch_to_primary()
await composite.force_switch_to_fallback()
```

## Error Handling

### Fallback Modes

```python
from fastex.limiter.backend.enums import FallbackMode

# ALLOW: Allow requests when backend is unavailable
# RAISE: Raise exceptions when backend is unavailable  
# DENY: Deny requests when backend is unavailable

config = RedisLimiterBackendConnectConfig(
    redis_client="redis://localhost:6379/0",
    fallback_mode=FallbackMode.ALLOW
)
```

### Exception Handling

```python
from fastex.limiter.backend.exceptions import LimiterBackendError

try:
    result = await backend.check_limit(key, config)
except LimiterBackendError as e:
    logger.error(f"Rate limiting error: {e}")
    # Handle gracefully
```

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=fastex

# Run specific backend tests
pytest tests/unit/limiter/backend/redis/
pytest tests/unit/limiter/backend/memory/
pytest tests/unit/limiter/backend/composite/
```

### Code Quality

```bash
# Format code
black fastex/

# Type checking
mypy fastex/

# Linting
ruff check fastex/
```

## Architecture

### Core Components

- **RateLimiter**: FastAPI dependency for rate limiting
- **LimiterBackend**: Abstract interface for backend implementations
- **CompositeLimiterBackend**: High-availability backend with failover
- **LuaScript**: Extensible Lua script system for Redis
- **FastexLogger**: Structured logging wrapper

### Backend Hierarchy

```
LimiterBackend (Interface)
├── BaseLimiterBackend (Abstract)
├── RedisLimiterBackend
├── InMemoryLimiterBackend
└── CompositeLimiterBackend
    ├── Primary Backend
    └── Fallback Backend
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Run the test suite
6. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.
