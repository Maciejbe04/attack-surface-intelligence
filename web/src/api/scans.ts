import { apiFetch, emitSessionExpired } from "../auth";
import { ModuleFilterValues } from "../modules";

export type TargetType = "ip" | "cidr" | "domain";

export type TargetGroupRef = {
  id: number;
  name: string;
};

export type Target = {
  id: number;
  address: string;
  type: TargetType;
  comment: string;
  groups: TargetGroupRef[];
  created_at: string;
  updated_at: string;
};

export type ScheduleFrequency = "hourly" | "daily" | "weekly";

export type GroupSchedule = {
  enabled: boolean;
  frequency: ScheduleFrequency;
  interval_hours: number;
  /** "HH:MM", UTC */
  time_of_day: string;
  /** 0 = Monday … 6 = Sunday */
  weekday: number;
  modules: ScanModule[];
  next_run_at: string | null;
  last_run_at: string | null;
  last_run_id: number | null;
  last_status: string;
};

export type GroupScheduleInput = Pick<
  GroupSchedule,
  "enabled" | "frequency" | "interval_hours" | "time_of_day" | "weekday" | "modules"
>;

export type TargetGroup = {
  id: number;
  name: string;
  description: string;
  owner: string;
  target_count: number;
  schedule: GroupSchedule | null;
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

export type ScanBatchStatus =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "cancelled"
  | "paused";

export type ScanBatch = {
  id: number;
  target_address: string;
  target_type: TargetType;
  status: ScanBatchStatus;
  progress: number;
  result: unknown;
  error: string;
  created_at: string;
  claimed_at: string | null;
  finished_at: string | null;
};

export type ObservationLifecycle =
  | "NEW"
  | "CHANGED"
  | "MISSING"
  | "FLAKY"
  | "GONE"
  | "UNCHANGED";

export type ObservationOverride = {
  id: number;
  entity_key: string;
  tags: string[];
  notes: string;
  attrs_patch: Record<string, unknown>;
  updated_at: string;
};

export type Observation = {
  id: number;
  entity_type: string;
  entity_key: string;
  lifecycle: ObservationLifecycle;
  target_address: string;
  attrs: Record<string, unknown>;
  effective_attrs?: Record<string, unknown>;
  tags?: string[];
  notes?: string;
  override?: ObservationOverride | null;
  source: string;
  miss_streak: number;
  evidence: Array<{ id: number; kind: string; summary: string; encrypted: boolean }>;
  created_at: string;
  updated_at: string;
};

export type AllowlistEntry = {
  id: number;
  value: string;
  type: "ip" | "cidr" | "domain";
  enabled: boolean;
  comment: string;
  created_at: string;
  updated_at: string;
};

export type AuditEvent = {
  id: number;
  actor: string | null;
  action: string;
  object_type: string;
  object_id: string;
  summary: string;
  created_at: string;
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

export type CuriosityHighlight = {
  id: string;
  severity: string;
  text: string;
  count: number;
};

export type CuriositySummary = {
  hosts_with_open_ports: number;
  open_ports_total: number;
  interesting_ports: number;
  interesting_port_examples?: Array<{
    address: string;
    port: number;
    protocol: string;
    service: string;
    sensitive?: boolean;
  }>;
  admin_or_login_hints: number;
  high_confidence_tech: number;
  expiring_certs: number;
  top_services?: Array<{ service: string; count: number }>;
  highlights: CuriosityHighlight[];
};

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
  result_summary: Record<string, unknown> & {
    lifecycle?: Partial<Record<ObservationLifecycle, number>>;
    curiosity?: CuriositySummary;
    paused?: number;
  };
  error: string;
  defectdojo_export_status: DefectDojoExportStatus;
  defectdojo_export_detail: string;
  group_id: number | null;
  group_name: string | null;
  scheduled: boolean;
  window_seconds: number | null;
  deadline_at: string | null;
  eta_seconds: number | null;
  resume_available: boolean;
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
  window_seconds?: number | null;
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
    const message = firstError(body) ?? `Request failed with HTTP ${response.status}.`;
    // Unauthenticated (lost session cookie) — not a normal RBAC denial.
    if (
      response.status === 401 ||
      (response.status === 403 &&
        /authentication credentials were not provided/i.test(message))
    ) {
      emitSessionExpired();
    }
    throw new ApiError(message, response.status, body);
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

/** Server-side typeahead: exact and prefix matches on the address come first. */
export function searchTargets(
  query: string,
  limit = 8,
  signal?: AbortSignal,
): Promise<Target[]> {
  const params = new URLSearchParams({ search: query, limit: String(limit) });
  return request<Target[]>(`/api/targets/?${params.toString()}`, { signal });
}

export function listGroups(signal?: AbortSignal): Promise<TargetGroup[]> {
  return request<TargetGroup[]>("/api/groups/", { signal });
}

export function createGroup(
  group: { name: string; description?: string },
  signal?: AbortSignal,
): Promise<TargetGroup> {
  return request<TargetGroup>("/api/groups/", {
    method: "POST",
    body: JSON.stringify(group),
    signal,
  });
}

export function updateGroup(
  id: number,
  patch: { name?: string; description?: string },
  signal?: AbortSignal,
): Promise<TargetGroup> {
  return request<TargetGroup>(`/api/groups/${id}/`, {
    method: "PATCH",
    body: JSON.stringify(patch),
    signal,
  });
}

export function deleteGroup(id: number, signal?: AbortSignal): Promise<void> {
  return request<void>(`/api/groups/${id}/`, { method: "DELETE", signal });
}

export function updateGroupMembers(
  id: number,
  action: "add" | "remove",
  targetIds: number[],
  signal?: AbortSignal,
): Promise<TargetGroup & { changed_count: number }> {
  return request<TargetGroup & { changed_count: number }>(`/api/groups/${id}/targets/`, {
    method: "POST",
    body: JSON.stringify({ action, target_ids: targetIds }),
    signal,
  });
}

export function scanGroup(
  id: number,
  modules: ScanModule[],
  clientRequestId: string,
  signal?: AbortSignal,
  windowSeconds?: number | null,
): Promise<ScanDetail> {
  const body: Record<string, unknown> = {
    modules,
    client_request_id: clientRequestId,
  };
  if (windowSeconds != null && windowSeconds > 0) {
    body.window_seconds = windowSeconds;
  }
  return request<ScanDetail>(`/api/groups/${id}/scan/`, {
    method: "POST",
    body: JSON.stringify(body),
    signal,
  });
}

export function saveGroupSchedule(
  id: number,
  schedule: GroupScheduleInput,
  signal?: AbortSignal,
): Promise<TargetGroup> {
  return request<TargetGroup>(`/api/groups/${id}/schedule/`, {
    method: "PUT",
    body: JSON.stringify(schedule),
    signal,
  });
}

export function deleteGroupSchedule(id: number, signal?: AbortSignal): Promise<TargetGroup> {
  return request<TargetGroup>(`/api/groups/${id}/schedule/`, { method: "DELETE", signal });
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
  groups: (TargetGroupRef & { created: boolean; added_count: number })[];
  scan: ScanDetail | null;
};

export async function importTargetsFile(
  file: File,
  options: {
    startScan?: boolean;
    modules?: ScanModule[];
    clientRequestId?: string;
    /** Put every imported host into this existing group … */
    groupId?: number;
    /** … or into a group with this name (created when missing). */
    groupName?: string;
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
  if (options.groupId !== undefined) {
    body.append("group_id", String(options.groupId));
  } else if (options.groupName) {
    body.append("group_name", options.groupName);
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

export function resumeScan(id: number, signal?: AbortSignal): Promise<ScanDetail> {
  return request<ScanDetail>(`/api/scans/${id}/resume/`, {
    method: "POST",
    body: "{}",
    signal,
  });
}

export function listObservations(
  id: number,
  params?: { lifecycle?: string; entity_type?: string },
  signal?: AbortSignal,
): Promise<{
  run_id: number;
  count: number;
  lifecycle_summary: Partial<Record<ObservationLifecycle, number>>;
  results: Observation[];
}> {
  const query = new URLSearchParams();
  if (params?.lifecycle) query.set("lifecycle", params.lifecycle);
  if (params?.entity_type) query.set("entity_type", params.entity_type);
  const suffix = query.toString() ? `?${query}` : "";
  return request(`/api/scans/${id}/observations/${suffix}`, { signal });
}

export type ScanDiffObservation = {
  id: number;
  entity_type: string;
  entity_key: string;
  lifecycle: ObservationLifecycle;
  target_address: string;
  attrs: Record<string, unknown>;
  miss_streak: number;
};

export type ScanDiffChange = {
  entity_key: string;
  entity_type?: string;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
  lifecycle: ObservationLifecycle;
};

export type ScanDiff = {
  current_run_id: number;
  against_run_id: number | null;
  modules?: string[];
  added: ScanDiffObservation[];
  removed: ScanDiffObservation[];
  changed: ScanDiffChange[];
  counts: {
    added: number;
    removed: number;
    changed: number;
  };
  detail?: string;
};

export function getScanDiff(
  id: number,
  againstId?: number | null,
  signal?: AbortSignal,
): Promise<ScanDiff> {
  const query = new URLSearchParams();
  if (againstId != null) query.set("against", String(againstId));
  const suffix = query.toString() ? `?${query}` : "";
  return request<ScanDiff>(`/api/scans/${id}/diff/${suffix}`, { signal });
}

export function listAudit(signal?: AbortSignal): Promise<{ results: AuditEvent[] }> {
  return request<{ results: AuditEvent[] }>("/api/audit/", { signal });
}

export function upsertOverride(
  payload: {
    entity_key: string;
    target_address?: string;
    tags?: string[];
    notes?: string;
    attrs_patch?: Record<string, unknown>;
  },
  signal?: AbortSignal,
): Promise<ObservationOverride> {
  return request<ObservationOverride>("/api/overrides/", {
    method: "POST",
    body: JSON.stringify(payload),
    signal,
  });
}

export function deleteOverride(id: number, signal?: AbortSignal): Promise<void> {
  return request<void>(`/api/overrides/${id}/`, { method: "DELETE", signal });
}

export function listAllowlist(
  signal?: AbortSignal,
): Promise<{ enforced: boolean; results: AllowlistEntry[] }> {
  return request<{ enforced: boolean; results: AllowlistEntry[] }>("/api/allowlist/", {
    signal,
  });
}

export function createAllowlistEntry(
  entry: { value: string; type: AllowlistEntry["type"]; comment?: string },
  signal?: AbortSignal,
): Promise<AllowlistEntry> {
  return request<AllowlistEntry>("/api/allowlist/", {
    method: "POST",
    body: JSON.stringify(entry),
    signal,
  });
}

export function deleteAllowlistEntry(id: number, signal?: AbortSignal): Promise<void> {
  return request<void>(`/api/allowlist/${id}/`, { method: "DELETE", signal });
}

export async function downloadScanExport(
  id: number,
  format: "json" | "csv",
  signal?: AbortSignal,
): Promise<void> {
  const response = await apiFetch(`/api/scans/${id}/export/?format=${format}`, { signal });
  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      body = null;
    }
    throw new ApiError(
      firstError(body) ?? `Export failed with HTTP ${response.status}.`,
      response.status,
      body,
    );
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `scan-${id}.${format}`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export const ACTIVE_SCAN_STATUSES = new Set<ScanStatus>([
  "queued",
  "running",
  "cancel_requested",
]);
