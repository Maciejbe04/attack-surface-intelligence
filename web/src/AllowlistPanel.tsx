import { FormEvent, useEffect, useState } from "react";
import {
  AllowlistEntry,
  apiErrorMessage,
  createAllowlistEntry,
  deleteAllowlistEntry,
  listAllowlist,
} from "./api/scans";
import { Translate } from "./i18n";

type Props = {
  active: boolean;
  canManage: boolean;
  t: Translate;
};

export function AllowlistPanel({ active, canManage, t }: Props) {
  const [allowlist, setAllowlist] = useState<AllowlistEntry[]>([]);
  const [enforced, setEnforced] = useState(false);
  const [allowValue, setAllowValue] = useState("");
  const [allowType, setAllowType] = useState<AllowlistEntry["type"]>("cidr");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    if (!active) {
      setAllowlist([]);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    listAllowlist(controller.signal)
      .then((payload) => {
        if (controller.signal.aborted) return;
        setAllowlist(payload.results);
        setEnforced(payload.enforced);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        if (err instanceof DOMException && err.name === "AbortError") return;
        setAllowlist([]);
        setEnforced(false);
        setError(apiErrorMessage(err, t("Could not load allowlist.")));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [active, refresh, t]);

  async function onAdd(event: FormEvent) {
    event.preventDefault();
    if (!canManage || !allowValue.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      await createAllowlistEntry({ value: allowValue.trim(), type: allowType });
      setAllowValue("");
      setRefresh((value) => value + 1);
    } catch (err) {
      setError(apiErrorMessage(err, t("Could not add allowlist entry.")));
    } finally {
      setBusy(false);
    }
  }

  async function onDelete(id: number) {
    if (!canManage || busy) return;
    setBusy(true);
    setError(null);
    try {
      await deleteAllowlistEntry(id);
      setRefresh((value) => value + 1);
    } catch (err) {
      setError(apiErrorMessage(err, t("Could not remove allowlist entry.")));
    } finally {
      setBusy(false);
    }
  }

  if (!active) return null;

  return (
    <>
      <header className="page-header">
        <h1>{t("Allowlist")}</h1>
        <p>
          {t(
            "When at least one entry is enabled, scans and new targets must match IP/CIDR/domain. Domains are re-checked after DNS resolution.",
          )}
        </p>
      </header>

      {loading && (
        <p className="field-help" role="status">
          {t("Loading…")}
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

      <section className="panel">
        <div className="panel__header">
          <h2>{t("Allowlist")}</h2>
          <span
            className={`status-badge ${enforced ? "status-badge--completed" : "status-badge--cancelled"}`}
          >
            {enforced ? t("Enforced") : t("Open (empty)")}
          </span>
        </div>
        <div className="panel__body">
          {canManage && (
            <form className="form-row" onSubmit={onAdd}>
              <label htmlFor="allowlist-value">{t("Add entry")}</label>
              <div className="scan-actions" style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                <select
                  className="input input--select"
                  value={allowType}
                  onChange={(e) => setAllowType(e.target.value as AllowlistEntry["type"])}
                  disabled={busy}
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
                  disabled={busy}
                  required
                />
                <button type="submit" className="btn btn--primary" disabled={busy || !allowValue.trim()}>
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
                    {canManage && <th scope="col">{t("Actions")}</th>}
                  </tr>
                </thead>
                <tbody>
                  {allowlist.map((entry) => (
                    <tr key={entry.id}>
                      <td className="mono">{entry.value}</td>
                      <td className="mono">{entry.type}</td>
                      {canManage && (
                        <td className="scan-actions">
                          <button
                            type="button"
                            className="btn btn--danger"
                            disabled={busy}
                            onClick={() => void onDelete(entry.id)}
                          >
                            {t("Delete")}
                          </button>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>
    </>
  );
}
