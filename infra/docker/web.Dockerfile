ARG PDP_DOCKER_REGISTRY=docker.arvancloud.ir/library
FROM ${PDP_DOCKER_REGISTRY}/node:22-bookworm-slim AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN chmod +x scripts/*.sh
RUN npm run build

FROM ${PDP_DOCKER_REGISTRY}/node:22-bookworm-slim
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app ./
EXPOSE 3000
CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0", "--port", "3000"]

