import { CuriosityHighlight, CuriositySummary, Scan } from "./api/scans";
import { Translate } from "./i18n";

function highlightLabel(item: CuriosityHighlight, t: Translate): string {
  switch (item.id) {
    case "hosts_with_open_ports":
      return t("Hosts up");
    case "open_ports_total":
      return t("Open ports");
    case "interesting_ports":
      return t("Odd ports");
    case "admin_or_login_hints":
      return t("Login paths");
    case "high_confidence_tech":
      return t("Known tech");
    case "expiring_certs":
      return t("Certs soon");
    default:
      return item.text.replace(/^\d+\s*/, "");
  }
}

function severityLabel(severity: string, t: Translate): string {
  if (severity === "high") return t("high");
  if (severity === "medium") return t("medium");
  if (severity === "low") return t("low");
  return t("info");
}

function severityClass(severity: string): string {
  if (severity === "high") return "curiosity-card--high";
  if (severity === "medium") return "curiosity-card--medium";
  if (severity === "low") return "curiosity-card--low";
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
    <section className="panel curiosity-panel" aria-label={t("Curiosity")}>
      <div className="panel__header panel__header--split">
        <div className="curiosity-panel__title">
          <h2>{t("Curiosity")}</h2>
          <p className="curiosity-panel__lede">{t("From the last finished scan.")}</p>
        </div>
        {scanId != null && (
          <span className="curiosity-panel__meta mono">
            {t("Scan")} #{scanId}
          </span>
        )}
      </div>
      <div className="panel__body curiosity-panel__body">
        <div className="curiosity-grid">
          {cards.map((item) => (
            <article
              key={item.id}
              className={`curiosity-card ${severityClass(item.severity)}`}
            >
              <div className="curiosity-card__top">
                <strong className="mono curiosity-card__count">{item.count}</strong>
                <span className={`curiosity-pill curiosity-pill--${item.severity || "info"}`}>
                  {severityLabel(item.severity || "info", t)}
                </span>
              </div>
              <span className="curiosity-card__label">{highlightLabel(item, t)}</span>
            </article>
          ))}
        </div>
        {curiosity.top_services && curiosity.top_services.length > 0 && (
          <div className="curiosity-services">
            <span className="curiosity-services__label">{t("Services")}</span>
            <ul className="curiosity-services__list">
              {curiosity.top_services.map((row) => (
                <li key={row.service} className="curiosity-chip mono">
                  {row.service}
                  <span className="curiosity-chip__count">{row.count}</span>
                </li>
              ))}
            </ul>
          </div>
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
