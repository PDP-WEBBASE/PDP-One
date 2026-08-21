# syntax=docker/dockerfile:1.7
ARG PDP_DOCKER_REGISTRY=docker.arvancloud.ir/library

FROM ${PDP_DOCKER_REGISTRY}/node:22-bookworm-slim AS build
ARG PDP_BUILD_ID=unknown
ENV PDP_BUILD_ID=${PDP_BUILD_ID}
WORKDIR /app

COPY package*.json ./
RUN --mount=type=cache,target=/root/.npm npm ci
COPY . .
RUN mkdir -p public && printf '{"build_id":"%s"}\n' "$PDP_BUILD_ID" > public/pdp-build.json
RUN chmod +x scripts/*.sh
RUN npm run build

# Vinext is a development/build dependency in the repository, but its CLI and
# Cloudflare/Vite adapters are also required by the production "vinext start"
# command. Remove every other development-only package after the artifact is
# built, then restore this exact, pinned runtime set without saving it back to
# the source manifest.
RUN npm prune --omit=dev \
    && npm install --no-save --omit=dev \
      vinext@0.0.50 \
      vite@8.0.13 \
      wrangler@4.92.0 \
      @cloudflare/vite-plugin@1.37.1 \
      @vitejs/plugin-react@6.0.2 \
      @vitejs/plugin-rsc@0.5.26

FROM ${PDP_DOCKER_REGISTRY}/node:22-bookworm-slim AS runtime
ARG PDP_BUILD_ID=unknown
WORKDIR /app
ENV NODE_ENV=production \
    PDP_BUILD_ID=${PDP_BUILD_ID} \
    WRANGLER_WRITE_LOGS=false \
    WRANGLER_LOG_PATH=/tmp/pdp-one-wrangler.log

# Copy only the verified artifact, the pruned runtime dependencies, and the
# small Vinext configuration surface needed by "vinext start". Application
# source, tests, build scripts, TypeScript tooling and the build cache do not
# enter the final image.
COPY --from=build /app/package.json /app/package-lock.json ./
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/dist ./dist
COPY --from=build /app/public ./public
COPY --from=build /app/.openai ./.openai
COPY --from=build /app/build ./build
COPY --from=build /app/worker ./worker
COPY --from=build /app/vite.config.ts ./vite.config.ts

EXPOSE 3000
CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0", "--port", "3000"]
