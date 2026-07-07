# syntax=docker/dockerfile:1

###############################################################################
# Stage 1: install dependencies (lockfile-aware: pnpm or npm)
###############################################################################
FROM node:22-alpine AS deps

WORKDIR /app

# Wildcards tolerate whichever lockfile the project ends up with.
COPY package.json package-lock.json* pnpm-lock.yaml* ./
RUN if [ -f pnpm-lock.yaml ]; then \
        corepack enable pnpm && pnpm install --frozen-lockfile; \
    elif [ -f package-lock.json ]; then \
        npm ci; \
    else \
        npm install; \
    fi

###############################################################################
# Stage 2: build (Next.js standalone output; no API access required)
###############################################################################
FROM node:22-alpine AS build

WORKDIR /app

# Next.js resolves rewrites() at build time in standalone mode, so the API
# origin must be baked in here; compose can override via build.args.
ARG API_ORIGIN=http://api:8000
ENV NEXT_TELEMETRY_DISABLED=1 \
    API_ORIGIN=$API_ORIGIN

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# public/ is optional in Next.js; guarantee it exists for the runtime COPY.
RUN mkdir -p public \
    && if [ -f pnpm-lock.yaml ]; then \
        corepack enable pnpm && pnpm run build; \
    else \
        npm run build; \
    fi

###############################################################################
# Stage 3: runtime (non-root, standalone server)
###############################################################################
FROM node:22-alpine AS runtime

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# node:alpine ships a non-root `node` user (uid 1000).
COPY --from=build --chown=node:node /app/public ./public
COPY --from=build --chown=node:node /app/.next/standalone ./
COPY --from=build --chown=node:node /app/.next/static ./.next/static

USER node

EXPOSE 3000

CMD ["node", "server.js"]
