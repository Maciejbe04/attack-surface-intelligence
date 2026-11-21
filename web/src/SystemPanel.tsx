import { useEffect, useState } from "react";
import { apiFetch } from "./auth";
import { Translate } from "./i18n";
import { APP_NAME, APP_VERSION } from "./version";

export type SystemIntegration = {
  id: string;
  name: string;
  enabled: boolean;
  status: string;
  version: string;
  endpoint: string;
  product_type?: string;
  product_name?: string;
  engagement_name?: string;
  test_title?: string;
  auto_export?: boolean;
  summary: string;
};

export type SystemComponent = {
  id: string;
  name: string;
  role: string;
  version: string;
};

export type SystemInfo = {
  app: {
    name: string;
    version: string;
    role: string;
    platform: string;
    python: string;
  };
  integrations: SystemIntegration[];
  stack: SystemComponent[];
};

type Props = {
  active: boolean;
  t: Translate;
};

function statusLabel(status: string, t: Translate): string {
  if (status === "configured") return t("In use");
  if (status === "not_configured") return t("Not configured");
  return status;
}

export function SystemPanel({ active, t }: Props) {
  const [info, setInfo] = useState<SystemInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    apiFetch("/api/system/", { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.json() as Promise<SystemInfo>;
      })
      .then((payload) => {
        if (!controller.signal.aborted) setInfo(payload);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        if (err instanceof DOMException && err.name === "AbortError") return;
        setError(t("Could not load system information."));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [active, t]);

  if (!active) return null;

  return (
    <>
      <header className="page-header">
        <h1>{t("System & integrations")}</h1>
        <p>
          {APP_NAME} v{APP_VERSION} · {t("Stack composition and active integrations.")}
        </p>
      </header>

      {loading && (
        <p className="field-help" role="status">
          {t("Loading system information…")}
        </p>
      )}

      {error && (
        <div className="flash flash--error" role="alert">
          <div>
            <strong>{t("Unavailable")}</strong>
            <p>{error}</p>
          </div>
        </div>
      )}

      {info && (
        <>
          <section className="panel">
            <div className="panel__header">
              <h2>{t("Integrations")}</h2>
            </div>
            <div className="panel__body">
              <ul className="system-panel__list">
                {info.integrations.map((integration) => (
                  <li key={integration.id} className="system-panel__card">
                    <div className="system-panel__card-head">
                      <strong>{integration.name}</strong>
                      <span
                        className={`status-badge ${
                          integration.enabled
                            ? "status-badge--completed"
                            : "status-badge--cancelled"
                        }`}
                      >
                        {statusLabel(integration.status, t)}
                      </span>
                    </div>
                    <p className="field-help">{t(integration.summary)}</p>
                    <dl className="system-panel__meta">
                      <div>
                        <dt>{t("Version")}</dt>
                        <dd className="mono">{integration.version || "—"}</dd>
                      </div>
                      <div>
                        <dt>{t("Endpoint")}</dt>
                        <dd className="mono">{integration.endpoint || "—"}</dd>
                      </div>
                      {integration.auto_export && (
                        <div>
                          <dt>{t("Export")}</dt>
                          <dd>{t("Automatic after scan completion")}</dd>
                        </div>
                      )}
                      {integration.product_name && (
                        <div>
                          <dt>{t("Product")}</dt>
                          <dd>
                            {integration.product_type
                              ? `${integration.product_type} / ${integration.product_name}`
                              : integration.product_name}
                          </dd>
                        </div>
                      )}
                    </dl>
                  </li>
                ))}
              </ul>
            </div>
          </section>

          <section className="panel">
            <div className="panel__header">
              <h2>{t("System information")}</h2>
            </div>
            <div className="panel__body">
              <p className="field-help" style={{ marginTop: 0 }}>
                {t("Platform")}: <span className="mono">{info.app.platform}</span>
              </p>
              <div className="table-wrap">
                <table className="hosts system-panel__table">
                  <caption className="sr-only">{t("Stack components")}</caption>
                  <thead>
                    <tr>
                      <th scope="col">{t("Component")}</th>
                      <th scope="col">{t("Role")}</th>
                      <th scope="col">{t("Version")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {info.stack.map((component) => (
                      <tr key={component.id}>
                        <td>{component.name}</td>
                        <td>{t(component.role)}</td>
                        <td className="mono">{component.version}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        </>
      )}
    </>
  );
}

export function SystemLockButton({
  onClick,
  t,
  className = "",
}: {
  onClick: () => void;
  t: Translate;
  className?: string;
}) {
  return (
    <button
      type="button"
      className={`btn btn--normal system-lock-btn ${className}`.trim()}
      onClick={onClick}
      aria-label={t("System & integrations")}
      title={t("System & integrations")}
    >
      <svg
        className="system-lock-btn__icon"
        viewBox="0 0 24 24"
        width="14"
        height="14"
        aria-hidden="true"
        focusable="false"
      >
        <path
          fill="currentColor"
          d="M17 9h-1V7a4 4 0 0 0-8 0v2H7a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-8a2 2 0 0 0-2-2Zm-7-2a2 2 0 1 1 4 0v2h-4V7Zm7 12H7v-8h10v8Zm-5-3a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3Z"
        />
      </svg>
      <span className="system-lock-btn__label">{t("System")}</span>
    </button>
  );
}
