from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any

from django.conf import settings
from django.core.cache import cache

from .curiosity import (
    curiosity_rank,
    curiosity_to_defectdojo_severity,
    normalize_curiosity_level,
    port_curiosity_score,
)
from .models import ScanBatch, ScanRun

MAX_RESPONSE_BYTES = 2 * 1024 * 1024
TOKEN_CACHE_KEY = "integrations:defectdojo:api-token"


class DefectDojoError(RuntimeError):
    pass


class DefectDojoNotConfigured(DefectDojoError):
    pass


def _stable_id(*parts: object) -> str:
    value = "\x00".join(str(part).strip().lower() for part in parts)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _endpoint(value: object) -> list[str]:
    if isinstance(value, str) and value.strip():
        return [value.strip()[:2000]]
    return []


def _finding(
    *,
    title: str,
    description: str,
    unique_id: str,
    endpoints: list[str | dict[str, Any]],
    rule: str,
    severity: str = "Info",
    curiosity: str | None = None,
) -> dict[str, Any]:
    level = normalize_curiosity_level(curiosity)
    if level:
        severity = curiosity_to_defectdojo_severity(level)
        if f"Curiosity: {level}" not in description:
            description = f"{description}\nCuriosity: {level}".strip()
    finding: dict[str, Any] = {
        "title": title[:511],
        "severity": severity,
        "description": description,
        "unique_id_from_tool": unique_id,
        "vuln_id_from_tool": rule,
        "dynamic_finding": True,
        "static_finding": False,
        "tags": ["surfacex", "attack-surface"],
    }
    if level:
        finding["tags"] = [*finding["tags"], f"curiosity:{level}"]
    if endpoints:
        finding["endpoints"] = endpoints
    return finding


def build_generic_findings_report(run: ScanRun) -> dict[str, Any]:
    """Build DefectDojo generic findings from active discovery results.

    Passive crt.sh/RDAP payloads (`result["passive"]`) are intentionally omitted —
    they stay as SurfaceX observations / Findings only.
    """
    findings_by_id: dict[str, dict[str, Any]] = {}

    for batch in run.batches.all():
        if batch.status != ScanBatch.Status.COMPLETED:
            continue
        result = batch.result if isinstance(batch.result, dict) else {}
        # Do not read result["passive"] — SurfaceX-only report.
        hosts = result.get("hosts", [])
        if not isinstance(hosts, list):
            hosts = []

        for host in hosts:
            if not isinstance(host, dict):
                continue
            address = str(host.get("address") or batch.target_address).strip()
            if not address:
                continue
            live_id = _stable_id("live-host", address)
            findings_by_id[live_id] = _finding(
                title=f"Live host: {address}",
                description="SurfaceX observed a responding host during discovery.",
                unique_id=live_id,
                endpoints=[address],
                rule="surfacex.live-host",
                severity="Info",
                curiosity="info",
            )

            ports = host.get("ports", [])
            if not isinstance(ports, list):
                continue
            for port_data in ports:
                if not isinstance(port_data, dict):
                    continue
                port = port_data.get("port")
                if isinstance(port, bool) or not isinstance(port, int):
                    continue
                protocol = str(port_data.get("protocol") or "tcp").lower()
                service = str(port_data.get("service") or "unknown").strip()
                product = str(port_data.get("product") or "").strip()
                version = str(port_data.get("version") or "").strip()
                curiosity = port_curiosity_score(port)
                service_id = _stable_id(
                    "open-service",
                    address,
                    protocol,
                    port,
                )
                details = [f"Protocol: {protocol}", f"Service: {service}"]
                if product:
                    details.append(f"Product: {product}")
                if version:
                    details.append(f"Version: {version}")
                findings_by_id[service_id] = _finding(
                    title=f"Open {service} service on {address}:{port}",
                    description="\n".join(details),
                    unique_id=service_id,
                    endpoints=[
                        {
                            "protocol": protocol,
                            "host": address,
                            "port": port,
                        }
                    ],
                    rule="surfacex.open-service",
                    curiosity=curiosity,
                )

        technology_records: list[dict[str, Any]] = []
        signatures = result.get("signatures", [])
        if isinstance(signatures, list):
            technology_records.extend(
                item for item in signatures if isinstance(item, dict)
            )
        http_records = result.get("http", [])
        if isinstance(http_records, list):
            for record in http_records:
                if not isinstance(record, dict):
                    continue
                technologies = record.get("tech", [])
                if not isinstance(technologies, list):
                    continue
                for technology in technologies:
                    if isinstance(technology, str):
                        technology_records.append(
                            {
                                "endpoint": record.get(
                                    "url",
                                    record.get("input", batch.target_address),
                                ),
                                "technology": technology,
                                "confidence": 30,
                                "evidence": "httpx technology detection",
                            }
                        )

        for record in technology_records:
            technology = str(record.get("technology") or "").strip()
            if not technology:
                continue
            endpoint = str(
                record.get("endpoint") or batch.target_address
            ).strip()
            technology_id = _stable_id("technology", endpoint, technology)
            confidence = record.get("confidence")
            evidence = str(record.get("evidence") or "SurfaceX fingerprint")
            try:
                conf_score = int(confidence) if confidence is not None else 0
            except (TypeError, ValueError):
                conf_score = 0
            if conf_score >= 70:
                tech_curiosity = "medium"
            elif conf_score >= 40:
                tech_curiosity = "low"
            else:
                tech_curiosity = "info"
            existing = findings_by_id.get(technology_id)
            if existing is not None:
                existing_level = None
                for tag in existing.get("tags") or []:
                    if isinstance(tag, str) and tag.startswith("curiosity:"):
                        existing_level = tag.split(":", 1)[1]
                        break
                if curiosity_rank(tech_curiosity) <= curiosity_rank(existing_level):
                    continue
            findings_by_id[technology_id] = _finding(
                title=f"Technology detected: {technology}",
                description=(
                    f"Technology: {technology}\n"
                    f"Confidence: {confidence if confidence is not None else 'unknown'}\n"
                    f"Evidence: {evidence}"
                ),
                unique_id=technology_id,
                endpoints=_endpoint(endpoint),
                rule="surfacex.technology",
                curiosity=tech_curiosity,
            )

    return {
        "name": f"SurfaceX scan #{run.pk}",
        "type": "SurfaceX",
        "version": "1",
        "description": "Attack-surface observations exported by SurfaceX.",
        "dynamic_tool": True,
        "findings": list(findings_by_id.values()),
    }


def _read_response(response: Any) -> dict[str, Any]:
    body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise DefectDojoError("DefectDojo response exceeded the 2 MiB limit.")
    try:
        decoded = json.loads(body or b"{}")
    except json.JSONDecodeError as exc:
        raise DefectDojoError("DefectDojo returned invalid JSON.") from exc
    if not isinstance(decoded, dict):
        raise DefectDojoError("DefectDojo returned an invalid response.")
    return decoded


def _base_url() -> str:
    value = settings.DEFECTDOJO_URL.strip().rstrip("/")
    if not value:
        raise DefectDojoNotConfigured("DefectDojo URL is not configured.")
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise DefectDojoNotConfigured("DefectDojo URL is invalid.")
    return value


def _api_token() -> str:
    configured = settings.DEFECTDOJO_API_TOKEN.strip()
    if configured:
        return configured

    cached = cache.get(TOKEN_CACHE_KEY)
    if isinstance(cached, str) and cached:
        return cached

    username = settings.DEFECTDOJO_USERNAME.strip()
    password = settings.DEFECTDOJO_PASSWORD
    if not username or not password:
        raise DefectDojoNotConfigured(
            "DefectDojo API token or username and password are required."
        )
    payload = json.dumps(
        {"username": username, "password": password},
        separators=(",", ":"),
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{_base_url()}/api/v2/api-token-auth/",
        data=payload,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=settings.DEFECTDOJO_TIMEOUT_SECONDS,
        ) as response:
            decoded = _read_response(response)
    except urllib.error.HTTPError as exc:
        raise DefectDojoError(
            f"DefectDojo authentication failed with HTTP {exc.code}."
        ) from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise DefectDojoError("Cannot reach DefectDojo.") from exc

    token = decoded.get("token")
    if not isinstance(token, str) or not token:
        raise DefectDojoError("DefectDojo did not return an API token.")
    cache.set(TOKEN_CACHE_KEY, token, timeout=900)
    return token


def _multipart_body(
    fields: dict[str, str],
    *,
    filename: str,
    content: bytes,
) -> tuple[bytes, str]:
    boundary = f"surfacex-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            (
                f"--{boundary}\r\n".encode(),
                (
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                ).encode(),
                value.encode("utf-8"),
                b"\r\n",
            )
        )
    chunks.extend(
        (
            f"--{boundary}\r\n".encode(),
            (
                'Content-Disposition: form-data; name="file"; '
                f'filename="{filename}"\r\n'
            ).encode(),
            b"Content-Type: application/json\r\n\r\n",
            content,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        )
    )
    return b"".join(chunks), boundary


def export_scan_to_defectdojo(run: ScanRun) -> dict[str, Any]:
    report = build_generic_findings_report(run)
    findings = report["findings"]
    if not findings:
        raise DefectDojoError("The scan has no observations to export.")

    report_bytes = json.dumps(
        report,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    scan_date = (run.finished_at or run.created_at).date().isoformat()
    fields = {
        "scan_type": "Generic Findings Import",
        "product_type_name": settings.DEFECTDOJO_PRODUCT_TYPE,
        "product_name": settings.DEFECTDOJO_PRODUCT_NAME,
        "engagement_name": settings.DEFECTDOJO_ENGAGEMENT_NAME,
        "test_title": settings.DEFECTDOJO_TEST_TITLE,
        "auto_create_context": "true",
        "minimum_severity": "Info",
        "active": "true",
        "verified": "false",
        "close_old_findings": "false",
        "do_not_reactivate": "false",
        "scan_date": scan_date,
    }
    body, boundary = _multipart_body(
        fields,
        filename=f"surfacex-scan-{run.pk}.json",
        content=report_bytes,
    )
    request = urllib.request.Request(
        f"{_base_url()}/api/v2/reimport-scan/",
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Authorization": f"Token {_api_token()}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=settings.DEFECTDOJO_TIMEOUT_SECONDS,
        ) as response:
            result = _read_response(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read(4096).decode("utf-8", errors="replace")
        raise DefectDojoError(
            f"DefectDojo rejected the report with HTTP {exc.code}: {detail}"
        ) from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise DefectDojoError("Cannot reach DefectDojo.") from exc

    return {
        "finding_count": len(findings),
        "test": result.get("test"),
        "message": result.get("message", "Scan exported to DefectDojo."),
    }
