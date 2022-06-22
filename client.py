import aiohttp
import asyncio
import yaml
import os
import logging
from datetime import datetime, timedelta
import random

proxy = "http://localhost:8888"
if "DEBUG" in os.environ:
    logging.basicConfig(
        level=logging.DEBUG, format="%(levelname)8s %(asctime)s %(name)15s| %(message)s"
    )
else:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)8s %(asctime)s %(name)15s| %(message)s"
    )


async def fetch(session, url):
    async with session.get(url, proxy=proxy) as resp:
        response = await resp.json()


async def worker(session):
    url = "http://mock_api/kr/lol/summoner/v4/summoners/by-name/Doctress"
    await asyncio.sleep(random.random() * 10)
    while True:
        async with session.get(url, proxy=proxy) as resp:
            try:
                response = await resp.json()
            except:
                logging.info(resp.status)
                raise
            if resp.status == 430:
                wait_until = datetime.fromtimestamp(response["Retry-At"])
                seconds = (wait_until - datetime.now()).total_seconds()
                seconds = max(0.1, seconds)
                if seconds > 0:
                    logging.info("Wait for %s seconds.", seconds)
                    await asyncio.sleep(seconds)


async def main():
    async with aiohttp.ClientSession() as session:
        await asyncio.gather(*[asyncio.create_task(worker(session)) for _ in range(50)])
    logging.info("Exited workers")
    await asyncio.sleep(5)


asyncio.run(main())
