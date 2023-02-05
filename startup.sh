#!/usr/bin/env bash

./wait-for-it.sh redis-spiritmight:6379


exec poetry run gunicorn main:init_app \
    --bind 0.0.0.0:8888 \
    -w 6 \
    --worker-class aiohttp.GunicornWebWorker
#exec poetry run python -u main.py
