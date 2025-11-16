import asyncio
from backend.models.base import AsyncSessionLocal
from backend.models.logs import ApplicationLog
from sqlalchemy import select

async def check_logs():
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ApplicationLog)
            .order_by(ApplicationLog.timestamp.desc())
            .limit(20)
        )
        logs = result.scalars().all()
        print(f'Found {len(logs)} application logs in database')
        for log in logs:
            print(f'  [{log.timestamp}] {log.level:8s} - {log.logger:30s}: {log.message[:80]}')

asyncio.run(check_logs())
