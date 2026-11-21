from __future__ import annotations

import ipaddress
import json
import os
import signal
import socket
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from typing import Any

from .validation import normalize_target

FAST_PORTS = (
    "21,22,23,25,53,80,110,111,135,139,143,443,445,465,587,993,995,"
    "1433,1521,2049,3306,3389,5432,5900,6379,8000,8080,8443,8888,"
    "9200,27017"
)
WEB_PORTS = "80,443,3000,5000,7001,8000,8080,8443,8888,9000,9443"
HTTP_PORTS = {80, 443, 3000, 5000, 7001, 8000, 8080, 8443, 8888, 9000, 9443}
TLS_PORTS = {443, 8443, 9443}
MAX_COMMAND_OUTPUT = 2 * 1024 * 1024
MAX_RESULT_BYTES = 1800 * 1024
MAX_OBSERVATIONS = 2000
COMMAND_TIMEOUT_SECONDS = 180
TERMINATE_GRACE_SECONDS = 5


class ScanRunnerError(RuntimeError):
    pass


class ScanCancelled(ScanRunnerError):
    pass


def _terminate_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=TERMINATE_GRACE_SECONDS)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()


def _run_command(
    arguments: list[str],
    *,
    input_data: bytes | None,
    should_cancel: Callable[[], bool],
    timeout: int = COMMAND_TIMEOUT_SECONDS,
) -> tuple[bytes, bytes]:
    started = time.monotonic()
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        process = subprocess.Popen(
            arguments,
            stdin=subprocess.PIPE if input_data is not None else subprocess.DEVNULL,
            stdout=stdout_file,
            stderr=stderr_file,
            start_new_session=True,
            shell=False,
        )
        if input_data is not None and process.stdin is not None:
            try:
                process.stdin.write(input_data)
                process.stdin.close()
            except BrokenPipeError:
                pass

        try:
            while process.poll() is None:
                if should_cancel():
                    _terminate_process(process)
                    raise ScanCancelled("Scan cancellation requested.")
                if time.monotonic() - started > timeout:
                    _terminate_process(process)
                    raise ScanRunnerError(
                        f"Command exceeded the {timeout}-second timeout."
                    )
                if (
                    os.fstat(stdout_file.fileno()).st_size > MAX_COMMAND_OUTPUT
                    or os.fstat(stderr_file.fileno()).st_size > MAX_COMMAND_OUTPUT
                ):
                    _terminate_process(process)
                    raise ScanRunnerError("Command output exceeded the 2 MiB limit.")
                time.sleep(0.25)
        except BaseException:
            _terminate_process(process)
            raise

        stdout_file.seek(0)
        stderr_file.seek(0)
        output = stdout_file.read(MAX_COMMAND_OUTPUT + 1)
        error = stderr_file.read(MAX_COMMAND_OUTPUT + 1)
        if len(output) > MAX_COMMAND_OUTPUT or len(error) > MAX_COMMAND_OUTPUT:
            raise ScanRunnerError("Command output exceeded the 2 MiB limit.")
        if process.returncode != 0:
            detail = error.decode("utf-8", errors="replace")[-1000:].strip()
            raise ScanRunnerError(
                f"{arguments[0]} exited with code {process.returncode}: {detail}"
            )
        return output, error


def _supports_syn_scan() -> bool:
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_TCP)
        probe.close()
        return True
    except OSError:
        return False


def _module_map(modules: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {module["id"]: module["filters"] for module in modules}


def _port_profile(name: str, custom: str | None = None) -> str | None:
    if name == "discovery-fast":
        return FAST_PORTS
    if name == "discovery-web":
        return WEB_PORTS
    if name == "discovery-full":
        return None
    if name == "custom":
        return custom
    raise ScanRunnerError("Unsupported port profile.")


def _nmap_arguments(
    address: str,
    target_type: str,
    selected: dict[str, dict[str, Any]],
) -> tuple[list[str], str]:
    arguments = ["nmap"]
    try:
        is_ipv6 = (
            ipaddress.ip_address(address).version == 6
            if target_type == "ip"
            else target_type == "cidr"
            and ipaddress.ip_network(address).version == 6
        )
    except ValueError as exc:
        raise ScanRunnerError("Invalid IP target.") from exc
    if is_ipv6:
        arguments.append("-6")

    full = selected.get("full-pipeline")
    host = selected.get("host-discovery")
    port = selected.get("port-scan")
    service_enabled = "service-detect" in selected or full is not None
    http_phase = bool(
        {"http-fingerprint", "tls-cert", "signatures"} & set(selected)
    )
    has_port_phase = port is not None or service_enabled or full is not None or http_phase
    scan_mode = "syn" if _supports_syn_scan() else "connect"

    if not has_port_phase:
        arguments.append("-sn")
        method = host["method"] if host else "icmp-tcp"
        if method in {"icmp", "icmp-tcp"}:
            arguments.append("-PE")
        if method in {"tcp", "icmp-tcp"}:
            arguments.append(f"-PS{host['tcpPorts'] if host else '80,443'}")
        if host:
            arguments.extend(["--host-timeout", f"{host['timeoutSec']}s"])
    else:
        arguments.extend(["-Pn", "-sS" if scan_mode == "syn" else "-sT"])
        if full:
            ports = _port_profile(full["portProfile"])
            timing = "T3"
            max_rate = 200
        elif port:
            ports = _port_profile(port["profile"], port["customPorts"])
            timing = port["timing"]
            max_rate = port["maxRate"]
        elif http_phase:
            requested_ports: set[int] = set()
            if "http-fingerprint" in selected:
                requested_ports.update(
                    int(value)
                    for value in selected["http-fingerprint"]["ports"].split(",")
                )
            if "tls-cert" in selected:
                requested_ports.update(
                    int(value) for value in selected["tls-cert"]["ports"].split(",")
                )
            if not requested_ports:
                requested_ports.update(HTTP_PORTS)
            ports = ",".join(str(value) for value in sorted(requested_ports))
            timing = "T3"
            max_rate = 200
        else:
            ports = FAST_PORTS
            timing = "T3"
            max_rate = 200
        if ports is None:
            arguments.extend(["--top-ports", "1000"])
        else:
            arguments.extend(["-p", ports])
        arguments.extend([f"-{timing}", "--max-rate", str(max_rate)])
        if service_enabled:
            intensity = selected.get("service-detect", {}).get("intensity", 5)
            arguments.extend(["-sV", "--version-intensity", str(intensity)])

    arguments.extend(["--max-retries", "1", "-oX", "-", address])
    return arguments, scan_mode


def _parse_nmap(output: bytes) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(output)
    except ET.ParseError as exc:
        raise ScanRunnerError("nmap returned invalid XML.") from exc

    hosts: list[dict[str, Any]] = []
    for host_element in root.findall("host"):
        address_element = host_element.find("address")
        status_element = host_element.find("status")
        if address_element is None:
            continue
        host: dict[str, Any] = {
            "address": address_element.attrib.get("addr", ""),
            "state": status_element.attrib.get("state", "unknown")
            if status_element is not None
            else "unknown",
            "ports": [],
        }
        for port_element in host_element.findall("./ports/port"):
            state_element = port_element.find("state")
            if state_element is None or state_element.attrib.get("state") != "open":
                continue
            service_element = port_element.find("service")
            host["ports"].append(
                {
                    "port": int(port_element.attrib["portid"]),
                    "protocol": port_element.attrib.get("protocol", "tcp"),
                    "service": service_element.attrib.get("name", "")
                    if service_element is not None
                    else "",
                    "product": service_element.attrib.get("product", "")
                    if service_element is not None
                    else "",
                    "version": service_element.attrib.get("version", "")
                    if service_element is not None
                    else "",
                }
            )
        hosts.append(host)
        if len(hosts) >= MAX_OBSERVATIONS:
            break
    return hosts


def _http_endpoints(
    target: str,
    hosts: list[dict[str, Any]],
    selected: dict[str, dict[str, Any]],
) -> list[str]:
    http_filters = selected.get("http-fingerprint")
    tls_filters = selected.get("tls-cert")
    full = selected.get("full-pipeline")
    endpoints: set[str] = set()

    def endpoint_host(address: str) -> str:
        try:
            return f"[{address}]" if ipaddress.ip_address(address).version == 6 else address
        except ValueError:
            return address

    try:
        ipaddress.ip_address(target)
        target_is_domain = False
    except ValueError:
        target_is_domain = "/" not in target

    if hosts:
        for host in hosts:
            for port_data in host["ports"]:
                port = port_data["port"]
                service = port_data["service"].lower()
                if port not in HTTP_PORTS and service not in {
                    "http",
                    "https",
                    "ssl/http",
                    "http-proxy",
                }:
                    continue
                scheme = "https" if port in TLS_PORTS or "https" in service else "http"
                endpoint_address = target if target_is_domain else host["address"]
                endpoints.add(f"{scheme}://{endpoint_host(endpoint_address)}:{port}")
    else:
        if "/" in target or (full and full["stopOnHostDown"]):
            return []
        ports: set[int] = set()
        if http_filters:
            ports.update(int(value) for value in http_filters["ports"].split(","))
        if tls_filters:
            ports.update(int(value) for value in tls_filters["ports"].split(","))
        if full:
            ports.update((80, 443, 8080, 8443))
        schemes = http_filters["schemes"] if http_filters else "both"
        for port in ports:
            if schemes == "both":
                scheme = "https" if port in TLS_PORTS else "http"
            else:
                scheme = schemes
            endpoints.add(f"{scheme}://{endpoint_host(target)}:{port}")

    return sorted(endpoints)[:MAX_OBSERVATIONS]


def _httpx_arguments(selected: dict[str, dict[str, Any]]) -> list[str]:
    http_filters = selected.get("http-fingerprint", {})
    full = selected.get("full-pipeline")
    timeout = http_filters.get("timeoutSec", 5)
    rate_limit = http_filters.get("rateLimit", 50)
    arguments = [
        "httpx",
        "-silent",
        "-json",
        "-status-code",
        "-title",
        "-server",
        "-timeout",
        str(timeout),
        "-retries",
        "1",
        "-rate-limit",
        str(rate_limit),
        "-threads",
        "50",
    ]
    if http_filters.get("techDetect", full is not None):
        arguments.append("-tech-detect")
    if "tls-cert" in selected or (full and full["includeTls"]):
        arguments.append("-tls-grab")
    # Redirects are deliberately not followed: an HTTP Location can leave the saved target.
    return arguments


def _parse_httpx(output: bytes) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ScanRunnerError("httpx returned invalid JSONL.") from exc
        if not isinstance(record, dict):
            raise ScanRunnerError("httpx returned an invalid record.")
        records.append(record)
        if len(records) >= MAX_OBSERVATIONS:
            break
    return records


def _signature_results(http_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    try:
        from .signatures import match_http_records

        findings = match_http_records(http_records)
    except Exception:
        findings = []
    return findings[:MAX_OBSERVATIONS]


def execute_scan(
    job: dict[str, Any],
    *,
    should_cancel: Callable[[], bool],
    report_progress: Callable[[int, str], None],
) -> dict[str, Any]:
    target_data = job.get("target")
    modules = job.get("modules")
    if not isinstance(target_data, dict) or not isinstance(modules, list):
        raise ScanRunnerError("Worker job is missing target or modules.")
    target_type = target_data.get("type")
    try:
        target = normalize_target(target_data.get("address", ""), target_type)
    except ValueError as exc:
        raise ScanRunnerError(str(exc)) from exc

    selected = _module_map(modules)
    if should_cancel():
        raise ScanCancelled("Scan cancellation requested.")

    nmap_arguments, scan_mode = _nmap_arguments(target, target_type, selected)
    report_progress(
        5,
        f"Starting nmap ({scan_mode}) for {target}: {' '.join(nmap_arguments[:-1])} <target>",
    )
    nmap_output, _ = _run_command(
        nmap_arguments,
        input_data=None,
        should_cancel=should_cancel,
    )
    hosts = _parse_nmap(nmap_output)
    open_ports = sum(
        len(host.get("ports", []))
        for host in hosts
        if isinstance(host.get("ports"), list)
    )
    report_progress(
        55,
        f"nmap finished for {target}: {len(hosts)} host(s), {open_ports} open port(s).",
    )

    needs_http = bool(
        {"http-fingerprint", "tls-cert", "signatures", "full-pipeline"} & set(selected)
    )
    http_records: list[dict[str, Any]] = []
    endpoints: list[str] = []
    if needs_http:
        endpoints = _http_endpoints(target, hosts, selected)
        if endpoints:
            httpx_args = _httpx_arguments(selected)
            report_progress(
                60,
                f"Starting httpx for {len(endpoints)} endpoint(s): {' '.join(httpx_args)}",
            )
            httpx_output, _ = _run_command(
                httpx_args,
                input_data=("\n".join(endpoints) + "\n").encode("utf-8"),
                should_cancel=should_cancel,
            )
            http_records = _parse_httpx(httpx_output)
            report_progress(
                90,
                f"httpx finished for {target}: {len(http_records)} HTTP observation(s).",
            )
        else:
            report_progress(90, f"No HTTP endpoints to probe for {target}.")
    else:
        report_progress(90, f"HTTP fingerprinting skipped for {target}.")

    run_signatures = "signatures" in selected or bool(
        selected.get("full-pipeline", {}).get("includeSignatures")
    )
    if run_signatures:
        report_progress(95, f"Matching signatures against observations for {target}.")
    result = {
        "target": {"address": target, "type": target_type},
        "metadata": {
            "scan_mode": scan_mode,
            "nmap_arguments": nmap_arguments[:-1] + ["<target>"],
            "httpx_arguments": _httpx_arguments(selected) if needs_http else [],
            "redirects_followed": False,
        },
        "hosts": hosts,
        "http": http_records,
        "signatures": _signature_results(http_records) if run_signatures else [],
        "endpoint_count": len(endpoints),
    }
    if len(json.dumps(result, separators=(",", ":")).encode("utf-8")) > MAX_RESULT_BYTES:
        raise ScanRunnerError("Normalized result exceeded the 1.8 MiB limit.")
    report_progress(100, f"Normalized results ready for {target}.")
    return result
