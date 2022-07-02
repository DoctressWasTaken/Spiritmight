# Riot API Ratelimiting Proxy

Processes requests that are being proxied to the web server to the Riot API,
while assuring Rate Limit conformity via a moving limit bucket. In essence:
- For each *relevant* ratelimit the full duration of the limit is tracked.
- All requests made in that interval are continuously summed up.
- As long as the max number of requests is reached no new requests are allowed.

### How to use:

It's a proxy running on http. So just pass along the Riot API URL (**as http**) and set the URL/IP (However you set the proxy to be reachable)
as the proxy target. An example setup using async python can be found in *client.py*


### Caveats:

Because some requests to the API could be delayed due to ping/network there is a small possibility that some requests are
counted towards the wrong bucket server side. As such the proxy adds an extra interval that delays the requests a bit which
causes slight loss of performance. Can be deactivated, **untested**.

**No high performance tests done yet.**

**Can be scaled and put behind a load balancer.**


### Config variables:
*Put them in **config.env** or update the compose file.*

```dotenv
# Prefix for redis keys (in case you run into overlap in naming schemas)
ENVIRONMENT=riot_api_proxy

# Security Buffer
DELAY=0.5

# For extra output
DEBUG=False

# Redis server location
REDIS_HOST=redis
REDIS_PORT=6379
```

In addition one or multiple api keys (multiple only if they share an obfuscation key) can be provided. Multiple
keys need to be separated by `|` but without spaces.
```dotenv
API_KEY=RGAPI-...|RGAPI-...
```

Standalone Redis + Network can be disabled in the compose file. The network should be created as an external network:

### Super simple setup
```shell
docker network create spiritmight
docker-compose build
docker-compose up -d
```

### Running in Kubernetes

For running in Kubernetes it mandatory to have a LoadBalancer provider in your cluster. Without said LB provider the Proxy will not be reachable.
If you want to change the envs do so in the `deployment.yaml` as for the API Key use the supplied `secrets_template.yaml` to create a `secrets.yaml` and
fill in your API Keys in the aforementioned format. 

```shell
docker-compose build
kubectl apply -f secrets.yaml
kubectl apply -f deployment.yaml
```


### Mock API

Start the container in the mock_api/ folder.  
Set `DEBUG=True` and un-comment the `API_URL` parameter.  
Now all requests should be directed to the mock API container instead.
