#!/usr/bin/env python3
"""Start PedalMind backend: init DB tables then launch uvicorn."""

import asyncio
import logging
import sys
import os

# Add project root to path so ai_engine and garmin_sync are importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("pedalmind")


async def init():
    from app.core.init_db import create_tables
    await create_tables()


def main():
    import uvicorn

    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    asyncio.run(init())
    logger.info("Starting PedalMind API on http://localhost:8000")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    main()
