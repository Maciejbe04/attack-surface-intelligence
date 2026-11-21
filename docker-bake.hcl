variable "HTTPX_VERSION" {
  default = "v1.6.9"
}

group "default" {
  targets = ["api", "worker", "web", "gateway"]
}

target "api" {
  context    = "."
  dockerfile = "deploy/docker/Dockerfile.api"
  tags       = ["surfacex-api:local"]
  platforms  = ["linux/amd64", "linux/arm64"]
}

target "worker" {
  context    = "."
  dockerfile = "deploy/docker/Dockerfile.worker"
  tags       = ["surfacex-worker:local"]
  platforms  = ["linux/amd64", "linux/arm64"]
  args = {
    HTTPX_VERSION = HTTPX_VERSION
  }
}

target "web" {
  context    = "."
  dockerfile = "deploy/docker/Dockerfile.web"
  tags       = ["surfacex-web:local"]
  platforms  = ["linux/amd64", "linux/arm64"]
}

target "gateway" {
  context    = "."
  dockerfile = "deploy/docker/Dockerfile.gateway"
  tags       = ["surfacex-gateway:local"]
  platforms  = ["linux/amd64", "linux/arm64"]
}
