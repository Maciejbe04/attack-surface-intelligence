import { FormEvent, useMemo, useState } from "react";
import {
  apiErrorMessage,
  createTarget,
  discoverPassive,
  PassiveDiscoveryResult,
  Target,
} from "./api/scans";
import { Translate } from "./i18n";

type Props = {
  targets: Target[];
  onTargetsAdded: (targets: Target[]) => void;
  pushToast: (kind: "ok" | "error", title: string, message: string) => void;
  t: Translate;
};

export function PassiveDiscoveryPanel({
  targets,
  onTargetsAdded,
  pushToast,
  t,
}: Props) {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<PassiveDiscoveryResult | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");

  const saved = useMemo(
    () => new Set(targets.map((target) => target.address.toLowerCase())),
    [targets],
  );
  const candidates = useMemo(() => {
    if (!result) return [];
    return result.type === "ip" ? [result.query] : result.subdomains;
  }, [result]);

  async function onDiscover(event: FormEvent) {
    event.preventDefault();
    const value = query.trim();
    if (!value) return;
    setLoading(true);
    setError("");
    try {
      const payload = await discoverPassive(value);
      setResult(payload);
      setQuery(payload.query);
      setSelected(
        new Set(payload.type === "ip" ? [payload.query] : payload.subdomains),
      );
    } catch (err) {
      setResult(null);
      setSelected(new Set());
      setError(apiErrorMessage(err, t("Passive discovery failed.")));
    } finally {
      setLoading(false);
    }
  }

  function toggleCandidate(address: string) {
    setSelected((previous) => {
      const next = new Set(previous);
      if (next.has(address)) next.delete(address);
      else next.add(address);
      return next;
    });
  }

  async function addSelected() {
    if (!result) return;
    const addresses = candidates.filter(
      (address) => selected.has(address) && !saved.has(address.toLowerCase()),
    );
    if (addresses.length === 0) return;
    setAdding(true);
    setError("");
    const created: Target[] = [];
    const failures: string[] = [];
    for (const address of addresses) {
      try {
        created.push(
          await createTarget({
            address,
            type: result.type === "ip" ? "ip" : "domain",
            comment:
              result.type === "domain"
                ? "Passive discovery: crt.sh"
                : "Passive discovery: RDAP",
          }),
        );
      } catch (err) {
        failures.push(
          `${address}: ${apiErrorMessage(err, t("Target not added"))}`,
        );
      }
    }
    if (created.length > 0) {
      onTargetsAdded(created);
      setSelected((previous) => {
        const next = new Set(previous);
        for (const target of created) next.delete(target.address);
        return next;
      });
      pushToast(
        "ok",
        t("Passive targets added"),
        `${created.length} ${t("targets added")}`,
      );
    }
    if (failures.length > 0) {
      const message = failures.slice(0, 3).join(" · ");
      setError(message);
      pushToast("error", t("Some targets were not added"), message);
    }
    setAdding(false);
  }

  const rdap = result?.rdap;
  const addableCount = candidates.filter(
    (address) => selected.has(address) && !saved.has(address.toLowerCase()),
  ).length;

  return (
    <section className="panel passive-discovery">
      <div className="panel__header">
        <h2>{t("Passive discovery")}</h2>
      </div>
      <form className="panel__body" onSubmit={onDiscover} aria-busy={loading}>
        <div className="form-row">
          <label htmlFor="passive-query">{t("Domain or IP")}</label>
          <div>
            <div className="passive-discovery__query">
              <input
                id="passive-query"
                className={`input ${error ? "is-invalid" : ""}`}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="example.com / 192.0.2.10"
                autoComplete="off"
              />
              <button
                type="submit"
                className="btn btn--primary"
                disabled={loading || !query.trim()}
              >
                {loading ? t("Discovering…") : t("Discover")}
              </button>
            </div>
            {error && <p className="field-error">{error}</p>}
            <p className="field-help">
              {t("Certificate Transparency subdomains and RDAP ownership data. No scan is started.")}
            </p>
          </div>
        </div>
      </form>

      {result && (
        <div className="passive-discovery__results">
          <div className="passive-discovery__summary">
            <strong className="mono">{result.query}</strong>
            {result.cached && <span className="status-badge status-badge--muted">{t("Cached")}</span>}
            {rdap && (
              <dl>
                {(rdap.name || rdap.handle) && (
                  <>
                    <dt>{t("Owner / handle")}</dt>
                    <dd>{rdap.name || rdap.handle}</dd>
                  </>
                )}
                {rdap.network && (
                  <>
                    <dt>{t("Network")}</dt>
                    <dd className="mono">{rdap.network}</dd>
                  </>
                )}
                {rdap.country && (
                  <>
                    <dt>{t("Country")}</dt>
                    <dd>{rdap.country}</dd>
                  </>
                )}
                {rdap.asns.length > 0 && (
                  <>
                    <dt>ASN</dt>
                    <dd>{rdap.asns.map((asn) => `AS${asn}`).join(", ")}</dd>
                  </>
                )}
              </dl>
            )}
          </div>

          {result.warnings.map((warning) => (
            <p className="field-help" key={warning}>
              {t("Provider warning")}: {warning}
            </p>
          ))}

          {candidates.length > 0 ? (
            <>
              <div className="passive-discovery__list" role="group" aria-label={t("Passive targets")}>
                {candidates.map((address) => {
                  const alreadySaved = saved.has(address.toLowerCase());
                  return (
                    <label key={address} className="passive-discovery__item">
                      <input
                        type="checkbox"
                        checked={selected.has(address)}
                        disabled={alreadySaved || adding}
                        onChange={() => toggleCandidate(address)}
                      />
                      <span className="mono">{address}</span>
                      {alreadySaved && <small>{t("already saved")}</small>}
                    </label>
                  );
                })}
              </div>
              <div className="panel__footer passive-discovery__actions">
                <span className="field-help">
                  {candidates.length} {t("found")} · {addableCount} {t("selected")}
                </span>
                <button
                  type="button"
                  className="btn btn--primary"
                  disabled={adding || addableCount === 0}
                  onClick={() => void addSelected()}
                >
                  {adding ? t("Adding…") : t("Add selected targets")}
                </button>
              </div>
            </>
          ) : (
            <p className="passive-discovery__empty field-help">
              {t("No certificate names found. RDAP data may still be available above.")}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
