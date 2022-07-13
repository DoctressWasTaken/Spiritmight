-- This is a script used in grafana to generate a key which is then read by another query to display all server limits in a single entry.
local function ends_with(str, ending)
    return str:sub(-#ending) == ending
end
local function mysplit (inputstr, sep)
    local t = {}
    for str in string.gmatch(inputstr, '([^' .. sep .. ']+)') do
        table.insert(t, str)
    end
    return t
end

local keys = redis.call('keys', 'riot_api_proxy:*')
for i = 0, #keys do
    local key = keys[i]
    if key == nil then

    elseif not ends_with(key, 'requests') then
        key = string.gsub(tostring(key), '%%', '/')
        local count = redis.call('zcount', keys[i] .. ':requests', '-inf', '+inf')
        local parts = mysplit(key, ':')
        local server = parts[3]
        if #parts == 3 then
            redis.call('hset', 'grafana_usage_server', tostring(server), tonumber(count))
        end
        redis.log(redis.LOG_WARNING, server .. ':' .. count)
    end
end
