"""Redis sliding-window rate limiter (ZSET of timestamped hits per key).

Limits (from settings): chat 20/minute, uploads 10/hour, per user.
"""

import time
import uuid

from redis.asyncio import Redis


async def hit(redis: Redis, key: str, limit: int, window_seconds: int) -> bool:
    """Record one hit against ``key``; return True if the hit is within ``limit``.

    Sliding window: members older than the window are pruned, the current hit is
    added, and the remaining cardinality (including this hit) is compared to the
    limit. The key expires after one idle window.
    """
    now = time.time()
    member = f"{now:.6f}:{uuid.uuid4().hex}"
    pipe = redis.pipeline()
    pipe.zremrangebyscore(key, 0, now - window_seconds)
    pipe.zadd(key, {member: now})
    pipe.zcard(key)
    pipe.expire(key, window_seconds)
    results = await pipe.execute()
    count = int(results[2])
    return count <= limit


def chat_key(user_id: uuid.UUID) -> str:
    return f"ratelimit:chat:{user_id}"


def upload_key(user_id: uuid.UUID) -> str:
    return f"ratelimit:upload:{user_id}"
