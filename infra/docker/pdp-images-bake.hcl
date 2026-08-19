variable "IMAGE_SHA" {
  default = "unknown"
}

variable "PDP_DOCKER_REGISTRY" {
  default = "docker.arvancloud.ir/library"
}

group "default" {
  targets = ["backend", "mcp", "web"]
}

target "backend" {
  context    = "./backend"
  dockerfile = "Dockerfile"
  tags       = ["ghcr.io/pdp-webbase/pdp-one-backend:${IMAGE_SHA}"]
  args = {
    PDP_DOCKER_REGISTRY = PDP_DOCKER_REGISTRY
  }
  labels = {
    "org.opencontainers.image.source"   = "https://github.com/PDP-WEBBASE/PDP-One"
    "org.opencontainers.image.revision" = IMAGE_SHA
    "org.opencontainers.image.title"    = "PDP One backend"
  }
  cache-from = ["type=gha,scope=pdp-one-backend"]
  cache-to   = ["type=gha,mode=max,scope=pdp-one-backend"]
}

target "mcp" {
  context    = "./services/pdp_mcp"
  dockerfile = "Dockerfile"
  tags       = ["ghcr.io/pdp-webbase/pdp-one-mcp:${IMAGE_SHA}"]
  args = {
    PDP_DOCKER_REGISTRY = PDP_DOCKER_REGISTRY
  }
  labels = {
    "org.opencontainers.image.source"   = "https://github.com/PDP-WEBBASE/PDP-One"
    "org.opencontainers.image.revision" = IMAGE_SHA
    "org.opencontainers.image.title"    = "PDP One mcp"
  }
  cache-from = ["type=gha,scope=pdp-one-mcp"]
  cache-to   = ["type=gha,mode=max,scope=pdp-one-mcp"]
}

target "web" {
  context    = "."
  dockerfile = "./infra/docker/web.Dockerfile"
  tags       = ["ghcr.io/pdp-webbase/pdp-one-web:${IMAGE_SHA}"]
  args = {
    PDP_DOCKER_REGISTRY = PDP_DOCKER_REGISTRY
    PDP_BUILD_ID        = IMAGE_SHA
  }
  labels = {
    "org.opencontainers.image.source"   = "https://github.com/PDP-WEBBASE/PDP-One"
    "org.opencontainers.image.revision" = IMAGE_SHA
    "org.opencontainers.image.title"    = "PDP One web"
  }
  cache-from = ["type=gha,scope=pdp-one-web"]
  cache-to   = ["type=gha,mode=max,scope=pdp-one-web"]
}
