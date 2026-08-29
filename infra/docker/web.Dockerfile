ARG PDP_DOCKER_REGISTRY=docker.arvancloud.ir/library
FROM ${PDP_DOCKER_REGISTRY}/node:22-bookworm-slim AS build
ARG PDP_BUILD_ID=unknown
ENV PDP_BUILD_ID=${PDP_BUILD_ID}
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN mkdir -p public && printf '{"build_id":"%s"}\n' "$PDP_BUILD_ID" > public/pdp-build.json
RUN chmod +x scripts/*.sh
RUN npm run build

FROM ${PDP_DOCKER_REGISTRY}/node:22-bookworm-slim
LABEL io.pdpone.component="web"
ARG PDP_BUILD_ID=unknown
WORKDIR /app
ENV NODE_ENV=production PDP_BUILD_ID=${PDP_BUILD_ID}
COPY --from=build /app ./
EXPOSE 3000
CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0", "--port", "3000"]