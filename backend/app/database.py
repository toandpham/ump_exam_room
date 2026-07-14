"""Async SQLAlchemy engine and session management."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
    # AD-69/75: tổng kết nối DB phải nhỏ để Postgres KHÔNG thrash (sự cố 29-06:
    # 4×(40+60)=400 kết nối làm Postgres sụp khi đông). Hiện tại: 6 uvicorn worker
    # × (15+10) = TỐI ĐA 150 kết nối / max_connections=600. Đổi số worker trong
    # docker-compose.yml thì tính lại công thức này.
    pool_size=15,
    max_overflow=10,
    pool_timeout=30,
    # AD-75: 1 query kẹt (lock/plan xấu) không được giữ connection vô hạn —
    # đủ 25 conn kẹt là worker đó tê liệt. asyncpg cắt query sau 30s.
    connect_args={"command_timeout": 30},
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a transactional async session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
