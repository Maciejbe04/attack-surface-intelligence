import { apiFetch } from "../auth";
import { ModuleFilterValues } from "../modules";

export type TargetType = "ip" | "cidr" | "domain";

export type Target = {
  id: number;
  address: string;
  type: TargetType;
  comment: string;
  created_at: string;
  updated_at: string;
};

export type ScanStatus =
  | "queued"
  | "running"
  | "cancel_requested"
  | "completed"
  | "partial"
  | "failed"
  | "cancelled";

export type ScanModule = {
  id: string;
  filters: ModuleFilterValues;
};

export type ScanBatch = {
  id: number;
  target_address: string;
  target_type: TargetType;
  status: Exclude<ScanStatus, "cancel_requested" | "partial">;
  progress: number;
  result: unknown;
  error: string;
  created_at: string;
  claimed_at: string | null;
  finished_at: string | null;
};

export type ScanEventLevel = "info" | "warn" | "error";

export type ScanEvent = {
  id: number;
  batch_id: number | null;
  target_address: string | null;
  level: ScanEventLevel;
  source: string;
  message: string;
  created_at: string;
};

export type DefectDojoExportStatus =
  | "none"
  | "pending"
  | "sending"
  | "sent"
  | "failed"
  | "skipped";

export type Scan = {
  id: number;
  status: ScanStatus;
  modules: ScanModule[];
  targets: string[];
  client_request_id: string;
  total_batches: number;
  completed_batches: number;
  failed_batches: number;
  progress: number;
  result_summary: Record<string, unknown>;
  error: string;
  defectdojo_export_status: DefectDojoExportStatus;
  defectdojo_export_detail: string;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type ScanDetail = Scan & {
  batches: ScanBatch[];
  events: ScanEvent[];
};

export type CreateScanRequest = {
  target_ids: number[];
  modules: ScanModule[];
  client_request_id: string;
};

export type DefectDojoExportResult = {
  finding_count: number;
  test: number | null;
  message: string;
};

export class ApiError extends Error {
  readonly status: number;
  readonly details: unknown;

  constructor(message: string, status: number, details: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

function firstError(value: unknown): string | null {
  if (typeof value === "string" && value.trim()) return value;
  if (Array.isArray(value)) {
    for (const item of value) {
      const message = firstError(item);
      if (message) return message;
    }
  }
  if (value && typeof value === "object") {
    const record = value as Record<string, unknown>;
    const detail = firstError(record.detail);
    if (detail) return detail;
    for (const [key, item] of Object.entries(record)) {
      if (key === "detail") continue;
      const message = firstError(item);
      if (message) return `${key}: ${message}`;
    }
  }
  return null;
}

async function request<T>(url: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await apiFetch(url, init);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError("Cannot reach the SurfaceX API.", 0, error);
  }

  const contentType = response.headers.get("content-type") ?? "";
  let body: unknown = null;
  if (response.status !== 204) {
    try {
      body = contentType.includes("application/json")
        ? await response.json()
        : await response.text();
    } catch {
      body = null;
    }
  }

  if (!response.ok) {
    throw new ApiError(
      firstError(body) ?? `Request failed with HTTP ${response.status}.`,
      response.status,
      body,
    );
  }
  return body as T;
}

export function apiErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) return error.message;
  return fallback;
}

export function listTargets(signal?: AbortSignal): Promise<Target[]> {
  return request<Target[]>("/api/targets/", { signal });
}

export function createTarget(
  target: Pick<Target, "address" | "type" | "comment">,
  signal?: AbortSignal,
): Promise<Target> {
  return request<Target>("/api/targets/", {
    method: "POST",
    body: JSON.stringify(target),
    signal,
  });
}

export type TargetImportResult = {
  created_count: number;
  existing_count: number;
  total_count: number;
  parse_errors: string[];
  skipped_duplicates_in_file: number;
  target_ids: number[];
  targets: Target[];
  scan: ScanDetail | null;
};

export async function importTargetsFile(
  file: File,
  options: {
    startScan?: boolean;
    modules?: ScanModule[];
    clientRequestId?: string;
  } = {},
  signal?: AbortSignal,
): Promise<TargetImportResult> {
  const body = new FormData();
  body.append("file", file);
  body.append("start_scan", options.startScan === false ? "false" : "true");
  if (options.modules) {
    body.append("modules", JSON.stringify(options.modules));
  }
  if (options.clientRequestId) {
    body.append("client_request_id", options.clientRequestId);
  }

  let response: Response;
  try {
    response = await apiFetch("/api/targets/import/", {
      method: "POST",
      body,
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError("Cannot reach the SurfaceX API.", 0, error);
  }

  const contentType = response.headers.get("content-type") ?? "";
  let payload: unknown = null;
  try {
    payload = contentType.includes("application/json")
      ? await response.json()
      : await response.text();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    throw new ApiError(
      firstError(payload) ?? `Request failed with HTTP ${response.status}.`,
      response.status,
      payload,
    );
  }
  return payload as TargetImportResult;
}

export function deleteTarget(id: number, signal?: AbortSignal): Promise<void> {
  return request<void>(`/api/targets/${id}/`, { method: "DELETE", signal });
}

export function listScans(signal?: AbortSignal): Promise<Scan[]> {
  return request<Scan[]>("/api/scans/", { signal });
}

export function getScan(id: number, signal?: AbortSignal): Promise<ScanDetail> {
  return request<ScanDetail>(`/api/scans/${id}/`, { signal });
}

export function createScan(payload: CreateScanRequest, signal?: AbortSignal): Promise<ScanDetail> {
  return request<ScanDetail>("/api/scans/", {
    method: "POST",
    body: JSON.stringify(payload),
    signal,
  });
}

export function cancelScan(id: number, signal?: AbortSignal): Promise<ScanDetail> {
  return request<ScanDetail>(`/api/scans/${id}/cancel/`, {
    method: "POST",
    body: "{}",
    signal,
  });
}

export function exportScanToDefectDojo(
  id: number,
  signal?: AbortSignal,
): Promise<DefectDojoExportResult> {
  return request<DefectDojoExportResult>(
    `/api/scans/${id}/export/defectdojo/`,
    {
      method: "POST",
      body: "{}",
      signal,
    },
  );
}

export const ACTIVE_SCAN_STATUSES = new Set<ScanStatus>([
  "queued",
  "running",
  "cancel_requested",
]);
