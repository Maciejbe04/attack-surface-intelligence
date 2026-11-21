import { useMemo, useState } from "react";
import { ObservationLifecycle, Scan } from "./api/scans";
import { Translate } from "./i18n";

const SERIES: ObservationLifecycle[] = ["NEW", "CHANGED", "MISSING", "FLAKY", "GONE"];

type RangeKey = "24h" | "7d" | "30d" | "all";

type Point = {
  id: number;
  label: string;
  finishedAt: string;
  values: Record<ObservationLifecycle, number>;
  total: number;
};

const RANGE_MS: Record<Exclude<RangeKey, "all">, number> = {
  "24h": 24 * 60 * 60 * 1000,
  "7d": 7 * 24 * 60 * 60 * 1000,
  "30d": 30 * 24 * 60 * 60 * 1000,
};

function formatTick(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function rangeLabel(key: RangeKey, t: Translate): string {
  if (key === "24h") return t("Last 24 hours");
  if (key === "7d") return t("Last 7 days");
  if (key === "30d") return t("Last 30 days");
  return t("All time");
}

export function ChangesOverTime({
  scans,
  t,
  onOpenScan,
}: {
  scans: Scan[];
  t: Translate;
  onOpenScan: (scanId: number) => void;
}) {
  const [range, setRange] = useState<RangeKey>("7d");

  const allPoints = useMemo(() => {
    const rows: Point[] = [];
    for (const scan of scans) {
      if (scan.status !== "completed" && scan.status !== "partial") continue;
      const lifecycle = scan.result_summary?.lifecycle;
      if (!lifecycle) continue;
      const values = {
        NEW: Number(lifecycle.NEW || 0),
        CHANGED: Number(lifecycle.CHANGED || 0),
        MISSING: Number(lifecycle.MISSING || 0),
        FLAKY: Number(lifecycle.FLAKY || 0),
        GONE: Number(lifecycle.GONE || 0),
        UNCHANGED: Number(lifecycle.UNCHANGED || 0),
      };
      const total = SERIES.reduce((sum, key) => sum + values[key], 0);
      if (total <= 0) continue;
      rows.push({
        id: scan.id,
        label: `#${scan.id}`,
        finishedAt: scan.finished_at || scan.created_at,
        values,
        total,
      });
    }
    return rows.sort((a, b) => a.finishedAt.localeCompare(b.finishedAt));
  }, [scans]);

  const points = useMemo(() => {
    if (range === "all") return allPoints.slice(-24);
    const cutoff = Date.now() - RANGE_MS[range];
    return allPoints.filter((point) => {
      const ts = Date.parse(point.finishedAt);
      return Number.isFinite(ts) && ts >= cutoff;
    });
  }, [allPoints, range]);

  const maxTotal = Math.max(1, ...points.map((point) => point.total));

  return (
    <section className="panel changes-over-time" aria-label={t("Changes over time")}>
      <div className="panel__header panel__header--split">
        <div>
          <h2>{t("Changes over time")}</h2>
          <p className="field-help">{t("Click a bar to open that scan log.")}</p>
        </div>
        <div className="changes-over-time__controls">
          <label className="changes-over-time__range" htmlFor="changes-range">
            <span className="field-help">{t("Time range")}</span>
            <select
              id="changes-range"
              className="input input--select"
              value={range}
              onChange={(event) => setRange(event.target.value as RangeKey)}
            >
              {(["24h", "7d", "30d", "all"] as RangeKey[]).map((key) => (
                <option key={key} value={key}>
                  {rangeLabel(key, t)}
                </option>
              ))}
            </select>
          </label>
          <div className="changes-over-time__legend" aria-hidden="true">
            {SERIES.map((key) => (
              <span key={key} className={`changes-over-time__swatch changes-over-time__swatch--${key}`}>
                {key}
              </span>
            ))}
          </div>
        </div>
      </div>
      <div className="panel__body">
        {points.length < 2 ? (
          <p className="field-help">
            {allPoints.length < 2
              ? t("Need at least two finished scans with lifecycle data to chart changes.")
              : t("No finished scans in this time range.")}
          </p>
        ) : (
          <div
            className="changes-over-time__chart"
            role="list"
            aria-label={t("Changes over time")}
          >
            {points.map((point) => (
              <button
                key={point.id}
                type="button"
                className="changes-over-time__col"
                role="listitem"
                onClick={() => onOpenScan(point.id)}
                title={`${point.label} · ${formatTick(point.finishedAt)} · ${SERIES.map(
                  (key) => `${key} ${point.values[key]}`,
                ).join(", ")}`}
                aria-label={`${t("Open scan log")} ${point.label}`}
              >
                <div
                  className="changes-over-time__stack"
                  style={{ height: `${Math.max(8, (point.total / maxTotal) * 100)}%` }}
                >
                  {SERIES.map((key) => {
                    const value = point.values[key];
                    if (value <= 0) return null;
                    return (
                      <div
                        key={key}
                        className={`changes-over-time__seg changes-over-time__seg--${key}`}
                        style={{ flexGrow: value, flexBasis: 0 }}
                      />
                    );
                  })}
                </div>
                <span className="changes-over-time__label mono">{point.label}</span>
                <span className="changes-over-time__when">{formatTick(point.finishedAt)}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
