# ---- Frontend (React) production image ----------------------------------
# Stage 1: build the CRA bundle with the right REACT_APP_* vars baked in
# Stage 2: serve it from nginx with an `/api` proxy to the backend service
# -------------------------------------------------------------------------
FROM node:20-alpine AS builder

WORKDIR /src
ENV NODE_OPTIONS=--openssl-legacy-provider
ENV CI=true

# Allow overrides at build time; docker-compose/CI supplies real values.
ARG REACT_APP_BACKEND_URL
ARG REACT_APP_DOMAIN_BG
ARG REACT_APP_DOMAIN_RO
ARG REACT_APP_DOMAIN_EN
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL \
    REACT_APP_DOMAIN_BG=$REACT_APP_DOMAIN_BG \
    REACT_APP_DOMAIN_RO=$REACT_APP_DOMAIN_RO \
    REACT_APP_DOMAIN_EN=$REACT_APP_DOMAIN_EN

COPY package.json yarn.lock ./
RUN yarn install --frozen-lockfile --network-timeout 120000

COPY . .
RUN yarn build

# ------------------------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

# Remove the default nginx demo site + install our config + built assets.
RUN rm -rf /usr/share/nginx/html/* /etc/nginx/conf.d/default.conf

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh
COPY --from=builder /src/build /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -q -O - http://127.0.0.1/healthz >/dev/null || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]
