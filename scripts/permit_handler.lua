local function check_limits(key, timestamp, customlimit)
    -- Get permission to register a new request
    if redis.call('exists', key) == 1 then
        local duration = tonumber(redis.call('hget', key, 'duration'))
        local max = tonumber(redis.call('hget', key, 'max'))
        local requests_key = key .. ':requests'
        -- Check if requests key exists
        if redis.call('exists', requests_key) == 1 then
            -- drop blockers that have timed out
            redis.call('zremrangebyscore', requests_key, 0, timestamp)
            -- count remaining
            local count = redis.call('zcount', requests_key, -1, "+inf")
            -- check against custom limit
            if customlimit ~= nil then
                if count >= tonumber(customlimit) then
                    return 1000
                end
            end
            -- check against limit
            if count >= max then
                local wait_until = tonumber(redis.call('zrange', requests_key, 0, 0, 'WITHSCORES')[2])
                return wait_until
            end
        end
    else
        redis.call('hset', key, 'duration', 10, 'max', 5)
    end
    return 0
end

local function internal_wait(key, timestamp)
    -- Check if the limit is full enough to warrant a local wait
    local duration = tonumber(redis.call('hget', key, 'duration'))
    local max = tonumber(redis.call('hget', key, 'max'))
    local requests_key = key .. ':requests'
    local count = redis.call('zcount', requests_key, -1, "+inf")
    if count == 0 then
        return 0
    end
    local fill_percentage = count / max
    local required_distance = fill_percentage * (duration + EXTRA_LENGTH) -- If almost full delay by up to the full bucket length
    local oldest_request = tonumber(redis.call('zrange', requests_key, 0, 0, 'WITHSCORES')[2])
    local extra_wait = (oldest_request - duration * 1000 + required_distance * 1000) - timestamp
    return extra_wait
end

local function update_limits(key, request_id, timestamp, additional_wait)
    -- Register a new request
    local duration = tonumber(redis.call('hget', key, 'duration'))
    local requests_key = key .. ':requests'
    redis.call('zadd', requests_key, timestamp + duration * 1000 + additional_wait + EXTRA_LENGTH * 1000, request_id)
end

local timestamp = ARGV[1]
local request_id = ARGV[2]
local ratelimit = ARGV[3]

local server = KEYS[1]
local endpoint = KEYS[2]
local endpoint_global_limit = KEYS[3]

local global_limit = tonumber(redis.call('pttl', endpoint_global_limit))
if global_limit > 0 then
    return global_limit
end

local wait_until = check_limits(server, timestamp, nil)
wait_until = math.max(wait_until, check_limits(endpoint, timestamp))

local additional_wait = internal_wait(server, timestamp, ratelimit)
additional_wait = math.max(additional_wait, internal_wait(endpoint, timestamp), 0)

if wait_until > 0 then
    return wait_until + additional_wait
end

if additional_wait <= 1000 * INTERNAL_DELAY then
    update_limits(server, request_id, timestamp, additional_wait)
    update_limits(endpoint, request_id, timestamp, additional_wait)
else
    return timestamp + additional_wait
end

return -additional_wait
