from fde_deploy.render import artifact_hashes, render_artifacts
from fde_deploy.spec import validate_spec
from helpers import make_spec

GOLDEN_COMPOSE = """# Rendered by fde-oneclick-deploy for acme-corp (production)
# version: 1.0.0 | region: us-east-1 | tier: medium
services:
  app:
    image: registry.example.internal/acme-corp/app:1.0.0
    ports:
      - "8080:8080"
    environment:
      - APP_ENV=production
      - APP_REGION=us-east-1
    deploy:
      replicas: 2
      resources:
        limits:
          cpus: "2"
          memory: 2048M
    restart: unless-stopped
"""

GOLDEN_ENV = """# Environment template for acme-corp (production) — placeholder values only.
# Real values are injected at deploy time from the referenced secret store.
APP_CUSTOMER=acme-corp
APP_ENV=production
APP_REGION=us-east-1
APP_VERSION=1.0.0
APP_PORT=8080
API_TOKEN_REF=env://ACME_API_TOKEN
DB_PASSWORD_REF=vault://prod/acme/db-password
FEATURE_AUDIT_LOG=true
FEATURE_METRICS=true
"""

GOLDEN_NGINX = """# Reverse proxy for acme-corp (production) — rendered by fde-oneclick-deploy
upstream acme-corp_app {
    server 127.0.0.1:8080;
}

server {
    listen 80;
    server_name acme-corp.example.internal;

    location / {
        proxy_pass http://acme-corp_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /health {
        proxy_pass http://acme-corp_app/health;
        access_log off;
    }
}
"""

GOLDEN_SERVICE = """[Unit]
Description=acme-corp app (production) — deployed by fde-oneclick-deploy
After=network.target docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/srv/acme-corp/current
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
Environment=APP_VERSION=1.0.0

[Install]
WantedBy=multi-user.target
"""


def test_golden_artifact_set():
    spec = validate_spec(make_spec())
    artifacts = render_artifacts(spec)
    assert artifacts["docker-compose.yml"] == GOLDEN_COMPOSE
    assert artifacts[".env"] == GOLDEN_ENV
    assert artifacts["nginx.conf"] == GOLDEN_NGINX
    assert artifacts["app.service"] == GOLDEN_SERVICE


def test_rendering_is_deterministic():
    spec = validate_spec(make_spec())
    first = render_artifacts(spec)
    second = render_artifacts(spec)
    assert first == second
    assert artifact_hashes(first) == artifact_hashes(second)


def test_tier_drives_resources():
    small = render_artifacts(validate_spec(make_spec(tier="small")))
    large = render_artifacts(validate_spec(make_spec(tier="large")))
    assert "replicas: 1" in small["docker-compose.yml"]
    assert "memory: 1024M" in small["docker-compose.yml"]
    assert "replicas: 3" in large["docker-compose.yml"]
    assert "memory: 4096M" in large["docker-compose.yml"]


def test_no_secret_values_only_references():
    spec = validate_spec(make_spec())
    env = render_artifacts(spec)[".env"]
    assert "DB_PASSWORD_REF=vault://prod/acme/db-password" in env
    assert "DB_PASSWORD=" not in env.replace("DB_PASSWORD_REF=", "")
