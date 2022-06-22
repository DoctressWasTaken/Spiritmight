#!/usr/bin/env bash


exec poetry run gunicorn main:init_app \
    --bind 0.0.0.0:80 \
    --worker-class aiohttp.GunicornWebWorker
#exec poetry run python -u main.py
