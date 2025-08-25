import time
from pathlib import Path
from typing import Any

from fastex.limiter.backend.redis.scripts.interface import LuaScript


class FixedWindowScript(LuaScript):
    """Fixed window - simple but less precise limiting."""

    def get_script(self) -> str:
        return FIXED_WINDOW_SCRIPT

    def extra_params(self) -> list[Any]:
        return []

    def parse_result(self, result: list[Any]) -> tuple[int, int]:
        return int(result[0]), int(result[1])


class SlidingWindowScript(LuaScript):
    """Sliding window - more precise limiting using sorted sets."""

    def get_script(self) -> str:
        return SLIDING_WINDOW_SCRIPT

    def extra_params(self) -> list[Any]:
        return [int(time.time() * 1000)]

    def parse_result(self, result: list[Any]) -> tuple[int, int]:
        return int(result[0]), int(result[1])


class FileBasedScript(LuaScript):
    """Load Lua script from an external file."""

    def __init__(self, script_path: str | Path):
        self.script_path = Path(script_path)

    def get_script(self) -> str:
        return self.script_path.read_text()

    def extra_params(self) -> list[Any]:
        return []

    def parse_result(self, result: list[Any]) -> tuple[int, int]:
        return int(result[0]), int(result[1])


FIXED_WINDOW_SCRIPT = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])

local current = tonumber(redis.call('GET', key) or "0")

if current == 0 then
    redis.call('SET', key, 1, 'PX', window_ms)
    return {0, 1}
elseif current < limit then
    current = redis.call('INCR', key)
    return {0, current}
else
    local ttl = redis.call('PTTL', key)
    return {ttl, current}
end
"""

SLIDING_WINDOW_SCRIPT = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

redis.call('ZREMRANGEBYSCORE', key, 0, now - window_ms)

local current = redis.call('ZCARD', key)

if current < limit then
    redis.call('ZADD', key, now, now)
    redis.call('EXPIRE', key, math.ceil(window_ms / 1000))
    return {0, current + 1}
else
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    if #oldest > 0 then
        local reset_time = oldest[2] + window_ms - now
        return {reset_time, current}
    else
        return {window_ms, current}
    end
end
"""
