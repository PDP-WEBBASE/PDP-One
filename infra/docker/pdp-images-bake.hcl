# Component identity contract is verified on Session #124 corrective builds.
variable "RELEASE_SHA" {
  default = "unknown"
}

variable "BACKEND_FINGERPRINT" {
  default = "unknown"
}

variable "MCP_FINGERPRINT" {
  default = "unknown"
}

variable "WEB_FINGERPRINT" {
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
  tags       = ["ghcr.io/pdp-webbase/pdp-one-backend:content-${BACKEND_FINGERPRINT}"]
  args = {
    PDP_DOCKER_REGISTRY = PDP_DOCKER_REGISTRY
  }
  labels = {
    "org.opencontainers.image.source"          = "https://github.com/PDP-WEBBASE/PDP-One"
    "org.opencontainers.image.revision"        = RELEASE_SHA
    "org.opencontainers.image.title"           = "PDP One backend"
    "io.pdpone.component"                      = "backend"
    "io.pdpone.component.fingerprint"          = BACKEND_FINGERPRINT
  }
  cache-from = ["type=gha,scope=pdp-one-backend"]
  cache-to   = ["type=gha,mode=max,scope=pdp-one-backend"]
}

target "mcp" {
  context    = "./services/pdp_mcp"
  dockerfile = "Dockerfile"
  tags       = ["ghcr.io/pdp-webbase/pdp-one-mcp:content-${MCP_FINGERPRINT}"]
  args = {
    PDP_DOCKER_REGISTRY = PDP_DOCKER_REGISTRY
  }
  labels = {
    "org.opencontainers.image.source"          = "https://github.com/PDP-WEBBASE/PDP-One"
    "org.opencontainers.image.revision"        = RELEASE_SHA
    "org.opencontainers.image.title"           = "PDP One mcp"
    "io.pdpone.component"                      = "mcp"
    "io.pdpone.component.fingerprint"          = MCP_FINGERPRINT
  }
  cache-from = ["type=gha,scope=pdp-one-mcp"]
  cache-to   = ["type=gha,mode=max,scope=pdp-one-mcp"]
}

target "web" {
  context    = "."
  dockerfile = "./infra/docker/web.Dockerfile"
  tags       = ["ghcr.io/pdp-webbase/pdp-one-web:content-${WEB_FINGERPRINT}"]
  args = {
    PDP_DOCKER_REGISTRY = PDP_DOCKER_REGISTRY
    PDP_BUILD_ID        = "content-${WEB_FINGERPRINT}"
  }
  labels = {
    "org.opencontainers.image.source"          = "https://github.com/PDP-WEBBASE/PDP-One"
    "org.opencontainers.image.revision"        = RELEASE_SHA
    "org.opencontainers.image.title"           = "PDP One web"
    "io.pdpone.component"                      = "web"
    "io.pdpone.component.fingerprint"          = WEB_FINGERPRINT
  }
  cache-from = ["type=gha,scope=pdp-one-web"]
  cache-to   = ["type=gha,mode=max,scope=pdp-one-web"]
}
