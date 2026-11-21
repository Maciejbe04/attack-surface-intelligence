import { FormEvent, useEffect, useState } from "react";
import {
  apiErrorMessage,
  downloadScanExport,
  listObservations,
  Observation,
  ObservationLifecycle,
  resumeScan,
  Scan,
  upsertOverride,
} from "./api/scans";
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

type Props = {
  scan: Scan | null;
  canMutate: boolean;
  canExport: boolean;
  onScanUpdated: (scan: Scan) => void;
  pushToast: (kind: "ok" | "error", title: string, message: string) => void;
  t: Translate;
};

export function FindingsPanel({
  scan,
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

  useEffect(() => {
    if (!scan || !scan.finished_at) {
      setRows([]);
      setSummary({});
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
        pushToast("error", t("Findings unavailable"), apiErrorMessage(error, t("Could not load findings.")));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [scan?.id, scan?.finished_at, lifecycle, pushToast, t]);

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

  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editNotes, setEditNotes] = useState("");
  const [editTags, setEditTags] = useState("");
  const [editTech, setEditTech] = useState("");

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
    <section className="panel">
      <div className="panel__header">
        <h2>{t("Findings / Changes")}</h2>
        <div className="panel__actions">
          {scan.resume_available && canMutate && (
            <button type="button" className="btn btn--normal" disabled={busy} onClick={() => void onResume()}>
              {t("Resume")}
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

        {!finished ? (
          <p className="field-help">{t("Findings appear after the scan finishes.")}</p>
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
    (scan) => scan.status === "completed" && scan.result_summary?.lifecycle,
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
