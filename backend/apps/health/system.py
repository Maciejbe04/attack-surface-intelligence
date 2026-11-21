from __future__ import annotations

import platform
import re
import shutil
import subprocess
import sys
from typing import Any
from urllib.parse import urlparse

import django
import redis
from celery import __version__ as celery_version
from django.conf import settings
from django.db import connection
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


def _short(value: str, limit: int = 120) -> str:
    text = " ".join(value.split())
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


def _postgres_version() -> str:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SHOW server_version")
            row = cursor.fetchone()
        return str(row[0]) if row else "unknown"
    except Exception as exc:
        return f"unavailable ({type(exc).__name__})"


def _redis_version() -> str:
    try:
        client = redis.Redis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        info = client.info("server")
        return str(info.get("redis_version") or "unknown")
    except Exception as exc:
        return f"unavailable ({type(exc).__name__})"


def _command_version(binary: str, arguments: list[str]) -> str | None:
    path = shutil.which(binary)
    if not path:
        return None
    try:
        completed = subprocess.run(
            [path, *arguments],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except Exception as exc:
        return f"unavailable ({type(exc).__name__})"
    output = (completed.stdout or completed.stderr or "").strip()
    if not output:
        return "installed"
    first_line = output.splitlines()[0]
    match = re.search(r"(\d+\.\d+(?:\.\d+)?)", first_line)
    return match.group(1) if match else _short(first_line, 80)


def _defectdojo_integration() -> dict[str, Any]:
    configured = bool(
        settings.DEFECTDOJO_URL
        and (settings.DEFECTDOJO_API_TOKEN or settings.DEFECTDOJO_PASSWORD)
    )
    host = ""
    if settings.DEFECTDOJO_URL:
        parsed = urlparse(settings.DEFECTDOJO_URL)
        host = parsed.netloc or settings.DEFECTDOJO_URL
    return {
        "id": "defectdojo",
        "name": "DefectDojo",
        "enabled": configured,
        "status": "configured" if configured else "not_configured",
        "version": settings.DEFECTDOJO_VERSION,
        "endpoint": host,
        "product_type": settings.DEFECTDOJO_PRODUCT_TYPE,
        "product_name": settings.DEFECTDOJO_PRODUCT_NAME,
        "engagement_name": settings.DEFECTDOJO_ENGAGEMENT_NAME,
        "test_title": settings.DEFECTDOJO_TEST_TITLE,
        "auto_export": True,
        "summary": (
            "Automatic findings export after completed scans."
            if configured
            else "Optional. Configure URL and credentials to enable export."
        ),
    }


def build_system_info() -> dict[str, Any]:
    nmap_version = _command_version("nmap", ["--version"])
    httpx_runtime = _command_version("httpx", ["-version"])
    components = [
        {
            "id": "surfacex-api",
            "name": "SurfaceX API",
            "role": "Django REST API",
            "version": settings.APP_VERSION,
        },
        {
            "id": "python",
            "name": "Python",
            "role": "Runtime",
            "version": platform.python_version(),
        },
        {
            "id": "django",
            "name": "Django",
            "role": "Web framework",
            "version": django.get_version(),
        },
        {
            "id": "celery",
            "name": "Celery",
            "role": "Task queue",
            "version": celery_version,
        },
        {
            "id": "postgresql",
            "name": "PostgreSQL",
            "role": "Primary database",
            "version": _postgres_version(),
        },
        {
            "id": "redis",
            "name": "Redis",
            "role": "Broker / cache / sessions",
            "version": _redis_version(),
        },
        {
            "id": "nmap",
            "name": "nmap",
            "role": "Host / port discovery (worker)",
            "version": nmap_version or "worker image",
        },
        {
            "id": "httpx",
            "name": "ProjectDiscovery httpx",
            "role": "HTTP fingerprinting (worker)",
            "version": httpx_runtime or settings.HTTPX_VERSION,
        },
        {
            "id": "react",
            "name": "React web console",
            "role": "Frontend",
            "version": settings.WEB_VERSION,
        },
        {
            "id": "defectdojo",
            "name": "DefectDojo",
            "role": "Optional findings platform",
            "version": settings.DEFECTDOJO_VERSION,
        },
    ]
    try:
        from apps.scans.signatures import pack_info

        sig_pack = pack_info()
    except Exception:
        sig_pack = {"version": "unknown", "count": 0, "ids": []}
    return {
        "app": {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "role": settings.ROLE,
            "platform": platform.platform(),
            "python": platform.python_version(),
            "executable": sys.executable,
        },
        "integrations": [_defectdojo_integration()],
        "signatures": {
            "pack_version": sig_pack.get("version"),
            "count": sig_pack.get("count"),
            "ids": sig_pack.get("ids") or [],
            "summary": "Built-in YAML signature pack (read-only).",
        },
        "stack": components,
    }


class SystemInfoView(APIView):
    permission_classes = (IsAuthenticated,)

    def get(self, request: Request) -> Response:
        return Response(build_system_info())
