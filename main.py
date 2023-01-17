import aioredis
import aiohttp
import asyncio
import yaml
import logging
import re
import pprint
import os
from datetime import datetime, timedelta
import hashlib
import random
import uvloop
from functools import partial
from dotenv import load_dotenv

load_dotenv()
uvloop.install()

pp = pprint.PrettyPrinter(indent=4)

is_mock = False
api_url = "https?:\/\/([a-z12]{2,8}).api.riotgames.com.*"
if "DEBUG" in os.environ and os.environ.get("DEBUG") == "True":
    is_mock = api_url != os.environ.get("API_URL", api_url)
    api_url = os.environ.get("API_URL", api_url)  # Can be replaced only when DEBUG
    logging.basicConfig(
        level=logging.DEBUG, format="%(levelname)8s %(asctime)s %(name)15s| %(message)s"
    )
    logging.debug("Running debug level.")
else:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)8s %(asctime)s %(name)15s| %(message)s"
    )
    logging.getLogger().setLevel(logging.INFO)

from aiohttp import web


class Mapping:
    url_regex = re.compile(api_url)
    endpoints = {}
    session = redis = permit = update = None

    def __init__(self):
        self.logging = logging.getLogger("Proxy")
        self.env = os.environ.get("ENVIRONMENT", "rgapi")
        self.keys = {}
        for key in os.environ.get("API_KEY").split("|"):
            self.keys[key] = {
                "key": key,
                "ident": key[-5:],
                "session": aiohttp.ClientSession(headers={"X-Riot-Token": key}),
            }
        self.logging.info("Recognized %i api keys.", len(self.keys))
        # pp.pprint(self.endpoints)

    async def init(self, host="localhost", port=6379):
        self.redis = aioredis.from_url(
            "redis://%s:%s" % (host, port), encoding="utf-8", decode_responses=True
        )
        # TODO: If multiple copies of the service are started this might lead to multiple scripts
        #   And with it to parallel executions of said script (unsure)
        self.logging.info(
            "Internal buffer of %s second(s).", os.environ.get("INTERNAL_DELAY", 1)
        )
        self.logging.info(
            "Extra bucket length of %s second(s).", os.environ.get("EXTRA_LENGTH", 1)
        )
        with open("scripts/permit_handler.lua") as permit:
            permit_script = permit.read()
            permit_script = permit_script.replace(
                "INTERNAL_DELAY", os.environ.get("INTERNAL_DELAY", 1)
            ).replace("EXTRA_LENGTH", os.environ.get("EXTRA_LENGTH", 1))
            self.permit = await self.redis.script_load(permit_script)
            self.logging.info(self.permit)
        with open("scripts/update_ratelimits.lua") as update:
            self.update = await self.redis.script_load(update.read())
            self.logging.info(self.update)

    async def handler_wrapper(self, endpoint):
        return partial(self.handler, endpoint)

    async def handler(self, endpoint, request) -> web.Response:
        """Reqest Handler."""
        url = str(request.raw_path)
        self.logging.debug(url)
        server = self.url_regex.findall(url)[0]
        send_timestamp = datetime.now().timestamp() * 1000
        request_string = "%s_%s" % (url, send_timestamp)
        request_id = hashlib.md5(request_string.encode()).hexdigest()
        key_order = list(self.keys.keys())
        max_wait_time = 0
        for key in key_order:
            server_key = "%s:%s:%s" % (self.env, self.keys[key]["ident"], server)
            endpoint_key = "%s:%s" % (server_key, endpoint)

            endpoint_global_limit = "%s:global" % endpoint_key
            ratelimit = request.headers.get("ratelimit", -1)
            wait_time = await self.redis.evalsha(
                self.permit,
                3,
                server_key,
                endpoint_key,
                endpoint_global_limit,
                send_timestamp,
                request_id,
                ratelimit,
            )
            if wait_time > 0:
                max_wait_time = max(max_wait_time, wait_time)
                continue

            if wait_time < 0:
                await asyncio.sleep(-wait_time / 1000)

            url = url.replace("http:", "https:")
            try:
                async with self.keys[key]["session"].get(url) as response:

                    server_tracker = "tracking:%s:%s:server" % (int(send_timestamp / 1000), server_key)
                    await self.redis.hincrby(server_tracker, response.status, 1)
                    await self.redis.execute_command("expire", server_tracker, 600, "nx")
                    endpoint_tracker = "tracking:%s:%s" % (int(send_timestamp / 1000), endpoint_key)
                    await self.redis.hincrby(endpoint_tracker, response.status, 1)
                    await self.redis.execute_command("expire", endpoint_tracker, 600, "nx")

                    if (app_limits := response.headers.get("X-App-Rate-Limit")) and \
                            (method_limits := response.headers.get("X-Method-Rate-Limit")):
                        if app_limits == "20:1,100:120":
                            app_limits = ["15", "18"]
                        else:
                            app_limits = app_limits.split(",")[0].split(":")
                        method_limits = method_limits.split(",")[0].split(":")
                        await self.redis.evalsha(
                            self.update,
                            2,
                            server_key,
                            endpoint_key,
                            *[int(x) for x in app_limits + method_limits],
                        )
                    match response.status:
                        case 200:
                            result = await response.json()
                            return web.json_response(
                                result,
                                headers={
                                    header: response.headers[header]
                                    for header in response.headers
                                    if header.startswith("X")
                                },
                            )
                        case _:
                            if (
                                    response.status == 429
                                    and response.headers.get("X-Rate-Limit-Type") == "service"
                            ):
                                retry_after = response.headers.get("Retry-After", "1").strip()
                                await self.redis.setex(
                                    endpoint_global_limit, int(retry_after), 1
                                )

                            if limit_type := response.headers.get("X-Rate-Limit-Type", None):
                                self.logging.warning(
                                    "%i | %s | %s ",
                                    response.status,
                                    limit_type,
                                    url,
                                )
                            else:
                                self.logging.warning("%i | %s ", response.status, url)
                            return web.json_response(
                                {},
                                status=response.status,
                                headers={
                                    header: response.headers[header]
                                    for header in response.headers
                                    if header.startswith("X")
                                },
                            )
            except (aiohttp.ServerDisconnectedError, aiohttp.ClientConnectorError):
                return web.json_response({"Error": "API Disconnected"}, status=500)
        else:
            server_key = "%s:%s:%s" % (self.env, 'No-Key', server)
            endpoint_key = "%s:%s" % (server_key, endpoint)
            server_tracker = "tracking:%s:%s:server" % (int(send_timestamp / 1000), server_key)
            await self.redis.hincrby(server_tracker, 430, 1)
            await self.redis.execute_command("expire", server_tracker, 600, "nx")
            endpoint_tracker = "tracking:%s:%s" % (int(send_timestamp / 1000), endpoint_key)
            await self.redis.hincrby(endpoint_tracker, 430, 1)
            await self.redis.execute_command("expire", endpoint_tracker, 600, "nx")
            return web.json_response({"Retry-At": max_wait_time / 1000}, status=430)


class Router(web.UrlDispatcher):
    def __init__(self):
        super(Router, self).__init__()
        self.logging = logging.getLogger("Router")

    async def resolve(self, request):
        request = request.clone(rel_url=request.raw_path.split('.com')[1])
        res = await super().resolve(request)
        return res


async def init_app():
    mapping = Mapping()
    app = web.Application(router=Router())

    routes = []
    with open("endpoints.yaml") as endpoints:
        ep = yaml.safe_load(endpoints)["endpoints"]
        for cat in ep:
            for endpoint in ep[cat]:
                name = ".".join(re.sub('\{[^}]*}', '_', endpoint).strip('/').split('/'))
                routes.append(web.get(endpoint, await mapping.handler_wrapper(name), name=name))
                logging.info("Initiated endpoint %s", name)
    app.add_routes(routes)
    await mapping.init(
        host=os.environ.get("REDIS_HOST"),
        port=int(os.environ.get("REDIS_PORT")),
    )
    return app


async def runner():
    app = await init_app()
    web.run_app(app, host="0.0.0.0", port=8888)


if __name__ == "__main__":
    app = asyncio.run(runner())
