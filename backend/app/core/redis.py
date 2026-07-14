"""Shared async Redis client.

Used for the JWT blacklist (logout), and later for exam payloads, sessions,
and pub/sub. Connection pooling is handled by redis-py.

AD-75: bắt buộc có socket timeout — Redis TREO (VM nghẽn RAM, sự cố 13-07) mà
không timeout thì blacklist/device_lock trên đường nóng treo vô hạn, dồn nghẹt
cả 6 worker. Chết hẳn (refused) thì 500 sạch — chấp nhận; treo thì KHÔNG.

Pub/sub dùng CLIENT RIÊNG không socket_timeout: listen() chờ message hàng phút
là bình thường, đặt socket_timeout chung sẽ làm nó tự đứt mỗi khi kênh im ắng.
Độ bền của subscriber do vòng retry ở websocket/manager.py lo.
"""

from __future__ import annotations

from redis.asyncio import Redis, from_url

from app.config import settings

redis_client: Redis = from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=2,
    socket_timeout=5,
    health_check_interval=30,
)

redis_pubsub_client: Redis = from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=2,
)
