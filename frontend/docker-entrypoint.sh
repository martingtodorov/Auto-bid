#!/bin/sh
# Renders nginx.conf with env variables, then starts nginx.
set -eu

: "${BACKEND_HOST:=backend:8001}"
export BACKEND_HOST

envsubst '${BACKEND_HOST}' < /etc/nginx/conf.d/default.conf > /tmp/default.conf
mv /tmp/default.conf /etc/nginx/conf.d/default.conf

exec nginx -g 'daemon off;'
