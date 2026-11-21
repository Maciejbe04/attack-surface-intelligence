from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from rest_framework import serializers


PORTS_RE = re.compile(r"^[0-9]+(?:,[0-9]+)*$")
RELATIVE_PATH_RE = re.compile(r"^/[A-Za-z0-9._~!$&'()*+,;=:@%/-]*$")


@dataclass(frozen=True)
class Field:
    kind: str
    default: str | int | bool
    minimum: int | None = None
    maximum: int | None = None
    choices: tuple[str, ...] = ()


MODULES: dict[str, dict[str, Field]] = {
    "host-discovery": {
        "method": Field("choice", "icmp-tcp", choices=("icmp", "tcp", "icmp-tcp")),
        "tcpPorts": Field("ports", "80,443"),
        "timeoutSec": Field("integer", 3, 1, 30),
    },
    "port-scan": {
        "profile": Field(
            "choice",
            "discovery-fast",
            choices=("discovery-fast", "discovery-web", "discovery-full", "custom"),
        ),
        "customPorts": Field("ports", "22,80,443,8080,8443"),
        "timing": Field("choice", "T3", choices=("T2", "T3", "T4")),
        "maxRate": Field("integer", 200, 10, 5000),
    },
    "service-detect": {
        "intensity": Field("integer", 5, 0, 9),
        "lightOnly": Field("boolean", True),
    },
    "http-fingerprint": {
        "schemes": Field("choice", "both", choices=("http", "https", "both")),
        "ports": Field("ports", "80,443,8080,8443"),
        "followRedirects": Field("boolean", True),
        "maxRedirects": Field("integer", 3, 0, 10),
        "techDetect": Field("boolean", True),
        "timeoutSec": Field("integer", 5, 1, 30),
        "rateLimit": Field("integer", 50, 1, 500),
    },
    "tls-cert": {
        "ports": Field("ports", "443,8443"),
        "expireWarnDays": Field("integer", 30, 1, 365),
        "includeChain": Field("boolean", False),
    },
    "signatures": {
        "pack": Field("choice", "builtin", choices=("builtin", "web", "all")),
        "minConfidence": Field(
            "choice", "medium", choices=("low", "medium", "high")
        ),
        "pathsExtra": Field("paths", ""),
    },
    "full-pipeline": {
        "portProfile": Field(
            "choice",
            "discovery-fast",
            choices=("discovery-fast", "discovery-web"),
        ),
        "includeTls": Field("boolean", True),
        "includeSignatures": Field("boolean", True),
        "stopOnHostDown": Field("boolean", True),
    },
}


def _validate_ports(value: Any) -> str:
    if not isinstance(value, str) or not PORTS_RE.fullmatch(value):
        raise serializers.ValidationError("Must be a comma-separated port list.")
    ports = [int(port) for port in value.split(",")]
    if len(ports) > 1000 or len(set(ports)) != len(ports):
        raise serializers.ValidationError("Ports must be unique (maximum 1000).")
    if any(port < 1 or port > 65535 for port in ports):
        raise serializers.ValidationError("Ports must be between 1 and 65535.")
    return ",".join(str(port) for port in ports)


def _validate_paths(value: Any) -> str:
    if not isinstance(value, str):
        raise serializers.ValidationError("Must be a comma-separated path list.")
    if not value:
        return ""
    paths = value.split(",")
    if len(paths) > 20:
        raise serializers.ValidationError("At most 20 extra paths are allowed.")
    for path in paths:
        if (
            len(path) > 200
            or not RELATIVE_PATH_RE.fullmatch(path)
            or ".." in path.split("/")
            or path.startswith("//")
        ):
            raise serializers.ValidationError("Only safe relative paths are allowed.")
    return ",".join(paths)


def validate_modules(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise serializers.ValidationError("Select at least one module.")
    if len(value) > len(MODULES):
        raise serializers.ValidationError("Too many modules.")

    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != {"id", "filters"}:
            raise serializers.ValidationError(
                "Each module must contain only id and filters."
            )
        module_id = item["id"]
        filters = item["filters"]
        if module_id not in MODULES:
            raise serializers.ValidationError(f"Unknown module: {module_id!s}.")
        if module_id in seen:
            raise serializers.ValidationError(f"Duplicate module: {module_id}.")
        if not isinstance(filters, dict):
            raise serializers.ValidationError("Module filters must be an object.")

        schema = MODULES[module_id]
        unknown = set(filters) - set(schema)
        if unknown:
            raise serializers.ValidationError(
                f"Unknown filters for {module_id}: {', '.join(sorted(unknown))}."
            )

        normalized: dict[str, Any] = {}
        for key, field in schema.items():
            field_value = filters.get(key, field.default)
            if field.kind == "boolean":
                if not isinstance(field_value, bool):
                    raise serializers.ValidationError(f"{module_id}.{key} must be boolean.")
            elif field.kind == "integer":
                if isinstance(field_value, bool) or not isinstance(field_value, int):
                    raise serializers.ValidationError(f"{module_id}.{key} must be integer.")
                if field.minimum is not None and field_value < field.minimum:
                    raise serializers.ValidationError(f"{module_id}.{key} is too small.")
                if field.maximum is not None and field_value > field.maximum:
                    raise serializers.ValidationError(f"{module_id}.{key} is too large.")
            elif field.kind == "choice":
                if field_value not in field.choices:
                    raise serializers.ValidationError(
                        f"{module_id}.{key} has an unsupported value."
                    )
            elif field.kind == "ports":
                field_value = _validate_ports(field_value)
            elif field.kind == "paths":
                field_value = _validate_paths(field_value)
            normalized[key] = field_value

        validated.append({"id": module_id, "filters": normalized})
        seen.add(module_id)

    if "full-pipeline" in seen and len(seen) != 1:
        raise serializers.ValidationError(
            "full-pipeline is exclusive and cannot be combined with other modules."
        )
    return validated
