import { PointerEvent as ReactPointerEvent, useMemo, useState } from "react";
import { ObservationLifecycle, Scan } from "./api/scans";
import { Translate } from "./i18n";

const SERIES: ObservationLifecycle[] = ["NEW", "CHANGED", "MISSING", "FLAKY", "GONE"];
type RangeKey = "24h" | "7d" | "30d" | "all";
type ChartSize = "small" | "medium" | "large";
type ZoomRange = { start: number; end: number };

type Point = {
  id: number;
  finishedAt: string;
  values: Record<ObservationLifecycle, number>;
  total: number;
};

type AxisTick = {
  key: string;
  left: string;
  date: string;
  time: string;
};

const RANGE_MS: Record<Exclude<RangeKey, "all">, number> = {
  "24h": 24 * 60 * 60 * 1000,
  "7d": 7 * 24 * 60 * 60 * 1000,
  "30d": 30 * 24 * 60 * 60 * 1000,
};

function pad2(value: number): string {
  return String(value).padStart(2, "0");
}

function formatTick(iso: string): string {
  try {
    const date = new Date(iso);
    return `${pad2(date.getDate())}.${pad2(date.getMonth() + 1)} ${pad2(date.getHours())}:${pad2(
      date.getMinutes(),
    )}`;
  } catch {
    return iso;
  }
}

function formatAxisDate(iso: string): { date: string; time: string } {
  try {
    const value = new Date(iso);
    return {
      date: `${pad2(value.getDate())}.${pad2(value.getMonth() + 1)}`,
      time: `${pad2(value.getHours())}:${pad2(value.getMinutes())}`,
    };
  } catch {
    return { date: iso, time: "" };
  }
}

function pickAxisIndexes(length: number): number[] {
  if (length <= 0) return [];
  if (length === 1) return [0];
  const maxTicks = length <= 8 ? length : 5;
  const indexes = new Set<number>([0, length - 1]);
  if (maxTicks <= 2) return [...indexes].sort((a, b) => a - b);
  for (let step = 1; step < maxTicks - 1; step += 1) {
    indexes.add(Math.round((step / (maxTicks - 1)) * (length - 1)));
  }
  return [...indexes].sort((a, b) => a - b);
}

function rangeLabel(key: RangeKey, t: Translate): string {
  if (key === "24h") return t("Last 24 hours");
  if (key === "7d") return t("Last 7 days");
  if (key === "30d") return t("Last 30 days");
  return t("All time");
}

export function ChangesOverTime({ scans, t }: { scans: Scan[]; t: Translate }) {
  const [range, setRange] = useState<RangeKey>("7d");
  const [chartSize, setChartSize] = useState<ChartSize>("medium");
  const [zoom, setZoom] = useState<ZoomRange | null>(null);
  const [dragStart, setDragStart] = useState<number | null>(null);
  const [dragCurrent, setDragCurrent] = useState<number | null>(null);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

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
        finishedAt: scan.finished_at || scan.created_at,
        values,
        total,
      });
    }
    return rows.sort((a, b) => a.finishedAt.localeCompare(b.finishedAt));
  }, [scans]);

  const rangePoints = useMemo(() => {
    if (range === "all") return allPoints.slice(-24);
    const cutoff = Date.now() - RANGE_MS[range];
    return allPoints.filter((point) => {
      const ts = Date.parse(point.finishedAt);
      return Number.isFinite(ts) && ts >= cutoff;
    });
  }, [allPoints, range]);

  const points = useMemo(() => {
    if (!zoom) return rangePoints;
    return rangePoints.slice(zoom.start, zoom.end + 1);
  }, [rangePoints, zoom]);

  const maxTotal = Math.max(1, ...points.map((point) => point.total));
  const barMaxPx = chartSize === "small" ? 80 : chartSize === "large" ? 220 : 140;
  const dense = points.length > 10;
  const selectedStart =
    dragStart === null || dragCurrent === null ? null : Math.min(dragStart, dragCurrent);
  const selectedEnd =
    dragStart === null || dragCurrent === null ? null : Math.max(dragStart, dragCurrent);
  const chartKey = `${range}-${zoom?.start ?? "full"}-${zoom?.end ?? "full"}-${chartSize}-${points
    .map((point) => point.id)
    .join(",")}`;

  const axisTicks = useMemo(() => {
    const indexes = pickAxisIndexes(points.length);
    return indexes.map((index): AxisTick => {
      const point = points[index];
      const axis = formatAxisDate(point.finishedAt);
      const center = ((index + 0.5) / points.length) * 100;
      return {
        key: `tick-${point.id}`,
        left: `${center}%`,
        date: axis.date,
        time: axis.time,
      };
    });
  }, [points]);

  function pointIndex(event: ReactPointerEvent<HTMLDivElement>): number {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = Math.max(0, Math.min(rect.width - 1, event.clientX - rect.left));
    return Math.min(points.length - 1, Math.floor((x / rect.width) * points.length));
  }

  function beginSelection(event: ReactPointerEvent<HTMLDivElement>) {
    if (event.button !== 0 || points.length < 2) return;
    const index = pointIndex(event);
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragStart(index);
    setDragCurrent(index);
  }

  function updateSelection(event: ReactPointerEvent<HTMLDivElement>) {
    const index = pointIndex(event);
    if (dragStart === null) {
      setHoverIndex(index);
      return;
    }
    setDragCurrent(index);
  }

  function finishSelection(event: ReactPointerEvent<HTMLDivElement>) {
    if (dragStart === null) return;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    const pointerEnd = pointIndex(event);
    const start = Math.min(dragStart, pointerEnd);
    const end = Math.max(dragStart, pointerEnd);
    if (end > start) {
      const base = zoom?.start ?? 0;
      setZoom({ start: base + start, end: base + end });
    }
    setDragStart(null);
    setDragCurrent(null);
    setHoverIndex(pointerEnd);
  }

  function cancelSelection() {
    setDragStart(null);
    setDragCurrent(null);
  }

  function changeSize(delta: -1 | 1) {
    const sizes: ChartSize[] = ["small", "medium", "large"];
    const index = sizes.indexOf(chartSize);
    setChartSize(sizes[Math.max(0, Math.min(sizes.length - 1, index + delta))]);
  }

  return (
    <section className="panel changes-over-time" aria-label={t("Changes over time")}>
      <div className="panel__header panel__header--split">
        <div>
          <h2>{t("Changes over time")}</h2>
          <p className="field-help">
            {t("Drag across chart to zoom. Dates mark scan completion time.")}
          </p>
        </div>
        <div className="changes-over-time__controls">
          <div className="changes-over-time__toolbar">
            <label className="changes-over-time__range" htmlFor="changes-range">
              <span className="field-help">{t("Time range")}</span>
              <select
                id="changes-range"
                className="input input--select"
                value={range}
                onChange={(event) => {
                  setRange(event.target.value as RangeKey);
                  setZoom(null);
                }}
              >
                {(["24h", "7d", "30d", "all"] as RangeKey[]).map((key) => (
                  <option key={key} value={key}>
                    {rangeLabel(key, t)}
                  </option>
                ))}
              </select>
            </label>
            <div className="changes-over-time__size-controls" role="group" aria-label={t("Chart size")}>
              <button
                type="button"
                className="btn btn--normal"
                disabled={chartSize === "small"}
                onClick={() => changeSize(-1)}
                aria-label={t("Decrease chart height")}
                title={t("Decrease chart height")}
              >
                −
              </button>
              <button
                type="button"
                className="btn btn--normal"
                disabled={chartSize === "large"}
                onClick={() => changeSize(1)}
                aria-label={t("Increase chart height")}
                title={t("Increase chart height")}
              >
                +
              </button>
              <button
                type="button"
                className="btn btn--normal"
                disabled={!zoom}
                onClick={() => setZoom(null)}
              >
                {t("Reset zoom")}
              </button>
            </div>
          </div>
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
        {rangePoints.length < 2 ? (
          <p className="field-help">
            {allPoints.length < 2
              ? t("Need at least two finished scans with lifecycle data to chart changes.")
              : t("No finished scans in this time range.")}
          </p>
        ) : (
          <div
            key={chartKey}
            className={`changes-over-time__chart changes-over-time__chart--${chartSize}${
              dense ? " changes-over-time__chart--dense" : ""
            }`}
            role="application"
            aria-label={t("Drag across chart to zoom. Dates mark scan completion time.")}
            onPointerDown={beginSelection}
            onPointerMove={updateSelection}
            onPointerUp={finishSelection}
            onPointerCancel={cancelSelection}
            onPointerLeave={() => {
              if (dragStart === null) setHoverIndex(null);
            }}
          >
            {selectedStart !== null && selectedEnd !== null && (
              <div
                className="changes-over-time__selection"
                style={{
                  left: `${(selectedStart / points.length) * 100}%`,
                  width: `${((selectedEnd - selectedStart + 1) / points.length) * 100}%`,
                }}
              />
            )}
            {hoverIndex !== null &&
              dragStart === null &&
              points[hoverIndex] && (
                <div
                  className="changes-over-time__tooltip"
                  style={{ left: `${((hoverIndex + 0.5) / points.length) * 100}%` }}
                >
                  <strong>
                    {t("Scan")} #{points[hoverIndex].id}
                  </strong>
                  <span>{formatTick(points[hoverIndex].finishedAt)}</span>
                  <span>
                    {SERIES.filter((key) => points[hoverIndex].values[key] > 0)
                      .map((key) => `${key} ${points[hoverIndex].values[key]}`)
                      .join(" · ")}
                  </span>
                </div>
              )}
            <div className="changes-over-time__bars">
              {points.map((point, index) => {
                const barHeight = Math.max(8, Math.round((point.total / maxTotal) * barMaxPx));
                const hovered = hoverIndex === index && dragStart === null;
                return (
                  <div
                    key={point.id}
                    className={`changes-over-time__col${hovered ? " is-hovered" : ""}`}
                    style={
                      dense
                        ? undefined
                        : { animationDelay: `${Math.min(index, 18) * 18}ms` }
                    }
                  >
                    <div className="changes-over-time__plot">
                      <div className="changes-over-time__stack" style={{ height: `${barHeight}px` }}>
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
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="changes-over-time__axis" aria-hidden="true">
              {axisTicks.map((tick) => (
                <div
                  key={tick.key}
                  className="changes-over-time__tick changes-over-time__tick--visible"
                  style={{ left: tick.left }}
                >
                  <span className="changes-over-time__tick-date">{tick.date}</span>
                  <span className="changes-over-time__tick-time">{tick.time}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
