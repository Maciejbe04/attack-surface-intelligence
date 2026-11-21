import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  apiErrorMessage,
  downloadScanExport,
  getScanDiff,
  listObservations,
  Observation,
  ObservationLifecycle,
  resumeScan,
  Scan,
  ScanDiff,
  ScanDiffChange,
  ScanDiffObservation,
  upsertOverride,
} from "./api/scans";
import { CuriosityInsights } from "./CuriosityInsights";
import { Translate } from "./i18n";

const LIFECYCLES: Array<ObservationLifecycle | ""> = [
  "",
  "NEW",
  "CHANGED",
  "MISSING",
  "FLAKY",
  "GONE",
  "UNCHANGED",
];

const PREVIOUS = "";

function formatEta(seconds: number | null | undefined): string {
  if (seconds == null || seconds < 0) return "";
  if (seconds < 60) return `~${seconds}s`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `~${minutes}m`;
  return `~${Math.round(minutes / 60)}h`;
}

function attrsPreview(attrs: Record<string, unknown>): string {
  const parts: string[] = [];
  for (const key of ["technology", "level", "confidence", "port", "status_code", "title", "server", "state"]) {
    if (attrs[key] != null && attrs[key] !== "") {
      parts.push(`${key}=${String(attrs[key])}`);
    }
  }
  return parts.slice(0, 4).join(" · ") || "—";
}

type CuriosityLevel = "high" | "medium" | "low" | "info";

function curiosityFromAttrs(attrs: Record<string, unknown> | undefined): CuriosityLevel | null {
  if (!attrs || attrs.curiosity == null || attrs.curiosity === "") return null;
  const raw = attrs.curiosity;
  if (typeof raw === "number") {
    if (raw === 3) return "high";
    if (raw === 2) return "medium";
    if (raw === 1) return "info";
    return null;
  }
  const value = String(raw).trim().toLowerCase();
  if (value === "high" || value === "medium" || value === "low" || value === "info") {
    return value;
  }
  if (value === "3") return "high";
  if (value === "2") return "medium";
  if (value === "1") return "info";
  return null;
}

function CuriosityBadge({ value, t }: { value: CuriosityLevel | null; t: Translate }) {
  if (value == null) return <span className="field-help">—</span>;
  const label =
    value === "high"
      ? t("high")
      : value === "medium"
        ? t("medium")
        : value === "low"
          ? t("low")
          : t("info");
  return (
    <span
      className={`curiosity-badge curiosity-badge--${value}`}
      title={t("Curiosity: high / medium / low / info")}
    >
      {label}
    </span>
  );
}

function attrDiffLines(before: Record<string, unknown>, after: Record<string, unknown>): string[] {
  const keys = Array.from(new Set([...Object.keys(before), ...Object.keys(after)])).sort();
  const lines: string[] = [];
  for (const key of keys) {
    if (key === "curiosity") continue;
    const left = before[key];
    const right = after[key];
    if (JSON.stringify(left) === JSON.stringify(right)) continue;
    lines.push(`${key}: ${left == null ? "—" : String(left)} → ${right == null ? "—" : String(right)}`);
  }
  return lines;
}

type DiffRow =
  | { kind: "added" | "removed"; item: ScanDiffObservation }
  | { kind: "changed"; item: ScanDiffChange };

type DiffMethod = "host" | "port" | "http" | "tls" | "tech" | "signatures" | "other";

const DIFF_METHOD_ORDER: DiffMethod[] = [
  "host",
  "port",
  "http",
  "tls",
  "tech",
  "signatures",
  "other",
];

function diffMethodFromKey(entityKey: string, entityType?: string): DiffMethod {
  const type = (entityType || "").toLowerCase();
  if (type === "host" || entityKey.startsWith("host:")) return "host";
  if (type === "port" || entityKey.startsWith("port:")) return "port";
  if (type === "http" || entityKey.startsWith("http:")) return "http";
  if (type === "cert" || entityKey.startsWith("cert:")) return "tls";
  if (type === "tech" || entityKey.startsWith("tech:")) return "tech";
  if (type === "signature" || entityKey.startsWith("sig:") || entityKey.startsWith("signature:")) {
    return "signatures";
  }
  return "other";
}

function moduleIds(scan: Scan): string[] {
  return [...(scan.modules || [])]
    .map((module) => module.id)
    .filter(Boolean)
    .sort();
}

function sameModules(left: Scan, right: Scan): boolean {
  const a = moduleIds(left);
  const b = moduleIds(right);
  return a.length === b.length && a.every((value, index) => value === b[index]);
}

type Props = {
  scan: Scan | null;
  scans?: Scan[];
  canMutate: boolean;
  canExport: boolean;
  onScanUpdated: (scan: Scan) => void;
  pushToast: (kind: "ok" | "error", title: string, message: string) => void;
  t: Translate;
};

export function FindingsPanel({
  scan,
  scans = [],
  canMutate,
  canExport,
  onScanUpdated,
  pushToast,
  t,
}: Props) {
  const [lifecycle, setLifecycle] = useState<ObservationLifecycle | "">("");
  const [rows, setRows] = useState<Observation[]>([]);
  const [summary, setSummary] = useState<Partial<Record<ObservationLifecycle, number>>>({});
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editNotes, setEditNotes] = useState("");
  const [editTags, setEditTags] = useState("");
  const [editTech, setEditTech] = useState("");
  const [compareMode, setCompareMode] = useState(false);
  const [againstId, setAgainstId] = useState<string>(PREVIOUS);
  const [diff, setDiff] = useState<ScanDiff | null>(null);
  const [diffLoading, setDiffLoading] = useState(false);

  const againstOptions = useMemo(() => {
    if (!scan) return [];
    const finished = (item: Scan) =>
      Boolean(item.finished_at) &&
      (item.status === "completed" || item.status === "partial" || item.status === "failed");
    const sameTargets = (item: Scan) => {
      const left = [...(scan.targets || [])].map((v) => v.toLowerCase()).sort();
      const right = [...(item.targets || [])].map((v) => v.toLowerCase()).sort();
      if (left.length === 0 || right.length === 0) return false;
      return left.length === right.length && left.every((value, index) => value === right[index]);
    };
    return scans.filter((item) => {
      if (item.id === scan.id || !finished(item)) return false;
      if (!sameModules(scan, item)) return false;
      if (scan.group_id != null) {
        return item.group_id === scan.group_id;
      }
      // Host / ad-hoc scan: same modules and the same target host set.
      return item.group_id == null && sameTargets(item);
    });
  }, [scan, scans]);

  useEffect(() => {
    setCompareMode(false);
    setAgainstId(PREVIOUS);
    setDiff(null);
    setEditingKey(null);
  }, [scan?.id]);

  useEffect(() => {
    if (againstId === PREVIOUS) return;
    if (!againstOptions.some((item) => String(item.id) === againstId)) {
      setAgainstId(PREVIOUS);
    }
  }, [againstId, againstOptions]);

  useEffect(() => {
    if (!scan || !scan.finished_at || compareMode) {
      if (!scan || !scan.finished_at) {
        setRows([]);
        setSummary({});
      }
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    listObservations(
      scan.id,
      lifecycle ? { lifecycle } : undefined,
      controller.signal,
    )
      .then((payload) => {
        if (controller.signal.aborted) return;
        setRows(payload.results);
        setSummary(payload.lifecycle_summary || {});
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (error instanceof DOMException && error.name === "AbortError") return;
        // Auth loss is handled globally; avoid toast+rerender fetch storms.
        if (error instanceof ApiError && (error.status === 401 || error.status === 403)) return;
        pushToast("error", t("Findings unavailable"), apiErrorMessage(error, t("Could not load findings.")));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
    // pushToast/t are stable enough via parent useCallback; omit to avoid refetch loops.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional
  }, [scan?.id, scan?.finished_at, lifecycle, compareMode]);

  useEffect(() => {
    if (!scan || !scan.finished_at || !compareMode) {
      if (!compareMode) setDiff(null);
      return;
    }
    const controller = new AbortController();
    setDiffLoading(true);
    const against = againstId === PREVIOUS ? null : Number(againstId);
    getScanDiff(scan.id, against, controller.signal)
      .then((payload) => {
        if (controller.signal.aborted) return;
        setDiff(payload);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (error instanceof DOMException && error.name === "AbortError") return;
        if (error instanceof ApiError && (error.status === 401 || error.status === 403)) return;
        setDiff(null);
        pushToast("error", t("Compare unavailable"), apiErrorMessage(error, t("Could not load scan diff.")));
      })
      .finally(() => {
        if (!controller.signal.aborted) setDiffLoading(false);
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional
  }, [scan?.id, scan?.finished_at, compareMode, againstId]);

  const diffRows: DiffRow[] = useMemo(() => {
    if (!diff) return [];
    return [
      ...diff.added.map((item) => ({ kind: "added" as const, item })),
      ...diff.removed.map((item) => ({ kind: "removed" as const, item })),
      ...diff.changed.map((item) => ({ kind: "changed" as const, item })),
    ];
  }, [diff]);

  const diffGroups = useMemo(() => {
    const buckets = new Map<DiffMethod, DiffRow[]>();
    for (const method of DIFF_METHOD_ORDER) buckets.set(method, []);
    for (const row of diffRows) {
      const entityKey = row.item.entity_key;
      const entityType =
        row.kind === "changed" ? row.item.entity_type : row.item.entity_type;
      const method = diffMethodFromKey(entityKey, entityType);
      buckets.get(method)!.push(row);
    }
    return DIFF_METHOD_ORDER.map((method) => ({
      method,
      rows: buckets.get(method) || [],
    })).filter((group) => group.rows.length > 0);
  }, [diffRows]);

  function methodLabel(method: DiffMethod): string {
    if (method === "host") return t("Hosts");
    if (method === "port") return t("Ports");
    if (method === "http") return t("HTTP");
    if (method === "tls") return t("TLS");
    if (method === "tech") return t("Technology");
    if (method === "signatures") return t("Signatures");
    return t("Other");
  }

  if (!scan) return null;

  const lifecycleFromScan = scan.result_summary?.lifecycle || summary;
  const finished = Boolean(scan.finished_at);

  async function onExport(format: "json" | "csv") {
    setBusy(true);
    try {
      await downloadScanExport(scan!.id, format);
      pushToast("ok", t("Export ready"), `scan-${scan!.id}.${format}`);
    } catch (error) {
      pushToast("error", t("Export failed"), apiErrorMessage(error, t("Could not export scan.")));
    } finally {
      setBusy(false);
    }
  }

  async function onResume() {
    setBusy(true);
    try {
      const updated = await resumeScan(scan!.id);
      onScanUpdated(updated);
      pushToast("ok", t("Scan resumed"), `#${updated.id}`);
    } catch (error) {
      pushToast("error", t("Resume failed"), apiErrorMessage(error, t("Could not resume scan.")));
    } finally {
      setBusy(false);
    }
  }

  function openOverride(row: Observation) {
    setEditingKey(row.entity_key);
    setEditNotes(row.notes || "");
    setEditTags((row.tags || []).join(", "));
    const attrs = row.effective_attrs || row.attrs || {};
    setEditTech(attrs.technology != null ? String(attrs.technology) : "");
  }

  async function onSaveOverride(event: FormEvent) {
    event.preventDefault();
    if (!editingKey || !canExport) return;
    const row = rows.find((item) => item.entity_key === editingKey);
    if (!row) return;
    setBusy(true);
    try {
      const tags = editTags
        .split(",")
        .map((part) => part.trim())
        .filter(Boolean);
      const attrs_patch: Record<string, unknown> = {};
      if (editTech.trim()) attrs_patch.technology = editTech.trim();
      const updated = await upsertOverride({
        entity_key: row.entity_key,
        target_address: row.target_address,
        tags,
        notes: editNotes,
        attrs_patch,
      });
      setRows((prev) =>
        prev.map((item) =>
          item.entity_key === row.entity_key
            ? {
                ...item,
                override: updated,
                tags: updated.tags,
                notes: updated.notes,
                effective_attrs: {
                  ...(item.attrs || {}),
                  ...(updated.attrs_patch || {}),
                },
              }
            : item,
        ),
      );
      setEditingKey(null);
      pushToast("ok", t("Override saved"), row.entity_key);
    } catch (error) {
      pushToast(
        "error",
        t("Override not saved"),
        apiErrorMessage(error, t("Could not save the override.")),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {finished && (
        <CuriosityInsights
          curiosity={scan.result_summary?.curiosity}
          scanId={scan.id}
          t={t}
        />
      )}
    <section className="panel">
      <div className="panel__header">
        <h2>{t("Findings / Changes")}</h2>
        <div className="panel__actions">
          {scan.resume_available && canMutate && (
            <button type="button" className="btn btn--normal" disabled={busy} onClick={() => void onResume()}>
              {t("Resume")}
            </button>
          )}
          {finished && (
            <button
              type="button"
              className="btn btn--normal"
              aria-pressed={compareMode}
              disabled={busy}
              onClick={() => setCompareMode((value) => !value)}
            >
              {compareMode ? t("Hide compare") : t("Compare")}
            </button>
          )}
          {finished && canExport && (
            <>
              <button type="button" className="btn btn--normal" disabled={busy} onClick={() => void onExport("json")}>
                {t("Export JSON")}
              </button>
              <button type="button" className="btn btn--normal" disabled={busy} onClick={() => void onExport("csv")}>
                {t("Export CSV")}
              </button>
            </>
          )}
        </div>
      </div>
      <div className="panel__body">
        {!compareMode && (
          <div className="findings-kpis">
            {(["NEW", "CHANGED", "GONE"] as ObservationLifecycle[]).map((key) => (
              <div key={key} className="findings-kpi">
                <span className={`lifecycle-badge lifecycle-badge--${key}`}>{key}</span>
                <strong className="mono">{lifecycleFromScan[key] ?? 0}</strong>
              </div>
            ))}
            {(scan.eta_seconds != null || scan.resume_available) && (
              <div className="findings-kpi">
                {scan.resume_available ? (
                  <span className="status-badge status-badge--partial">{t("Paused")}</span>
                ) : (
                  <span className="field-help">{t("ETA")}</span>
                )}
                <strong className="mono">
                  {scan.resume_available ? t("Resume available") : formatEta(scan.eta_seconds)}
                </strong>
              </div>
            )}
          </div>
        )}

        {!finished ? (
          <p className="field-help">{t("Findings appear after the scan finishes.")}</p>
        ) : compareMode ? (
          <>
            <div className="form-row">
              <label htmlFor="findings-against">{t("Against")}</label>
              <select
                id="findings-against"
                className="input input--select"
                value={againstId}
                onChange={(e) => setAgainstId(e.target.value)}
                disabled={diffLoading}
              >
                <option value={PREVIOUS}>{t("Previous completed")}</option>
                {againstOptions.map((item) => (
                  <option key={item.id} value={String(item.id)}>
                    #{item.id}
                    {item.group_name ? ` · ${item.group_name}` : ""}
                    {!item.group_name && item.targets?.length
                      ? ` · ${item.targets.join(", ")}`
                      : ""}{" "}
                    · {item.status} · {new Date(item.finished_at || item.created_at).toLocaleString()}
                  </option>
                ))}
              </select>
              <p className="field-help">{t("Only scans for the same group or host set.")}</p>
            </div>

            {diffLoading ? (
              <p className="field-help" role="status">
                {t("Loading…")}
              </p>
            ) : !diff || diff.against_run_id == null ? (
              <p className="field-help">{diff?.detail || t("No previous run to compare.")}</p>
            ) : (
              <>
                <p className="field-help">
                  {t("Comparing scan")} #{diff.current_run_id} {t("vs")} #{diff.against_run_id}
                </p>
                <div className="findings-kpis">
                  <div className="findings-kpi">
                    <span className="lifecycle-badge lifecycle-badge--NEW">{t("Added")}</span>
                    <strong className="mono">{diff.counts.added}</strong>
                  </div>
                  <div className="findings-kpi">
                    <span className="lifecycle-badge lifecycle-badge--GONE">{t("Removed")}</span>
                    <strong className="mono">{diff.counts.removed}</strong>
                  </div>
                  <div className="findings-kpi">
                    <span className="lifecycle-badge lifecycle-badge--CHANGED">{t("Changed")}</span>
                    <strong className="mono">{diff.counts.changed}</strong>
                  </div>
                </div>
                <p className="field-help">
                  {t("Compare is limited to the same scan modules (TLS vs TLS, HTTP vs HTTP).")}
                  {diff.modules && diff.modules.length > 0
                    ? ` · ${diff.modules.join(", ")}`
                    : ""}
                </p>
                {diffRows.length === 0 ? (
                  <p className="field-help">{t("No differences between these scans.")}</p>
                ) : (
                  <div className="compare-method-groups">
                    {diffGroups.map((group) => (
                      <div key={group.method} className="compare-method-group">
                        <h3 className="compare-method-group__title">
                          {methodLabel(group.method)}
                          <span className="field-help mono">{group.rows.length}</span>
                        </h3>
                        <div className="table-wrap">
                          <table className="hosts">
                            <caption className="sr-only">
                              {t("Scan comparison")} — {methodLabel(group.method)}
                            </caption>
                            <thead>
                              <tr>
                                <th scope="col">{t("Change")}</th>
                                <th scope="col">{t("Entity")}</th>
                                <th scope="col">{t("Curiosity")}</th>
                                <th scope="col">{t("Details")}</th>
                              </tr>
                            </thead>
                            <tbody>
                              {group.rows.slice(0, 300).map((row) => {
                                if (row.kind === "changed") {
                                  const lines = attrDiffLines(row.item.before, row.item.after);
                                  return (
                                    <tr key={`changed-${row.item.entity_key}`}>
                                      <td>
                                        <span className="lifecycle-badge lifecycle-badge--CHANGED">
                                          {t("Changed")}
                                        </span>
                                      </td>
                                      <td className="mono">{row.item.entity_key}</td>
                                      <td>
                                        <CuriosityBadge
                                          value={curiosityFromAttrs(row.item.after)}
                                          t={t}
                                        />
                                      </td>
                                      <td>
                                        {lines.length > 0 ? (
                                          <ul className="diff-attr-list">
                                            {lines.map((line) => (
                                              <li key={line} className="mono">
                                                {line}
                                              </li>
                                            ))}
                                          </ul>
                                        ) : (
                                          "—"
                                        )}
                                      </td>
                                    </tr>
                                  );
                                }
                                const badge =
                                  row.kind === "added"
                                    ? "lifecycle-badge--NEW"
                                    : "lifecycle-badge--GONE";
                                return (
                                  <tr key={`${row.kind}-${row.item.entity_key}`}>
                                    <td>
                                      <span className={`lifecycle-badge ${badge}`}>
                                        {row.kind === "added" ? t("Added") : t("Removed")}
                                      </span>
                                    </td>
                                    <td className="mono">{row.item.entity_key}</td>
                                    <td>
                                      <CuriosityBadge
                                        value={curiosityFromAttrs(row.item.attrs)}
                                        t={t}
                                      />
                                    </td>
                                    <td>{attrsPreview(row.item.attrs)}</td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </>
        ) : (
          <>
            <div className="form-row">
              <label htmlFor="findings-lifecycle">{t("Lifecycle")}</label>
              <select
                id="findings-lifecycle"
                className="input input--select"
                value={lifecycle}
                onChange={(e) => setLifecycle(e.target.value as ObservationLifecycle | "")}
              >
                {LIFECYCLES.map((value) => (
                  <option key={value || "all"} value={value}>
                    {value || t("All")}
                  </option>
                ))}
              </select>
            </div>
            {loading ? (
              <p className="field-help" role="status">
                {t("Loading…")}
              </p>
            ) : rows.length === 0 ? (
              <p className="field-help">{t("No observations for this filter.")}</p>
            ) : (
              <div className="table-wrap">
                <table className="hosts">
                  <caption className="sr-only">{t("Observations")}</caption>
                  <thead>
                    <tr>
                      <th scope="col">{t("Lifecycle")}</th>
                      <th scope="col">{t("Type")}</th>
                      <th scope="col">{t("Entity")}</th>
                      <th scope="col">{t("Curiosity")}</th>
                      <th scope="col">{t("Details")}</th>
                      <th scope="col">{t("Override")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.slice(0, 200).map((row) => (
                      <tr key={row.id} className={editingKey === row.entity_key ? "is-selected" : undefined}>
                        <td>
                          <span className={`lifecycle-badge lifecycle-badge--${row.lifecycle}`}>
                            {row.lifecycle}
                          </span>
                        </td>
                        <td className="mono">{row.entity_type}</td>
                        <td className="mono">{row.entity_key}</td>
                        <td>
                          <CuriosityBadge
                            value={curiosityFromAttrs(row.effective_attrs || row.attrs)}
                            t={t}
                          />
                        </td>
                        <td>
                          {attrsPreview(row.effective_attrs || row.attrs)}
                          {(row.tags?.length || row.notes) && (
                            <div className="field-help">
                              {row.tags?.length ? `${t("Tags")}: ${row.tags.join(", ")}` : ""}
                              {row.tags?.length && row.notes ? " · " : ""}
                              {row.notes ? `${t("Notes")}: ${row.notes}` : ""}
                            </div>
                          )}
                        </td>
                        <td className="scan-actions">
                          {canExport && (
                            <button
                              type="button"
                              className="btn btn--normal"
                              disabled={busy}
                              onClick={() => openOverride(row)}
                            >
                              {row.override ? t("Edit override") : t("Add override")}
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {canExport && editingKey && (
              <form className="panel panel--nested" onSubmit={onSaveOverride}>
                <div className="panel__header">
                  <h3>
                    {t("Manual override")}: <span className="mono">{editingKey}</span>
                  </h3>
                </div>
                <div className="panel__body">
                  <p className="field-help">
                    {t("Overrides survive the next scan. Scanner attrs stay immutable.")}
                  </p>
                  <div className="form-row">
                    <label htmlFor="override-tech">{t("Technology")}</label>
                    <input
                      id="override-tech"
                      value={editTech}
                      onChange={(e) => setEditTech(e.target.value)}
                      disabled={busy}
                    />
                  </div>
                  <div className="form-row">
                    <label htmlFor="override-tags">{t("Tags")}</label>
                    <input
                      id="override-tags"
                      value={editTags}
                      onChange={(e) => setEditTags(e.target.value)}
                      placeholder={t("comma-separated")}
                      disabled={busy}
                    />
                  </div>
                  <div className="form-row">
                    <label htmlFor="override-notes">{t("Notes")}</label>
                    <textarea
                      id="override-notes"
                      value={editNotes}
                      onChange={(e) => setEditNotes(e.target.value)}
                      rows={3}
                      disabled={busy}
                    />
                  </div>
                  <div className="scan-actions">
                    <button type="submit" className="btn btn--primary" disabled={busy}>
                      {busy ? t("Saving…") : t("Save override")}
                    </button>
                    <button
                      type="button"
                      className="btn btn--normal"
                      disabled={busy}
                      onClick={() => setEditingKey(null)}
                    >
                      {t("Cancel")}
                    </button>
                  </div>
                </div>
              </form>
            )}
          </>
        )}
      </div>
    </section>
    </>
  );
}

export function LifecycleKpis({
  scans,
  t,
}: {
  scans: Scan[];
  t: Translate;
}) {
  const latest = scans.find(
    (item) => item.status === "completed" && item.result_summary?.lifecycle,
  );
  const counts = latest?.result_summary?.lifecycle;
  if (!counts) return null;
  return (
    <div className="findings-kpis findings-kpis--dashboard" aria-label={t("Latest findings")}>
      <span className="field-help">
        {t("Latest completed")} #{latest!.id}
      </span>
      {(["NEW", "CHANGED", "GONE"] as ObservationLifecycle[]).map((key) => (
        <div key={key} className="findings-kpi">
          <span className={`lifecycle-badge lifecycle-badge--${key}`}>{key}</span>
          <strong className="mono">{counts[key] ?? 0}</strong>
        </div>
      ))}
    </div>
  );
}
