import aioredis
import aiohttp
import asyncio
import yaml
import logging
import re
import pprint
import os
from datetime import datetime
import hashlib
import random
from aiohttplimiter import Allow, RateLimitExceeded, Limiter, default_keyfunc

pp = pprint.PrettyPrinter(indent=4)

if "DEBUG" in os.environ:
    logging.basicConfig(
        level=logging.DEBUG, format="%(levelname)8s %(asctime)s %(name)15s| %(message)s"
    )
else:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)8s %(asctime)s %(name)15s| %(message)s"
    )

logging.getLogger().setLevel(logging.WARN)
from aiohttp import web

logger = logging.getLogger("Mapping")

requests = {}


def handler(request: web.Request, exc: RateLimitExceeded):
    # If for some reason you want to allow the request, return aiohttplimitertest.Allow().
    logger.warning("429")
    return web.json_response({"Oh": "No"}, status=429)


limiter = Limiter(keyfunc=default_keyfunc, error_handler=handler)


@limiter.limit("500/10")
async def limiter_method(request):
    return


async def pseudo_handler(request: web.Request) -> web.Response:
    """Pseudo handler that should never be called."""
    global requests
    wait = 0
    if "euw1" in request.path:
        wait = 0.05
    elif "kr" in request.path:
        wait = 0.25
    elif "na1" in request.path:
        wait = 0.1
    await asyncio.sleep(wait * (1 + random.random() / 2 - 0.5))
    try:
        await limiter_method(request)
    except Exception as err:
        logging.warning(err)
    seconds = str(int(datetime.now().timestamp()) // 10 * 10)
    if seconds not in requests:
        prev = list(requests.keys())
        if len(prev) > 0:
            logger.warning("Requests at %s: %s.", prev[0], requests[prev[0]])
            del requests[prev[0]]
        requests[seconds] = 0
    requests[seconds] += 1
    # p.pprint(requests)
    return web.json_response(
        {"All": "Good"},
        headers={
            "X-App-Rate-Limit": "500:10,30000:600",
            "X-App-Rate-Limit-Count": "500:10,30000:600",
            "X-Method-Rate-Limit": "500:10",
            "X-Method-Rate-Limit-Count": "500:10",
            "mimetype": "",
        },
    )


async def init_app():
    app = web.Application(middlewares=[])
    app.add_routes([web.get("/{tail:.*}", pseudo_handler)])
    return app


async def runner():
    app = await init_app()
    web.run_app(app, host="0.0.0.0", port=80)


if __name__ == "__main__":
    app = asyncio.run(runner())
