import { useEffect, useRef } from "react";
import { ACTIVE_SCAN_STATUSES, ScanDetail, ScanEvent, ScanStatus } from "./api/scans";
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

function formatTime(value: string): string {
  try {
    return new Date(value).toLocaleTimeString();
  } catch {
    return value;
  }
}

function EventLine({ event }: { event: ScanEvent }) {
  const prefix = event.target_address ? `[${event.target_address}] ` : "";
  return (
    <div className={`scan-console__line scan-console__line--${event.level}`}>
      <span className="scan-console__time">{formatTime(event.created_at)}</span>
      <span className="scan-console__level">{event.level}</span>
      <span className="scan-console__source">{event.source}</span>
      <span className="scan-console__message">
        {prefix}
        {event.message}
      </span>
    </div>
  );
}

export function ScanConsole({ scan, loading, t, onClear }: Props) {
  const bodyRef = useRef<HTMLDivElement>(null);
  const active = scan ? ACTIVE_SCAN_STATUSES.has(scan.status) : false;

  useEffect(() => {
    const node = bodyRef.current;
    if (!node) return;
    node.scrollTop = node.scrollHeight;
  }, [scan?.id, scan?.events.length, scan?.status, scan?.progress]);

  return (
    <section className="panel scan-console" aria-live="polite">
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
        {scan && scan.events.length === 0 && (
          <div className="scan-console__empty">
            {t("No activity events yet for this scan.")}
          </div>
        )}
        {scan?.events.map((event) => (
          <EventLine key={event.id} event={event} />
        ))}
      </div>
    </section>
  );
}
