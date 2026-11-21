from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from celery import shared_task
from django.conf import settings

from .runner import ScanCancelled, ScanRunnerError, execute_scan


class TransientWorkerAPIError(RuntimeError):
    pass


class WorkerAPIError(RuntimeError):
    pass


def _api_request(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base_url = settings.API_INTERNAL_URL.rstrip("/")
    data = (
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
        if payload is not None
        else None
    )
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Worker-Token": settings.WORKER_TOKEN,
        },
    )

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                body = response.read(2 * 1024 * 1024 + 1)
                if len(body) > 2 * 1024 * 1024:
                    raise WorkerAPIError("Internal API response is too large.")
                decoded = json.loads(body or b"{}")
                if not isinstance(decoded, dict):
                    raise WorkerAPIError("Internal API returned an invalid response.")
                return decoded
        except urllib.error.HTTPError as exc:
            detail = exc.read(4096).decode("utf-8", errors="replace")
            if exc.code >= 500:
                last_error = exc
            else:
                raise WorkerAPIError(
                    f"Internal API returned HTTP {exc.code}: {detail}"
                ) from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last_error = exc
        except json.JSONDecodeError as exc:
            raise WorkerAPIError("Internal API returned invalid JSON.") from exc

        if attempt < 2:
            time.sleep(0.5 * (2**attempt))

    raise TransientWorkerAPIError(
        f"Internal API communication failed: {last_error}"
    ) from last_error


@shared_task(
    bind=True,
    name="scans.execute_batch",
    autoretry_for=(TransientWorkerAPIError,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=5,
    acks_late=True,
)
def execute_batch(self, batch_id: int, delivery_id: str) -> dict[str, Any]:
    identity = {"delivery_id": delivery_id}
    job = _api_request(
        "POST",
        f"/api/internal/batches/{batch_id}/claim/",
        identity,
    )
    if job.get("terminal"):
        return {"status": job.get("status", "terminal")}

    cancellation_cache = {"checked": 0.0, "cancelled": False}

    def should_cancel() -> bool:
        now = time.monotonic()
        if now - cancellation_cache["checked"] < 2:
            return bool(cancellation_cache["cancelled"])
        query = urllib.parse.urlencode({"delivery_id": delivery_id})
        response = _api_request(
            "GET",
            f"/api/internal/batches/{batch_id}/cancel-check/?{query}",
        )
        cancellation_cache["checked"] = now
        cancellation_cache["cancelled"] = bool(response.get("cancel_requested"))
        return bool(cancellation_cache["cancelled"])

    def report_progress(progress: int) -> None:
        _api_request(
            "POST",
            f"/api/internal/batches/{batch_id}/progress/",
            {**identity, "progress": progress},
        )

    try:
        result = execute_scan(
            job,
            should_cancel=should_cancel,
            report_progress=report_progress,
        )
    except ScanCancelled as exc:
        _api_request(
            "POST",
            f"/api/internal/batches/{batch_id}/fail/",
            {**identity, "error": str(exc), "cancelled": True},
        )
        return {"status": "cancelled"}
    except ScanRunnerError as exc:
        _api_request(
            "POST",
            f"/api/internal/batches/{batch_id}/fail/",
            {**identity, "error": str(exc), "cancelled": False},
        )
        return {"status": "failed"}
    except TransientWorkerAPIError:
        raise
    except Exception as exc:
        _api_request(
            "POST",
            f"/api/internal/batches/{batch_id}/fail/",
            {
                **identity,
                "error": f"Unexpected worker error: {type(exc).__name__}",
                "cancelled": False,
            },
        )
        return {"status": "failed"}

    _api_request(
        "POST",
        f"/api/internal/batches/{batch_id}/complete/",
        {**identity, "result": result},
    )
    return {"status": "completed"}
