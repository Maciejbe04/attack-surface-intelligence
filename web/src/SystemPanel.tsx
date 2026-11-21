import { FormEvent, useEffect, useState } from "react";
import {
  AllowlistEntry,
  apiErrorMessage,
  AuditEvent,
  createAllowlistEntry,
  deleteAllowlistEntry,
  listAllowlist,
  listAudit,
} from "./api/scans";
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
  signatures?: {
    pack_version: string;
    count: number;
    ids: string[];
    summary: string;
  };
  stack: SystemComponent[];
};

type Props = {
  active: boolean;
  isAdmin?: boolean;
  canManageAllowlist?: boolean;
  t: Translate;
};

function statusLabel(status: string, t: Translate): string {
  if (status === "configured") return t("In use");
  if (status === "not_configured") return t("Not configured");
  return status;
}

export function SystemPanel({
  active,
  isAdmin = false,
  canManageAllowlist = false,
  t,
}: Props) {
  const [info, setInfo] = useState<SystemInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [audit, setAudit] = useState<AuditEvent[]>([]);
  const [allowlist, setAllowlist] = useState<AllowlistEntry[]>([]);
  const [allowlistEnforced, setAllowlistEnforced] = useState(false);
  const [allowValue, setAllowValue] = useState("");
  const [allowType, setAllowType] = useState<AllowlistEntry["type"]>("cidr");
  const [allowBusy, setAllowBusy] = useState(false);
  const [allowRefresh, setAllowRefresh] = useState(0);

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

  useEffect(() => {
    if (!active || !isAdmin) {
      setAudit([]);
      return;
    }
    const controller = new AbortController();
    listAudit(controller.signal)
      .then((payload) => {
        if (!controller.signal.aborted) setAudit(payload.results.slice(0, 20));
      })
      .catch(() => {
        if (!controller.signal.aborted) setAudit([]);
      });
    return () => controller.abort();
  }, [active, isAdmin]);

  useEffect(() => {
    if (!active) {
      setAllowlist([]);
      return;
    }
    const controller = new AbortController();
    listAllowlist(controller.signal)
      .then((payload) => {
        if (controller.signal.aborted) return;
        setAllowlist(payload.results);
        setAllowlistEnforced(payload.enforced);
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setAllowlist([]);
          setAllowlistEnforced(false);
        }
      });
    return () => controller.abort();
  }, [active, allowRefresh]);

  async function onAddAllowlist(event: FormEvent) {
    event.preventDefault();
    if (!canManageAllowlist || !allowValue.trim() || allowBusy) return;
    setAllowBusy(true);
    try {
      await createAllowlistEntry({ value: allowValue.trim(), type: allowType });
      setAllowValue("");
      setAllowRefresh((value) => value + 1);
    } catch (err) {
      setError(apiErrorMessage(err, t("Could not add allowlist entry.")));
    } finally {
      setAllowBusy(false);
    }
  }

  async function onDeleteAllowlist(id: number) {
    if (!canManageAllowlist || allowBusy) return;
    setAllowBusy(true);
    try {
      await deleteAllowlistEntry(id);
      setAllowRefresh((value) => value + 1);
    } catch (err) {
      setError(apiErrorMessage(err, t("Could not remove allowlist entry.")));
    } finally {
      setAllowBusy(false);
    }
  }

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
              <h2>{t("Allowlist")}</h2>
              <span className={`status-badge ${allowlistEnforced ? "status-badge--completed" : "status-badge--cancelled"}`}>
                {allowlistEnforced ? t("Enforced") : t("Open (empty)")}
              </span>
            </div>
            <div className="panel__body">
              <p className="field-help" style={{ marginTop: 0 }}>
                {t(
                  "When at least one entry is enabled, scans and new targets must match IP/CIDR/domain. Domains are re-checked after DNS resolution.",
                )}
              </p>
              {canManageAllowlist && (
                <form className="form-row" onSubmit={onAddAllowlist}>
                  <label htmlFor="allowlist-value">{t("Add entry")}</label>
                  <div className="scan-actions" style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                    <select
                      className="input input--select"
                      value={allowType}
                      onChange={(e) => setAllowType(e.target.value as AllowlistEntry["type"])}
                      disabled={allowBusy}
                    >
                      <option value="cidr">CIDR</option>
                      <option value="ip">IP</option>
                      <option value="domain">{t("Domain")}</option>
                    </select>
                    <input
                      id="allowlist-value"
                      value={allowValue}
                      onChange={(e) => setAllowValue(e.target.value)}
                      placeholder="192.0.2.0/24 or lab.example"
                      disabled={allowBusy}
                      required
                    />
                    <button type="submit" className="btn btn--primary" disabled={allowBusy || !allowValue.trim()}>
                      {t("Add")}
                    </button>
                  </div>
                </form>
              )}
              {allowlist.length === 0 ? (
                <p className="field-help">{t("No allowlist entries — all saved targets may be scanned.")}</p>
              ) : (
                <div className="table-wrap">
                  <table className="hosts">
                    <caption className="sr-only">{t("Allowlist")}</caption>
                    <thead>
                      <tr>
                        <th scope="col">{t("Value")}</th>
                        <th scope="col">{t("Type")}</th>
                        <th scope="col">{t("Actions")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {allowlist.map((entry) => (
                        <tr key={entry.id}>
                          <td className="mono">{entry.value}</td>
                          <td className="mono">{entry.type}</td>
                          <td className="scan-actions">
                            {canManageAllowlist && (
                              <button
                                type="button"
                                className="btn btn--danger"
                                disabled={allowBusy}
                                onClick={() => void onDeleteAllowlist(entry.id)}
                              >
                                {t("Delete")}
                              </button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </section>

          {info.signatures && (
            <section className="panel">
              <div className="panel__header">
                <h2>{t("Signatures pack")}</h2>
              </div>
              <div className="panel__body">
                <p className="field-help" style={{ marginTop: 0 }}>
                  {t(info.signatures.summary)}
                </p>
                <dl className="system-panel__meta">
                  <div>
                    <dt>{t("Pack version")}</dt>
                    <dd className="mono">{info.signatures.pack_version || "—"}</dd>
                  </div>
                  <div>
                    <dt>{t("Signatures")}</dt>
                    <dd className="mono">{info.signatures.count}</dd>
                  </div>
                  <div>
                    <dt>{t("IDs")}</dt>
                    <dd className="mono">{info.signatures.ids.join(", ") || "—"}</dd>
                  </div>
                </dl>
              </div>
            </section>
          )}

          {isAdmin && (
            <section className="panel">
              <div className="panel__header">
                <h2>{t("Recent audit")}</h2>
              </div>
              <div className="panel__body">
                {audit.length === 0 ? (
                  <p className="field-help">{t("No audit events yet.")}</p>
                ) : (
                  <div className="table-wrap">
                    <table className="hosts">
                      <caption className="sr-only">{t("Audit log")}</caption>
                      <thead>
                        <tr>
                          <th scope="col">{t("When")}</th>
                          <th scope="col">{t("Actor")}</th>
                          <th scope="col">{t("Action")}</th>
                          <th scope="col">{t("Summary")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {audit.map((event) => (
                          <tr key={event.id}>
                            <td>{new Date(event.created_at).toLocaleString()}</td>
                            <td className="mono">{event.actor || "—"}</td>
                            <td className="mono">{event.action}</td>
                            <td>{event.summary}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </section>
          )}

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
