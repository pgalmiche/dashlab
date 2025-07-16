#!/bin/bash

# Start Gunicorn in the background
gunicorn -b 0.0.0.0:7777 dashboard:server &

# Start Caddy (runs in foreground by default)
exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
