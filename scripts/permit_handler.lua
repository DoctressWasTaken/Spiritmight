local function check_limits(key, timestamp)
    -- Get permission to register a new request
    local max_time = 0
    if redis.call('exists', key) == 1 then
        local duration = tonumber(redis.call('hget', key, 'duration'))
        local max = tonumber(redis.call('hget', key, 'max'))
        local requests_key = key .. ':requests'
        -- Check if requests key exists
        if redis.call('exists', requests_key) == 1 then
            -- drop blockers that have timed out
            redis.call('zremrangebyscore', requests_key, 0, timestamp)
            -- count remaining
            local current_block = redis.call('zcount', requests_key, -1, "+inf")
            -- redis.log(redis.LOG_WARNING, 'Tasks: '..current_block)
            -- redis.log(redis.LOG_WARNING, 'Max: '..max)
            -- redis.log(redis.LOG_WARNING, 'Key: '..key)

            -- check against limit
            if current_block >= max then
                return tonumber(redis.call('zrange', requests_key, 0, 0, 'WITHSCORES')[2])
            end
        end
    else
        redis.call('hset', key, 'duration', 10, 'max', 5)
    end
    return 0
end

local function interal_wait(key, timestamp)
    -- Check if the limit is full enough to warrant a local wait
    local duration = tonumber(redis.call('hget', key, 'duration'))
    local max = tonumber(redis.call('hget', key, 'max'))
    local requests_key = key .. ':requests'
    local count = redis.call('zcount', requests_key, -1, "+inf")
    local base = 2 / duration
    local falloff = 1 - base
    local wait_percentage = base * falloff ^ (max - count)
    local wait_duration = wait_percentage * duration
    if count == 0 then
        return 0
    end
    wait_duration = math.max(duration / 2 / max, wait_duration)
    -- redis.log(redis.LOG_WARNING, max .. ":" .. duration .. "\t| Calculated a wait of " .. wait_duration .. " with " .. count .. " preexisting requests.")
    local newest_request = tonumber(redis.call('zrange', requests_key, -1, -1, 'WITHSCORES')[2])
    local wait_from_latest = (newest_request - timestamp - duration * 1000) + wait_duration * 1000
    -- redis.log(redis.LOG_WARNING, max .. ":" .. duration .. "\t| Created a wait requirement of " .. wait_from_latest)
    -- redis.log(redis.LOG_WARNING, max .. ":" .. duration .. "\t| Newest request will dissapear at " .. newest_request)
    -- redis.log(redis.LOG_WARNING, max .. ":" .. duration .. "\t| Current timestamp " .. timestamp)
    return wait_from_latest

end

local function update_limits(key, request_id, timestamp, additional_wait)
    -- Register a new request
    local duration = tonumber(redis.call('hget', key, 'duration'))
    local max = tonumber(redis.call('hget', key, 'max'))
    local requests_key = key .. ':requests'

    redis.call('zadd', requests_key, timestamp + duration * 1000 + additional_wait + EXTRA_LENGTH * 1000, request_id)

end

local timestamp = ARGV[1]
local request_id = ARGV[2]

local server = KEYS[1]
local endpoint = KEYS[2]
local endpoint_global_limit = KEYS[3]

local global_limit = tonumber(redis.call('pttl', endpoint_global_limit))
if global_limit > 0 then
    return global_limit
end

local wait_until = check_limits(server, timestamp)
-- redis.log(redis.LOG_WARNING, "Server"..wait_until)
wait_until = math.max(wait_until, check_limits(endpoint, timestamp))
-- redis.log(redis.LOG_WARNING, "Wait until "..wait_until)

if wait_until > 0 then
    return wait_until
end

local additional_wait = interal_wait(server, timestamp)
additional_wait = math.max(additional_wait, interal_wait(endpoint, timestamp))

if additional_wait <= 1000 * INTERNAL_DELAY then
    update_limits(server, request_id, timestamp, additional_wait)
    update_limits(endpoint, request_id, timestamp, additional_wait)
else
    return additional_wait
end

return -additional_wait
