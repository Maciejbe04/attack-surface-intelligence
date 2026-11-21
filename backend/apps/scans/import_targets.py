from __future__ import annotations

import csv
import io
import ipaddress
import json
from dataclasses import dataclass

from .scope import check_target
from .validation import normalize_target

MAX_IMPORT_TARGETS = 10_000
MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_IMPORT_ERRORS = 50


@dataclass(frozen=True)
class ParsedTarget:
    address: str
    target_type: str
    comment: str = ""
    groups: tuple[str, ...] = ()


@dataclass
class ImportParseResult:
    targets: list[ParsedTarget]
    errors: list[str]
    skipped_duplicates_in_file: int = 0


def detect_target_type(address: str) -> str:
    value = address.strip()
    if "/" in value:
        return "cidr"
    try:
        ipaddress.ip_address(value)
        return "ip"
    except ValueError:
        return "domain"


def split_group_names(value: object) -> tuple[str, ...]:
    """Group cell: several names separated by ';' or '|'. Whitespace is collapsed."""
    if isinstance(value, list):
        parts = [str(item) for item in value]
    else:
        parts = str(value or "").replace("|", ";").split(";")
    names: list[str] = []
    for part in parts:
        name = " ".join(part.split())
        if name and name.lower() not in {existing.lower() for existing in names}:
            names.append(name)
    return tuple(names)


def _add_target(
    bucket: dict[str, ParsedTarget],
    *,
    address: str,
    target_type: str | None,
    comment: str,
    errors: list[str],
    line_label: str,
    groups: tuple[str, ...] = (),
) -> None:
    raw = address.strip()
    if not raw or raw.startswith("#"):
        return
    chosen_type = (target_type or detect_target_type(raw)).strip().lower()
    if chosen_type not in {"ip", "cidr", "domain"}:
        if len(errors) < MAX_IMPORT_ERRORS:
            errors.append(f"{line_label}: unsupported type '{chosen_type}'.")
        return
    try:
        normalized = normalize_target(raw, chosen_type)
        check_target(normalized, chosen_type)  # scan allowlist (OutOfScope is a ValueError)
    except ValueError as exc:
        if len(errors) < MAX_IMPORT_ERRORS:
            errors.append(f"{line_label}: {exc}")
        return
    key = normalized.lower()
    if key in bucket:
        # The same host listed twice may carry different groups: keep them all.
        if groups:
            existing = bucket[key]
            merged = existing.groups + tuple(
                name
                for name in groups
                if name.lower() not in {item.lower() for item in existing.groups}
            )
            bucket[key] = ParsedTarget(
                address=existing.address,
                target_type=existing.target_type,
                comment=existing.comment,
                groups=merged,
            )
        return
    if len(bucket) >= MAX_IMPORT_TARGETS:
        if len(errors) < MAX_IMPORT_ERRORS:
            errors.append(
                f"Import is limited to {MAX_IMPORT_TARGETS} targets."
            )
        return
    bucket[key] = ParsedTarget(
        address=normalized,
        target_type=chosen_type,
        comment=(comment or "")[:500],
        groups=groups,
    )


def parse_plaintext(content: str) -> ImportParseResult:
    bucket: dict[str, ParsedTarget] = {}
    errors: list[str] = []
    duplicates = 0
    for index, line in enumerate(content.splitlines(), start=1):
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        address = text.split(",", 1)[0].strip()
        before = len(bucket)
        error_before = len(errors)
        _add_target(
            bucket,
            address=address,
            target_type=None,
            comment="",
            errors=errors,
            line_label=f"line {index}",
        )
        if len(bucket) == before and len(errors) == error_before:
            duplicates += 1
    return ImportParseResult(
        targets=list(bucket.values()),
        errors=errors,
        skipped_duplicates_in_file=duplicates,
    )


def parse_csv(content: str) -> ImportParseResult:
    bucket: dict[str, ParsedTarget] = {}
    errors: list[str] = []
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        return ImportParseResult(targets=[], errors=["CSV header row is required."])

    field_map = {name.strip().lower(): name for name in reader.fieldnames if name}
    value_key = next(
        (
            field_map[name]
            for name in ("value", "address", "host", "target", "ip")
            if name in field_map
        ),
        None,
    )
    if value_key is None:
        return ImportParseResult(
            targets=[],
            errors=[
                "CSV must include a value/address/host column.",
            ],
        )
    type_key = next(
        (field_map[name] for name in ("type", "target_type") if name in field_map),
        None,
    )
    comment_key = next(
        (
            field_map[name]
            for name in ("comment", "notes", "note")
            if name in field_map
        ),
        None,
    )
    group_key = next(
        (
            field_map[name]
            for name in ("group", "groups", "group_name")
            if name in field_map
        ),
        None,
    )

    for index, row in enumerate(reader, start=2):
        _add_target(
            bucket,
            address=str(row.get(value_key) or ""),
            target_type=str(row.get(type_key) or "") if type_key else None,
            comment=str(row.get(comment_key) or "") if comment_key else "",
            errors=errors,
            line_label=f"row {index}",
            groups=split_group_names(row.get(group_key)) if group_key else (),
        )
        if len(bucket) >= MAX_IMPORT_TARGETS and any(
            "limited to" in item for item in errors
        ):
            break

    return ImportParseResult(targets=list(bucket.values()), errors=errors)


def parse_json(content: str) -> ImportParseResult:
    bucket: dict[str, ParsedTarget] = {}
    errors: list[str] = []
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        return ImportParseResult(targets=[], errors=[f"Invalid JSON: {exc.msg}."])

    items: list[object]
    if isinstance(payload, dict):
        version = payload.get("schema_version", 1)
        if version not in (1, "1"):
            return ImportParseResult(
                targets=[],
                errors=[f"Unsupported schema_version: {version}."],
            )
        raw_items = payload.get("targets", [])
        if not isinstance(raw_items, list):
            return ImportParseResult(
                targets=[],
                errors=["JSON field 'targets' must be a list."],
            )
        items = raw_items
    elif isinstance(payload, list):
        items = payload
    else:
        return ImportParseResult(
            targets=[],
            errors=["JSON must be an object with targets[] or a list."],
        )

    for index, item in enumerate(items, start=1):
        if isinstance(item, str):
            _add_target(
                bucket,
                address=item,
                target_type=None,
                comment="",
                errors=errors,
                line_label=f"item {index}",
            )
            continue
        if not isinstance(item, dict):
            if len(errors) < MAX_IMPORT_ERRORS:
                errors.append(f"item {index}: expected object or string.")
            continue
        address = item.get("value", item.get("address", item.get("host", "")))
        target_type = item.get("type", item.get("target_type"))
        comment = item.get("comment", item.get("notes", ""))
        _add_target(
            bucket,
            address=str(address or ""),
            target_type=str(target_type) if target_type else None,
            comment=str(comment or ""),
            errors=errors,
            line_label=f"item {index}",
            groups=split_group_names(item.get("groups", item.get("group", ""))),
        )
        if len(bucket) >= MAX_IMPORT_TARGETS and any(
            "limited to" in entry for entry in errors
        ):
            break

    return ImportParseResult(targets=list(bucket.values()), errors=errors)


def parse_import_payload(*, filename: str, raw: bytes) -> ImportParseResult:
    if len(raw) > MAX_IMPORT_BYTES:
        return ImportParseResult(
            targets=[],
            errors=[
                f"File exceeds the {MAX_IMPORT_BYTES // (1024 * 1024)} MiB limit."
            ],
        )
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return ImportParseResult(
            targets=[],
            errors=["File must be UTF-8 text."],
        )

    lower = filename.lower()
    stripped = content.lstrip()
    if lower.endswith(".json") or stripped.startswith("{") or stripped.startswith("["):
        return parse_json(content)
    if lower.endswith(".csv") or (
        "\n" in content and "," in content.splitlines()[0]
        and any(
            header in content.splitlines()[0].lower()
            for header in ("value", "address", "host", "target")
        )
    ):
        return parse_csv(content)
    return parse_plaintext(content)
