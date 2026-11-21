import { useEffect, useMemo, useRef } from "react";
import {
  ACTIVE_SCAN_STATUSES,
  ScanBatch,
  ScanDetail,
  ScanEvent,
  ScanEventLevel,
  ScanStatus,
} from "./api/scans";
import { Translate } from "./i18n";

const STATUS_LABELS: Record<ScanStatus, string> = {
  queued: "Queued",
  running: "Running",
  cancel_requested: "Cancel requested",
  completed: "Completed",
  partial: "Partial",
  failed: "Failed",
  cancelled: "Cancelled",
};

type Props = {
  scan: ScanDetail | null;
  loading: boolean;
  t: Translate;
  onClear?: () => void;
};

type ConsoleLine = {
  key: string;
  level: ScanEventLevel;
  source: string;
  message: string;
  created_at: string;
  target_address: string | null;
};

function formatTime(value: string): string {
  try {
    return new Date(value).toLocaleTimeString();
  } catch {
    return value;
  }
}

function batchSummary(batch: ScanBatch): string {
  const result = batch.result && typeof batch.result === "object" ? (batch.result as Record<string, unknown>) : null;
  const hosts = Array.isArray(result?.hosts) ? result.hosts.length : null;
  const http = Array.isArray(result?.http) ? result.http.length : null;
  const parts = [`Batch ${batch.status} for ${batch.target_address} (${batch.progress}%)`];
  if (hosts !== null) parts.push(`${hosts} host(s)`);
  if (http !== null) parts.push(`${http} HTTP observation(s)`);
  if (batch.error) parts.push(batch.error);
  return parts.join(" · ");
}

function synthesizeLines(scan: ScanDetail): ConsoleLine[] {
  const lines: ConsoleLine[] = [
    {
      key: `run-created-${scan.id}`,
      level: "info",
      source: "api",
      message: `Scan #${scan.id} created with status ${scan.status}.`,
      created_at: scan.created_at,
      target_address: null,
    },
  ];

  if (scan.started_at) {
    lines.push({
      key: `run-started-${scan.id}`,
      level: "info",
      source: "worker",
      message: `Scan started (${scan.progress}%).`,
      created_at: scan.started_at,
      target_address: null,
    });
  }

  for (const batch of scan.batches ?? []) {
    lines.push({
      key: `batch-${batch.id}-created`,
      level: "info",
      source: "api",
      message: `Batch queued for ${batch.target_address} (${batch.target_type}).`,
      created_at: batch.created_at,
      target_address: batch.target_address,
    });
    if (batch.claimed_at) {
      lines.push({
        key: `batch-${batch.id}-claimed`,
        level: "info",
        source: "worker",
        message: `Worker claimed batch for ${batch.target_address}.`,
        created_at: batch.claimed_at,
        target_address: batch.target_address,
      });
    }
    if (batch.finished_at || batch.status !== "queued") {
      const level: ScanEventLevel =
        batch.status === "failed" ? "error" : batch.status === "cancelled" ? "warn" : "info";
      lines.push({
        key: `batch-${batch.id}-state`,
        level,
        source: "worker",
        message: batchSummary(batch),
        created_at: batch.finished_at || batch.claimed_at || batch.created_at,
        target_address: batch.target_address,
      });
    }
  }

  if (scan.finished_at) {
    lines.push({
      key: `run-finished-${scan.id}`,
      level: scan.status === "failed" ? "error" : scan.status === "cancelled" ? "warn" : "info",
      source: "api",
      message: `Scan finished with status ${scan.status} (${scan.progress}%).`,
      created_at: scan.finished_at,
      target_address: null,
    });
  }

  if (scan.defectdojo_export_status && scan.defectdojo_export_status !== "none") {
    lines.push({
      key: `run-dd-${scan.id}`,
      level: scan.defectdojo_export_status === "failed" ? "error" : "info",
      source: "defectdojo",
      message:
        scan.defectdojo_export_detail ||
        `DefectDojo export status: ${scan.defectdojo_export_status}.`,
      created_at: scan.finished_at || scan.created_at,
      target_address: null,
    });
  }

  return lines;
}

function toConsoleLines(events: ScanEvent[]): ConsoleLine[] {
  return events.map((event) => ({
    key: `event-${event.id}`,
    level: event.level,
    source: event.source,
    message: event.message,
    created_at: event.created_at,
    target_address: event.target_address,
  }));
}

function EventLine({ line }: { line: ConsoleLine }) {
  const prefix = line.target_address ? `[${line.target_address}] ` : "";
  return (
    <div className={`scan-console__line scan-console__line--${line.level}`}>
      <span className="scan-console__time">{formatTime(line.created_at)}</span>
      <span className="scan-console__level">{line.level}</span>
      <span className="scan-console__source">{line.source}</span>
      <span className="scan-console__message">
        {prefix}
        {line.message}
      </span>
    </div>
  );
}

export function ScanConsole({ scan, loading, t, onClear }: Props) {
  const sectionRef = useRef<HTMLElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const active = scan ? ACTIVE_SCAN_STATUSES.has(scan.status) : false;
  const lines = useMemo(() => {
    if (!scan) return [];
    const events = scan.events ?? [];
    if (events.length > 0) return toConsoleLines(events);
    return synthesizeLines(scan);
  }, [scan]);

  useEffect(() => {
    if (!scan) return;
    sectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [scan?.id]);

  useEffect(() => {
    const node = bodyRef.current;
    if (!node) return;
    node.scrollTop = node.scrollHeight;
  }, [scan?.id, lines.length, scan?.status, scan?.progress]);

  return (
    <section
      ref={sectionRef}
      id="scan-activity-console"
      className="panel scan-console"
      aria-live="polite"
    >
      <div className="panel__header scan-console__header">
        <div>
          <h2>{t("Activity console")}</h2>
          <p className="field-help">
            {scan
              ? `${t("Scan")} #${scan.id} · ${t(STATUS_LABELS[scan.status])} · ${scan.progress}%`
              : t("Run a probe or scan selected targets to stream execution logs here.")}
          </p>
        </div>
        <div className="scan-console__actions">
          {active && <span className="scan-console__live">{t("Live")}</span>}
          {loading && <span className="field-help">{t("Refreshing…")}</span>}
          {scan && onClear && (
            <button type="button" className="btn btn--normal" onClick={onClear}>
              {t("Clear console")}
            </button>
          )}
        </div>
      </div>
      <div className="scan-console__body" ref={bodyRef} role="log" aria-label={t("Scan activity log")}>
        {!scan && (
          <div className="scan-console__empty">
            {t("Waiting for the next scan run.")}
          </div>
        )}
        {scan && lines.length === 0 && (
          <div className="scan-console__empty">
            {t("No activity events yet for this scan.")}
          </div>
        )}
        {lines.map((line) => (
          <EventLine key={line.key} line={line} />
        ))}
      </div>
    </section>
  );
}
