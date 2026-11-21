import { useMemo } from "react";
import { ObservationLifecycle, Scan } from "./api/scans";
import { Translate } from "./i18n";

const SERIES: ObservationLifecycle[] = ["NEW", "CHANGED", "MISSING", "FLAKY", "GONE"];

type Point = {
  id: number;
  label: string;
  finishedAt: string;
  values: Record<ObservationLifecycle, number>;
  total: number;
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

export function ChangesOverTime({ scans, t }: { scans: Scan[]; t: Translate }) {
  const points = useMemo(() => {
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
    return rows
      .sort((a, b) => a.finishedAt.localeCompare(b.finishedAt))
      .slice(-12);
  }, [scans]);

  const maxTotal = Math.max(1, ...points.map((point) => point.total));

  if (points.length < 2) {
    return (
      <section className="panel changes-over-time" aria-label={t("Changes over time")}>
        <div className="panel__header">
          <h2>{t("Changes over time")}</h2>
        </div>
        <div className="panel__body">
          <p className="field-help">
            {t("Need at least two finished scans with lifecycle data to chart changes.")}
          </p>
        </div>
      </section>
    );
  }

  return (
    <section className="panel changes-over-time" aria-label={t("Changes over time")}>
      <div className="panel__header panel__header--split">
        <div>
          <h2>{t("Changes over time")}</h2>
          <p className="field-help">{t("Lifecycle counts across recent finished scans.")}</p>
        </div>
        <div className="changes-over-time__legend" aria-hidden="true">
          {SERIES.map((key) => (
            <span key={key} className={`changes-over-time__swatch changes-over-time__swatch--${key}`}>
              {key}
            </span>
          ))}
        </div>
      </div>
      <div className="panel__body">
        <div className="changes-over-time__chart" role="img" aria-label={t("Changes over time")}>
          {points.map((point) => (
            <div key={point.id} className="changes-over-time__col">
              <div
                className="changes-over-time__stack"
                style={{ height: `${Math.max(8, (point.total / maxTotal) * 100)}%` }}
                title={`#${point.id}: ${SERIES.map((key) => `${key} ${point.values[key]}`).join(", ")}`}
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
            </div>
          ))}
        </div>
        <div className="table-wrap">
          <table className="hosts hosts--compact">
            <caption className="sr-only">{t("Changes over time")}</caption>
            <thead>
              <tr>
                <th scope="col">{t("Scan")}</th>
                <th scope="col">{t("When")}</th>
                {SERIES.map((key) => (
                  <th key={key} scope="col">
                    {key}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[...points].reverse().map((point) => (
                <tr key={`row-${point.id}`}>
                  <td className="mono">{point.label}</td>
                  <td>{formatTick(point.finishedAt)}</td>
                  {SERIES.map((key) => (
                    <td key={key} className="mono">
                      {point.values[key]}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
