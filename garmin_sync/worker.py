import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("garmin_sync")
POLL_INTERVAL_SEC = 1800

def parse_fit_file(fit_path: str, ftp: int, max_hr: int) -> dict:
    """Parse .FIT file into RideData contract dict.
    Key formulas:
      NP = 4th root of mean of (30s rolling avg power)^4
      IF = NP / FTP
      TSS = (duration_sec * NP * IF) / (FTP * 3600) * 100
      Decoupling = ((HR2/P2) - (HR1/P1)) / (HR1/P1) * 100
    Coggan zones (% FTP): Z1<55, Z2 55-75, Z3 76-90, Z4 91-105, Z5 106-120, Z6 121-150, Z7>150
    """
    # TODO: port logic from ~/garmin-analyzer/garmin_auto.py
    logger.warning("parse_fit_file not yet implemented")
    return {}

async def sync_user(user_id: str, garmin_token: str, garmin_refresh: str) -> list[dict]:
    # TODO: implement Garmin API sync
    logger.info(f"Syncing user {user_id} — not yet implemented")
    return []

async def worker_loop():
    logger.info("Garmin sync worker started")
    while True:
        try:
            logger.info("Poll cycle — no users yet")
        except Exception as e:
            logger.error(f"Sync error: {e}")
        await asyncio.sleep(POLL_INTERVAL_SEC)

if __name__ == "__main__":
    asyncio.run(worker_loop())
