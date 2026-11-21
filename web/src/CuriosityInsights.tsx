import { CuriosityHighlight, CuriositySummary, Scan } from "./api/scans";
import { Translate } from "./i18n";

function highlightLabel(item: CuriosityHighlight, t: Translate): string {
  switch (item.id) {
    case "hosts_with_open_ports":
      return t("{n} host(s) have open ports").replace("{n}", String(item.count));
    case "open_ports_total":
      return t("{n} open port(s) observed").replace("{n}", String(item.count));
    case "interesting_ports":
      return t("{n} non-standard or sensitive port(s)").replace("{n}", String(item.count));
    case "admin_or_login_hints":
      return t("{n} admin / login / staging hint(s)").replace("{n}", String(item.count));
    case "high_confidence_tech":
      return t("{n} medium/high-confidence technolog(ies)").replace("{n}", String(item.count));
    case "expiring_certs":
      return t("{n} certificate(s) expire within 30 days").replace("{n}", String(item.count));
    default:
      return item.text;
  }
}

function severityClass(severity: string): string {
  if (severity === "high") return "curiosity-card--high";
  if (severity === "medium") return "curiosity-card--medium";
  return "curiosity-card--info";
}

export function CuriosityInsights({
  curiosity,
  scanId,
  t,
}: {
  curiosity: CuriositySummary | null | undefined;
  scanId?: number;
  t: Translate;
}) {
  if (!curiosity) return null;
  const highlights = (curiosity.highlights || []).filter((item) => item.count > 0);
  if (highlights.length === 0 && !curiosity.hosts_with_open_ports && !curiosity.open_ports_total) {
    return null;
  }
  const cards =
    highlights.length > 0
      ? highlights
      : ([
          curiosity.hosts_with_open_ports
            ? {
                id: "hosts_with_open_ports",
                severity: "info",
                text: "",
                count: curiosity.hosts_with_open_ports,
              }
            : null,
          curiosity.open_ports_total
            ? {
                id: "open_ports_total",
                severity: "info",
                text: "",
                count: curiosity.open_ports_total,
              }
            : null,
        ].filter(Boolean) as CuriosityHighlight[]);

  if (cards.length === 0) return null;

  return (
    <section className="panel curiosity-panel" aria-label={t("Analytical curiosity")}>
      <div className="panel__header panel__header--split">
        <h2>{t("Analytical curiosity")}</h2>
        {scanId != null && (
          <span className="field-help">
            {t("Latest completed")} #{scanId}
          </span>
        )}
      </div>
      <div className="panel__body">
        <p className="field-help" style={{ marginTop: 0 }}>
          {t("Priority signals from the latest completed discovery scan.")}
        </p>
        <div className="curiosity-grid">
          {cards.map((item) => (
            <div key={item.id} className={`curiosity-card ${severityClass(item.severity)}`}>
              <strong className="mono curiosity-card__count">{item.count}</strong>
              <span className="curiosity-card__label">{highlightLabel(item, t)}</span>
            </div>
          ))}
        </div>
        {curiosity.top_services && curiosity.top_services.length > 0 && (
          <p className="field-help curiosity-services">
            {t("Top services")}:{" "}
            {curiosity.top_services
              .map((row) => `${row.service} (${row.count})`)
              .join(" · ")}
          </p>
        )}
      </div>
    </section>
  );
}

export function CuriosityInsightsFromScans({
  scans,
  t,
}: {
  scans: Scan[];
  t: Translate;
}) {
  const latest = scans.find(
    (item) => item.status === "completed" && item.result_summary?.curiosity,
  );
  if (!latest) return null;
  return (
    <CuriosityInsights
      curiosity={latest.result_summary.curiosity}
      scanId={latest.id}
      t={t}
    />
  );
}
