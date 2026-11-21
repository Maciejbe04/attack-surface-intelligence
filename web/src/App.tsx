import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  ACTIVE_SCAN_STATUSES,
  apiErrorMessage,
  cancelScan,
  createScan,
  createTarget,
  deleteTarget,
  exportScanToDefectDojo,
  getScan,
  listScans,
  listTargets,
  Scan,
  ScanDetail,
  ScanModule,
  ScanStatus,
  Target,
  TargetType,
} from "./api/scans";
import { apiFetch, AuthUser, ensureCsrf } from "./auth";
import { AppFooter } from "./AppFooter";
import { Language, Translate, useLanguage } from "./i18n";
import { LanguageSelect } from "./LanguageSelect";
import { Logo } from "./Logo";
import { ModulePanel } from "./ModulePanel";
import {
  createInitialModuleState,
  ModuleRegistryState,
  summarizeFilters,
} from "./modules";
import { ScanConsole } from "./ScanConsole";
import { useHighContrast } from "./useHighContrast";
import { APP_NAME, APP_VERSION } from "./version";

type NavId = "dashboard" | "targets" | "scans";

type Toast = {
  id: string;
  kind: "error" | "ok";
  title: string;
  message: string;
};

function detectType(value: string): TargetType {
  if (value.includes("/")) return "cidr";
  if (/^\d{1,3}(\.\d{1,3}){3}$/.test(value)) return "ip";
  return "domain";
}

function isValidTarget(value: string): boolean {
  const v = value.trim();
  if (!v || v.includes(" ")) return false;
  if (detectType(v) === "ip") {
    return v.split(".").every((part) => {
      const n = Number(part);
      return Number.isInteger(n) && n >= 0 && n <= 255;
    });
  }
  if (detectType(v) === "cidr") {
    const [ip, prefix] = v.split("/");
    const p = Number(prefix);
    return (
      isValidTarget(ip) &&
      detectType(ip) === "ip" &&
      Number.isInteger(p) &&
      p >= 0 &&
      p <= 32
    );
  }
  return /^[a-z0-9.-]+$/i.test(v) && v.includes(".");
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

const STATUS_LABELS: Record<ScanStatus, string> = {
  queued: "Queued",
  running: "Running",
  cancel_requested: "Cancel requested",
  completed: "Completed",
  partial: "Partial",
  failed: "Failed",
  cancelled: "Cancelled",
};

function ScanTable({
  scans,
  emptyTitle,
  emptyMessage,
  canMutate,
  canExport,
  cancellingIds,
  exportingIds,
  focusedScanId,
  onCancel,
  onExport,
  onOpenConsole,
  t,
}: {
  scans: Scan[];
  emptyTitle: string;
  emptyMessage: string;
  canMutate: boolean;
  canExport: boolean;
  cancellingIds: Set<number>;
  exportingIds: Set<number>;
  focusedScanId: number | null;
  onCancel: (scan: Scan) => void;
  onExport: (scan: Scan) => void;
  onOpenConsole: (scan: Scan) => void;
  t: Translate;
}) {
  if (scans.length === 0) {
    return (
      <div className="empty">
        <strong>{t(emptyTitle)}</strong>
        {t(emptyMessage)}
      </div>
    );
  }

  return (
    <table className="hosts">
      <caption className="sr-only">{t("Discovery scan runs")}</caption>
      <thead>
        <tr>
          <th scope="col">{t("Scan")}</th>
          <th scope="col">{t("Targets")}</th>
          <th scope="col">{t("Modules")}</th>
          <th scope="col">{t("Status")}</th>
          <th scope="col">{t("Progress")}</th>
          <th scope="col">{t("Batches")}</th>
          <th scope="col">{t("Queued")}</th>
          <th scope="col">{t("Actions")}</th>
        </tr>
      </thead>
      <tbody>
        {scans.map((scan) => {
          const active = ACTIVE_SCAN_STATUSES.has(scan.status);
          const cancelling = cancellingIds.has(scan.id);
          const exporting = exportingIds.has(scan.id);
          const focused = focusedScanId === scan.id;
          const exportable =
            canExport &&
            scan.completed_batches > 0 &&
            ["completed", "partial", "failed"].includes(scan.status);
          return (
            <tr key={scan.id} className={focused ? "is-selected" : undefined}>
              <td className="mono">#{scan.id}</td>
              <td className="scan-targets">
                {scan.targets.length > 0 ? scan.targets.join(", ") : "—"}
              </td>
              <td>
                {scan.modules
                  .map((module) => `${module.id} (${summarizeFilters(module.filters)})`)
                  .join("; ")}
              </td>
              <td>
                <span className={`status-badge status-badge--${scan.status}`}>
                  {t(STATUS_LABELS[scan.status])}
                </span>
                {scan.error && <span className="scan-error">{scan.error}</span>}
              </td>
              <td>
                <div className="scan-progress">
                  <progress value={scan.progress} max={100} aria-label={t("Scan progress")} />
                  <span>{scan.progress}%</span>
                </div>
              </td>
              <td>
                {scan.completed_batches}/{scan.total_batches}
                {scan.failed_batches > 0 && (
                  <span className="scan-error">
                    {t("Failed")}: {scan.failed_batches}
                  </span>
                )}
              </td>
              <td>{new Date(scan.created_at).toLocaleString()}</td>
              <td className="scan-actions">
                <button
                  type="button"
                  className="btn btn--normal"
                  onClick={() => onOpenConsole(scan)}
                  aria-pressed={focused}
                >
                  {focused ? t("Viewing log") : t("View log")}
                </button>
                {active && canMutate && (
                  <button
                    type="button"
                    className="btn btn--danger"
                    onClick={() => onCancel(scan)}
                    disabled={cancelling || scan.status === "cancel_requested"}
                    aria-busy={cancelling}
                  >
                    {cancelling ? t("Cancelling…") : t("Cancel")}
                  </button>
                )}
                {exportable && (
                  <button
                    type="button"
                    className="btn btn--normal"
                    onClick={() => onExport(scan)}
                    disabled={exporting}
                    aria-busy={exporting}
                  >
                    {exporting ? t("Exporting…") : t("Send to DefectDojo")}
                  </button>
                )}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function LoginScreen({
  onAuthenticated,
  highContrast,
  onToggleContrast,
  language,
  onLanguageChange,
  t,
}: {
  onAuthenticated: (user: AuthUser) => void;
  highContrast: boolean;
  onToggleContrast: () => void;
  language: Language;
  onLanguageChange: (language: Language) => void;
  t: Translate;
}) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [mfaCode, setMfaCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submitPassword(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await ensureCsrf();
      const response = await apiFetch("/api/auth/login/", {
        method: "POST",
        body: JSON.stringify({ username, password }),
      });
      const data = await response.json();
      if (!response.ok) {
        setError(data.detail || t("Sign-in failed."));
        return;
      }
      if (data.mfa_required) {
        setMfaToken(data.mfa_token);
        return;
      }
      onAuthenticated(data.user as AuthUser);
    } catch {
      setError(t("Cannot reach authentication API."));
    } finally {
      setBusy(false);
    }
  }

  async function submitMfa(event: FormEvent) {
    event.preventDefault();
    if (!mfaToken) return;
    setBusy(true);
    setError(null);
    try {
      const response = await apiFetch("/api/auth/mfa/verify/", {
        method: "POST",
        body: JSON.stringify({ mfa_token: mfaToken, code: mfaCode }),
      });
      const data = await response.json();
      if (!response.ok) {
        setError(data.detail || t("Invalid MFA code."));
        if (data.mfa_token) setMfaToken(data.mfa_token);
        return;
      }
      onAuthenticated(data.user as AuthUser);
    } catch {
      setError(t("Cannot reach authentication API."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-page">
      <a className="skip-link" href="#login-form">
        {t("Skip to sign-in form")}
      </a>
      <div className="login-language">
        <LanguageSelect
          language={language}
          onChange={onLanguageChange}
          label={t("Language")}
        />
      </div>
      <main className="login-card panel" id="login-form" aria-labelledby="login-title">
        <div className="panel__header">
          <h2 id="login-title">
            {mfaToken ? t("Multi-factor authentication") : t("Sign in")}
          </h2>
        </div>
        <div className="panel__body">
          <div className="login-brand">
            <Logo />
          </div>
          <p className="field-help" style={{ marginBottom: 16 }} id="login-help">
            {mfaToken
              ? t("Enter the 6-digit code from your authenticator app.")
              : t("Use your console username and password.")}
          </p>

          {!mfaToken && (
            <div className="flash flash--error" role="alert">
              <div>
                <strong>{t("Warning: MFA is disabled")}</strong>
                <p>
                  {t(
                    "Multi-factor authentication is currently turned off for this console. Accounts are protected by password only.",
                  )}
                </p>
              </div>
            </div>
          )}

          {error && (
            <div className="flash flash--error" role="alert">
              <div>
                <strong>{t("Authentication error")}</strong>
                <p>{error}</p>
              </div>
            </div>
          )}

          {!mfaToken ? (
            <form onSubmit={submitPassword} aria-describedby="login-help">
              <div className="form-row">
                <label htmlFor="username">{t("Username")}</label>
                <input
                  id="username"
                  className="input"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username"
                  required
                  aria-required="true"
                />
              </div>
              <div className="form-row">
                <label htmlFor="password">{t("Password")}</label>
                <input
                  id="password"
                  type="password"
                  className="input"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  required
                  aria-required="true"
                />
              </div>
              <div className="actions">
                <button type="submit" className="btn btn--primary" disabled={busy} aria-busy={busy}>
                  {busy ? t("Signing in…") : t("Sign in")}
                </button>
              </div>
            </form>
          ) : (
            <form onSubmit={submitMfa} aria-describedby="login-help">
              <div className="form-row">
                <label htmlFor="mfa">{t("MFA code")}</label>
                <div>
                  <input
                    id="mfa"
                    className="input"
                    inputMode="numeric"
                    pattern="[0-9]*"
                    maxLength={6}
                    value={mfaCode}
                    onChange={(e) => setMfaCode(e.target.value.replace(/\D/g, ""))}
                    autoComplete="one-time-code"
                    required
                    aria-required="true"
                    aria-describedby="mfa-help"
                  />
                  <p className="field-help" id="mfa-help">
                    {t("TOTP from Google Authenticator, 1Password, or Authy.")}
                  </p>
                </div>
              </div>
              <div className="actions">
                <button
                  type="submit"
                  className="btn btn--primary"
                  disabled={busy || mfaCode.length < 6}
                  aria-busy={busy}
                >
                  {busy ? t("Verifying…") : t("Verify")}
                </button>
                <button
                  type="button"
                  className="btn btn--normal"
                  disabled={busy}
                  onClick={() => {
                    setMfaToken(null);
                    setMfaCode("");
                    setError(null);
                  }}
                >
                  {t("Back")}
                </button>
              </div>
            </form>
          )}
        </div>
      </main>
      <AppFooter
        highContrast={highContrast}
        onToggleContrast={onToggleContrast}
        language={language}
        onLanguageChange={onLanguageChange}
        t={t}
      />
      <div id="a11y-help" className="sr-only" tabIndex={-1}>
        {APP_NAME} version {APP_VERSION}. Keyboard users can tab through form fields. Screen
        reader users: alerts are announced automatically. Use High contrast for stronger colors.
      </div>
    </div>
  );
}

function DashboardLoader({ t }: { t: Translate }) {
  return (
    <div className="dashboard-loader" role="status" aria-live="polite">
      <div className="dashboard-loader__card">
        <Logo />
        <div className="dashboard-loader__bar" aria-hidden="true">
          <span />
        </div>
        <p>{t("Preparing dashboard…")}</p>
      </div>
    </div>
  );
}

export function App() {
  const { highContrast, toggleHighContrast } = useHighContrast();
  const { language, setLanguage, t } = useLanguage();
  const [bootstrapping, setBootstrapping] = useState(true);
  const [enteringDashboard, setEnteringDashboard] = useState(false);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [nav, setNav] = useState<NavId>("dashboard");
  const [targets, setTargets] = useState<Target[]>([]);
  const [scans, setScans] = useState<Scan[]>([]);
  const [dataLoading, setDataLoading] = useState(false);
  const [scanRefreshKey, setScanRefreshKey] = useState(0);
  const [draft, setDraft] = useState("");
  const [draftComment, setDraftComment] = useState("");
  const [draftError, setDraftError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [flash, setFlash] = useState<string | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [probeHost, setProbeHost] = useState("");
  const [addPending, setAddPending] = useState(false);
  const [removePending, setRemovePending] = useState(false);
  const [scanPending, setScanPending] = useState<"dashboard" | "targets" | null>(null);
  const [cancellingIds, setCancellingIds] = useState<Set<number>>(new Set());
  const [exportingIds, setExportingIds] = useState<Set<number>>(new Set());
  const [consoleScanId, setConsoleScanId] = useState<number | null>(null);
  const [consoleScan, setConsoleScan] = useState<ScanDetail | null>(null);
  const [consoleLoading, setConsoleLoading] = useState(false);
  const [moduleState, setModuleState] = useState<ModuleRegistryState>(() =>
    createInitialModuleState(),
  );
  const canMutate = user?.role === "admin" || user?.role === "operator";
  const canExport = Boolean(user && user.role !== "viewer");

  function pushToast(kind: Toast["kind"], title: string, message: string) {
    const id = crypto.randomUUID();
    setToasts((prev) => [...prev, { id, kind, title, message }]);
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 6000);
  }

  function completeAuthentication(authenticatedUser: AuthUser) {
    setEnteringDashboard(true);
    window.setTimeout(() => {
      setUser(authenticatedUser);
      setEnteringDashboard(false);
    }, 300);
  }

  function dismissToast(id: string) {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }

  useEffect(() => {
    apiFetch("/api/auth/me/")
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((me) => {
        if (me.authenticated) setUser(me.user as AuthUser);
      })
      .catch(() => {
        pushToast("error", "No connection", "Cannot reach SurfaceX API. Check Docker Compose.");
      })
      .finally(() => setBootstrapping(false));
  }, []);

  useEffect(() => {
    if (!user) {
      setTargets([]);
      setSelected(new Set());
      setProbeHost("");
      return;
    }
    const controller = new AbortController();
    setDataLoading(true);
    listTargets(controller.signal)
      .then(setTargets)
      .catch((error: unknown) => {
        if (!isAbortError(error)) {
          pushToast(
            "error",
            t("Targets unavailable"),
            apiErrorMessage(error, t("Could not load targets.")),
          );
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setDataLoading(false);
      });
    return () => controller.abort();
  }, [user?.id, language]);

  useEffect(() => {
    if (!user) {
      setScans([]);
      return;
    }

    let disposed = false;
    let timer: number | undefined;
    let controller: AbortController | null = null;

    const clearTimer = () => {
      if (timer !== undefined) {
        window.clearTimeout(timer);
        timer = undefined;
      }
    };

    const poll = async () => {
      if (disposed || document.hidden || controller) return;
      controller = new AbortController();
      try {
        const nextScans = await listScans(controller.signal);
        if (disposed) return;
        setScans(nextScans);
        if (nextScans.some((scan) => ACTIVE_SCAN_STATUSES.has(scan.status))) {
          timer = window.setTimeout(poll, 2000);
        }
      } catch (error) {
        if (!disposed && !isAbortError(error)) {
          pushToast(
            "error",
            t("Scans unavailable"),
            apiErrorMessage(error, t("Could not load scans.")),
          );
          timer = window.setTimeout(poll, 5000);
        }
      } finally {
        controller = null;
      }
    };

    const onVisibilityChange = () => {
      if (document.hidden) {
        clearTimer();
        controller?.abort();
      } else {
        clearTimer();
        timer = window.setTimeout(poll, 0);
      }
    };

    document.addEventListener("visibilitychange", onVisibilityChange);
    void poll();
    return () => {
      disposed = true;
      clearTimer();
      controller?.abort();
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [user?.id, language, scanRefreshKey]);

  useEffect(() => {
    if (!user || consoleScanId === null) {
      setConsoleScan(null);
      setConsoleLoading(false);
      return;
    }

    let disposed = false;
    let timer: number | undefined;
    let controller: AbortController | null = null;

    const clearTimer = () => {
      if (timer !== undefined) {
        window.clearTimeout(timer);
        timer = undefined;
      }
    };

    const pollDetail = async () => {
      if (disposed || document.hidden || controller) return;
      controller = new AbortController();
      setConsoleLoading(true);
      try {
        const detail = await getScan(consoleScanId, controller.signal);
        if (disposed) return;
        setConsoleScan(detail);
        setScans((prev) =>
          prev.map((item) =>
            item.id === detail.id
              ? {
                  ...item,
                  status: detail.status,
                  progress: detail.progress,
                  completed_batches: detail.completed_batches,
                  failed_batches: detail.failed_batches,
                  result_summary: detail.result_summary,
                  error: detail.error,
                  started_at: detail.started_at,
                  finished_at: detail.finished_at,
                }
              : item,
          ),
        );
        if (ACTIVE_SCAN_STATUSES.has(detail.status)) {
          timer = window.setTimeout(pollDetail, 1500);
        }
      } catch (error) {
        if (!disposed && !isAbortError(error)) {
          pushToast(
            "error",
            t("Console unavailable"),
            apiErrorMessage(error, t("Could not load scan activity.")),
          );
          timer = window.setTimeout(pollDetail, 4000);
        }
      } finally {
        controller = null;
        if (!disposed) setConsoleLoading(false);
      }
    };

    const onVisibilityChange = () => {
      if (document.hidden) {
        clearTimer();
        controller?.abort();
      } else {
        clearTimer();
        timer = window.setTimeout(pollDetail, 0);
      }
    };

    document.addEventListener("visibilitychange", onVisibilityChange);
    void pollDetail();
    return () => {
      disposed = true;
      clearTimer();
      controller?.abort();
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [user?.id, language, consoleScanId, scanRefreshKey]);

  useEffect(() => {
    if (!probeHost && targets.length > 0) {
      setProbeHost(targets[0].address);
    }
  }, [targets, probeHost]);

  const allSelected = targets.length > 0 && selected.size === targets.length;
  const someSelected = selected.size > 0 && selected.size < targets.length;
  const selectedTargets = useMemo(
    () => targets.filter((t) => selected.has(t.id)),
    [targets, selected],
  );

  async function signOut() {
    try {
      await apiFetch("/api/auth/logout/", { method: "POST", body: "{}" });
    } catch {
      pushToast("error", "No connection", "Sign-out request failed.");
    }
    setUser(null);
  }

  function toggleAll() {
    if (allSelected) {
      setSelected(new Set());
      return;
    }
    setSelected(new Set(targets.map((t) => t.id)));
  }

  function toggleOne(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleModuleEnabled(id: string) {
    setModuleState((prev) => {
      const current = prev[id];
      if (!current) return prev;

      if (id === "full-pipeline" && !current.enabled) {
        const next: ModuleRegistryState = {};
        for (const [key, cfg] of Object.entries(prev)) {
          next[key] = {
            ...cfg,
            enabled: key === "full-pipeline",
            expanded: key === "full-pipeline" ? true : cfg.expanded,
          };
        }
        return next;
      }

      const next: ModuleRegistryState = {
        ...prev,
        [id]: {
          ...current,
          enabled: !current.enabled,
        },
      };
      if (id !== "full-pipeline" && next["full-pipeline"]?.enabled) {
        next["full-pipeline"] = { ...next["full-pipeline"], enabled: false };
      }
      return next;
    });
  }

  function toggleModuleExpanded(id: string) {
    setModuleState((prev) => {
      const current = prev[id];
      if (!current) return prev;
      return Object.fromEntries(
        Object.entries(prev).map(([moduleId, config]) => [
          moduleId,
          {
            ...config,
            expanded: moduleId === id ? !current.expanded : false,
          },
        ]),
      );
    });
  }

  function updateModuleFilter(id: string, key: string, value: string | number | boolean) {
    setModuleState((prev) => {
      const current = prev[id];
      if (!current) return prev;
      return {
        ...prev,
        [id]: {
          ...current,
          filters: { ...current.filters, [key]: value },
        },
      };
    });
  }

  function selectedModules(): ScanModule[] {
    return Object.entries(moduleState)
      .filter(([, config]) => config.enabled)
      .map(([id, config]) => ({ id, filters: config.filters }));
  }

  async function onAdd(event: FormEvent) {
    event.preventDefault();
    if (!canMutate || addPending) return;
    const value = draft.trim();
    if (!isValidTarget(value)) {
      setDraftError(t("Enter a valid IPv4, CIDR (e.g. 10.0.0.0/24), or hostname."));
      return;
    }
    if (targets.some((target) => target.address.toLowerCase() === value.toLowerCase())) {
      setDraftError(t("This target is already on the list."));
      return;
    }

    setAddPending(true);
    try {
      const target = await createTarget({
        address: value,
        type: detectType(value),
        comment: draftComment.trim(),
      });
      setTargets((prev) =>
        [...prev, target].sort((a, b) => a.address.localeCompare(b.address)),
      );
      setDraft("");
      setDraftComment("");
      setDraftError(null);
      setFlash(`${t("Added")} ${target.address}`);
      if (!probeHost) setProbeHost(target.address);
    } catch (error) {
      const message = apiErrorMessage(error, t("Could not add target."));
      setDraftError(message);
      pushToast("error", t("Target not added"), message);
    } finally {
      setAddPending(false);
    }
  }

  async function removeSelected() {
    if (!canMutate || selected.size === 0 || removePending) return;
    const ids = [...selected];
    setRemovePending(true);
    const results = await Promise.allSettled(ids.map((id) => deleteTarget(id)));
    const removedIds = new Set(
      ids.filter((_, index) => results[index].status === "fulfilled"),
    );
    const failed = results.length - removedIds.size;
    const removedTargets = targets.filter((target) => removedIds.has(target.id));
    setTargets((prev) => prev.filter((target) => !removedIds.has(target.id)));
    setSelected((prev) => new Set([...prev].filter((id) => !removedIds.has(id))));
    if (removedTargets.some((target) => target.address === probeHost)) setProbeHost("");
    if (removedIds.size > 0) {
      setFlash(`${t("Removed targets")}: ${removedIds.size}`);
    }
    if (failed > 0) {
      const firstFailure = results.find(
        (result): result is PromiseRejectedResult => result.status === "rejected",
      );
      pushToast(
        "error",
        t("Some targets were not removed"),
        apiErrorMessage(firstFailure?.reason, t("Could not remove selected targets.")),
      );
    }
    setRemovePending(false);
  }

  async function queueScan(targetIds: number[], source: "dashboard" | "targets") {
    if (!canMutate || scanPending || targetIds.length === 0) return;
    const modules = selectedModules();
    if (modules.length === 0) {
      pushToast("error", t("No modules"), t("Select at least one discovery module."));
      return;
    }
    setScanPending(source);
    try {
      const scan = await createScan({
        target_ids: targetIds,
        modules,
        client_request_id: crypto.randomUUID(),
      });
      setScans((prev) => [scan, ...prev.filter((item) => item.id !== scan.id)]);
      setConsoleScanId(scan.id);
      setConsoleScan(scan);
      setScanRefreshKey((value) => value + 1);
      pushToast(
        "ok",
        t("Scan queued"),
        `${t("Targets")}: ${targetIds.length} · ${t("Modules")}: ${modules.length}`,
      );
      if (source === "targets") {
        setFlash(`${t("Scan queued for targets")}: ${targetIds.length}`);
      }
    } catch (error) {
      pushToast(
        "error",
        t("Scan not queued"),
        apiErrorMessage(error, t("Could not queue scan.")),
      );
    } finally {
      setScanPending(null);
    }
  }

  function queueSelected() {
    void queueScan(
      selectedTargets.map((target) => target.id),
      "targets",
    );
  }

  function runProbe() {
    const host = probeHost.trim();
    if (!host) {
      pushToast("error", t("Host required"), t("Select a saved host / IP to probe."));
      return;
    }
    const target = targets.find(
      (item) => item.address.toLowerCase() === host.toLowerCase(),
    );
    if (!target) {
      pushToast("error", t("Saved target required"), t("Choose a target saved in Targets."));
      return;
    }
    void queueScan([target.id], "dashboard");
  }

  async function onCancelScan(scan: Scan) {
    if (!canMutate || cancellingIds.has(scan.id) || !ACTIVE_SCAN_STATUSES.has(scan.status)) return;
    setCancellingIds((prev) => new Set(prev).add(scan.id));
    try {
      const updated = await cancelScan(scan.id);
      setScans((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      setScanRefreshKey((value) => value + 1);
      pushToast("ok", t("Cancellation requested"), `${t("Scan")} #${scan.id}`);
    } catch (error) {
      pushToast(
        "error",
        t("Cancellation failed"),
        apiErrorMessage(error, t("Could not cancel scan.")),
      );
    } finally {
      setCancellingIds((prev) => {
        const next = new Set(prev);
        next.delete(scan.id);
        return next;
      });
    }
  }

  async function onExportScan(scan: Scan) {
    if (!canExport || exportingIds.has(scan.id)) return;
    setExportingIds((prev) => new Set(prev).add(scan.id));
    try {
      const result = await exportScanToDefectDojo(scan.id);
      pushToast(
        "ok",
        t("Sent to DefectDojo"),
        `${t("Findings")}: ${result.finding_count}${
          result.test ? ` · ${t("Test")}: #${result.test}` : ""
        }`,
      );
    } catch (error) {
      pushToast(
        "error",
        t("DefectDojo export failed"),
        apiErrorMessage(error, t("Could not send scan results to DefectDojo.")),
      );
    } finally {
      setExportingIds((prev) => {
        const next = new Set(prev);
        next.delete(scan.id);
        return next;
      });
    }
  }

  if (bootstrapping) {
    return (
      <div className="login-page" role="status" aria-live="polite">
        <p className="field-help">Loading {APP_NAME} console…</p>
      </div>
    );
  }

  if (enteringDashboard) {
    return <DashboardLoader t={t} />;
  }

  if (!user) {
    return (
      <LoginScreen
        onAuthenticated={completeAuthentication}
        highContrast={highContrast}
        onToggleContrast={toggleHighContrast}
        language={language}
        onLanguageChange={setLanguage}
        t={t}
      />
    );
  }

  return (
    <div className="app">
      <a className="skip-link" href="#main-content">
        {t("Skip to main content")}
      </a>
      <header className="topnav" role="banner">
        <a className="topnav__brand" href="/" aria-label={`${APP_NAME} home`}>
          <Logo />
        </a>
        <button
          type="button"
          className="btn btn--normal topnav__contrast"
          aria-pressed={highContrast}
          onClick={toggleHighContrast}
        >
          {highContrast ? t("Standard contrast") : t("High contrast")}
        </button>
        <LanguageSelect
          language={language}
          onChange={setLanguage}
          label={t("Language")}
          className="language-select--topnav"
        />
        <button type="button" className="btn btn--normal topnav__signout" onClick={signOut}>
          {t("Sign out")}
        </button>
      </header>

      <div className="toast-stack" aria-live="polite" aria-relevant="additions">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`toast ${toast.kind === "error" ? "toast--error" : "toast--ok"}`}
            role={toast.kind === "error" ? "alert" : "status"}
          >
            <div>
              <strong>{toast.title}</strong>
              <p>{toast.message}</p>
            </div>
            <button
              type="button"
              className="toast__close"
              aria-label={t("Dismiss")}
              onClick={() => dismissToast(toast.id)}
            >
              ×
            </button>
          </div>
        ))}
      </div>

      <div className="layout">
        <nav className="sidenav" aria-label={t("Primary")}>
          <div className="sidenav__section" id="nav-section-label">
            {t("Attack surface")}
          </div>
          <button
            type="button"
            className={`sidenav__item ${nav === "dashboard" ? "is-active" : ""}`}
            aria-current={nav === "dashboard" ? "page" : undefined}
            onClick={() => setNav("dashboard")}
          >
            {t("Dashboard")}
          </button>
          <button
            type="button"
            className={`sidenav__item ${nav === "targets" ? "is-active" : ""}`}
            aria-current={nav === "targets" ? "page" : undefined}
            onClick={() => setNav("targets")}
          >
            {t("Targets")}
          </button>
          <button
            type="button"
            className={`sidenav__item ${nav === "scans" ? "is-active" : ""}`}
            aria-current={nav === "scans" ? "page" : undefined}
            onClick={() => setNav("scans")}
          >
            {t("Scans")}
          </button>
        </nav>

        <main
          className="content content--enter"
          id="main-content"
          tabIndex={-1}
          key={nav}
          aria-busy={dataLoading}
        >
          {nav === "dashboard" && (
            <>
              <header className="page-header">
                <h1>{t("Dashboard")}</h1>
                <p>
                  {t(
                    "Pick a host and run discovery modules. SurfaceX probes only — no login, brute force, or exploitation.",
                  )}
                </p>
              </header>

              <section className="panel">
                <div className="panel__header">
                  <h2>{t("Target host")}</h2>
                </div>
                <div className="panel__body">
                  <div className="form-row">
                    <label htmlFor="probe-host">{t("Host / IP")}</label>
                    <div>
                      <input
                        id="probe-host"
                        className="input"
                        list="known-hosts"
                        value={probeHost}
                        onChange={(e) => setProbeHost(e.target.value)}
                        placeholder="10.0.0.15 or app.example.lab"
                        autoComplete="off"
                        spellCheck={false}
                      />
                      <datalist id="known-hosts">
                        {targets.map((target) => (
                          <option key={target.id} value={target.address} />
                        ))}
                      </datalist>
                      <p className="field-help">
                        {t("Type an address or choose from saved targets.")}
                      </p>
                    </div>
                  </div>
                </div>
              </section>

              <ModulePanel
                state={moduleState}
                onToggleEnabled={toggleModuleEnabled}
                onToggleExpanded={toggleModuleExpanded}
                onFilterChange={updateModuleFilter}
                onRun={runProbe}
                canRun={canMutate && scanPending === null}
                runPending={scanPending === "dashboard"}
                t={t}
              />

              <ScanConsole
                scan={consoleScan}
                loading={consoleLoading}
                onClear={() => {
                  setConsoleScanId(null);
                  setConsoleScan(null);
                }}
                t={t}
              />

              <section className="panel">
                <div className="panel__header">
                  <h2>{t("Recent probe jobs")}</h2>
                </div>
                <div className="table-wrap">
                  <ScanTable
                    scans={scans.slice(0, 10)}
                    emptyTitle="No probe jobs"
                    emptyMessage="Select modules and run a discovery probe against a host."
                    canMutate={canMutate}
                    canExport={canExport}
                    cancellingIds={cancellingIds}
                    exportingIds={exportingIds}
                    focusedScanId={consoleScanId}
                    onCancel={onCancelScan}
                    onExport={onExportScan}
                    onOpenConsole={(scan) => setConsoleScanId(scan.id)}
                    t={t}
                  />
                </div>
              </section>
            </>
          )}

          {nav === "targets" && (
            <>
              <header className="page-header">
                <h1>{t("Targets")}</h1>
                <p>
                  {t(
                    "Add IP addresses, CIDR ranges, or hostnames. Select hosts with checkboxes, then queue a scan or remove them from the working set.",
                  )}
                </p>
              </header>

              {flash && (
                <div className="flash flash--ok" role="status">
                  <div>
                    <strong>{t("Success")}</strong>
                    <p>{flash}</p>
                  </div>
                </div>
              )}

              {canMutate ? (
                <section className="panel">
                  <div className="panel__header">
                    <h2>{t("Add target")}</h2>
                  </div>
                  <form className="panel__body" onSubmit={onAdd} aria-busy={addPending}>
                  <div className="form-row">
                    <label htmlFor="host-input">{t("IP / hostname")}</label>
                    <div>
                      <input
                        id="host-input"
                        className={`input ${draftError ? "is-invalid" : ""}`}
                        value={draft}
                        onChange={(e) => {
                          setDraft(e.target.value);
                          setDraftError(null);
                          setFlash(null);
                        }}
                        placeholder="10.0.0.15 or app.example.lab or 10.0.0.0/24"
                        autoComplete="off"
                        spellCheck={false}
                      />
                      {draftError ? (
                        <p className="field-error">{draftError}</p>
                      ) : (
                        <p className="field-help">
                          {t("One target per submit. CIDR is stored as a range entry.")}
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="form-row">
                    <label htmlFor="target-comment">{t("Comment (optional)")}</label>
                    <div>
                      <textarea
                        id="target-comment"
                        className="input target-comment-input"
                        value={draftComment}
                        onChange={(e) => setDraftComment(e.target.value)}
                        placeholder="e.g. Production API, Warsaw office router, owner: Network Team"
                        maxLength={280}
                        rows={3}
                      />
                      <p className="field-help">
                        {t("Optional note describing the host, owner, environment, or purpose.")}{" "}
                        {draftComment.length}/280
                      </p>
                    </div>
                  </div>
                  <div className="actions">
                    <button type="submit" className="btn btn--primary" disabled={addPending}>
                      {addPending ? t("Adding…") : t("Add target")}
                    </button>
                  </div>
                  </form>
                </section>
              ) : (
                <div className="flash" role="note">
                  <div>
                    <strong>{t("Read-only access")}</strong>
                    <p>{t("Your role can view targets and scans but cannot change them.")}</p>
                  </div>
                </div>
              )}

              <section className="panel">
                <div className="table-toolbar" aria-busy={removePending || scanPending === "targets"}>
                  {canMutate && (
                    <div className="actions">
                    <button
                      type="button"
                      className="btn btn--primary"
                      disabled={selected.size === 0 || scanPending !== null || removePending}
                      onClick={queueSelected}
                      aria-busy={scanPending === "targets"}
                    >
                      {scanPending === "targets" ? t("Queueing…") : t("Scan selected")} (
                      {selected.size})
                    </button>
                    <button
                      type="button"
                      className="btn btn--danger"
                      disabled={selected.size === 0 || removePending || scanPending !== null}
                      onClick={removeSelected}
                      aria-busy={removePending}
                    >
                      {removePending ? t("Removing…") : t("Remove")}
                    </button>
                    <button
                      type="button"
                      className="btn btn--normal"
                      disabled={selected.size === 0}
                      onClick={() => setSelected(new Set())}
                    >
                      {t("Clear selection")}
                    </button>
                    </div>
                  )}
                  <div className="table-toolbar__count">
                    {canMutate ? `${selected.size} ${t("selected")} · ` : ""}
                    {targets.length} {t("total")}
                  </div>
                </div>

                <div className="table-wrap">
                  {targets.length === 0 ? (
                    <div className="empty">
                      <strong>{t("No targets")}</strong>
                      {t("Add an IP address or hostname to start building the scan set.")}
                    </div>
                  ) : (
                    <table className="hosts">
                      <caption className="sr-only">Target hosts for discovery</caption>
                      <thead>
                        <tr>
                          {canMutate && (
                            <th className="col-check" scope="col">
                              <input
                                type="checkbox"
                                checked={allSelected}
                                ref={(el) => {
                                  if (el) el.indeterminate = someSelected;
                                }}
                                onChange={toggleAll}
                                aria-label={t("Select all hosts")}
                              />
                            </th>
                          )}
                          <th scope="col">{t("Host / IP")}</th>
                          <th scope="col">{t("Comment")}</th>
                          <th scope="col">{t("Type")}</th>
                          <th scope="col">{t("Added")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {targets.map((target) => {
                          const isSelected = selected.has(target.id);
                          return (
                            <tr
                              key={target.id}
                              className={isSelected ? "is-selected" : undefined}
                            >
                              {canMutate && (
                                <td className="col-check">
                                  <input
                                    type="checkbox"
                                    checked={isSelected}
                                    onChange={() => toggleOne(target.id)}
                                    aria-label={`${t("Select")} ${target.address}`}
                                  />
                                </td>
                              )}
                              <td className="mono">{target.address}</td>
                              <td className="target-comment">
                                {target.comment || <span className="target-comment--empty">—</span>}
                              </td>
                              <td>{target.type}</td>
                              <td>{new Date(target.created_at).toLocaleString()}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  )}
                </div>
              </section>

              <ScanConsole
                scan={consoleScan}
                loading={consoleLoading}
                onClear={() => {
                  setConsoleScanId(null);
                  setConsoleScan(null);
                }}
                t={t}
              />
            </>
          )}

          {nav === "scans" && (
            <>
              <header className="page-header">
                <h1>{t("Scans")}</h1>
                <p>{t("Queued discovery jobs from the dashboard and target list.")}</p>
              </header>
              <ScanConsole
                scan={consoleScan}
                loading={consoleLoading}
                onClear={() => {
                  setConsoleScanId(null);
                  setConsoleScan(null);
                }}
                t={t}
              />
              <div className="panel">
                <div className="table-wrap" aria-busy={dataLoading}>
                  <ScanTable
                    scans={scans}
                    emptyTitle="No scan runs yet"
                    emptyMessage="Use Dashboard modules to probe a host."
                    canMutate={canMutate}
                    canExport={canExport}
                    cancellingIds={cancellingIds}
                    exportingIds={exportingIds}
                    focusedScanId={consoleScanId}
                    onCancel={onCancelScan}
                    onExport={onExportScan}
                    onOpenConsole={(scan) => setConsoleScanId(scan.id)}
                    t={t}
                  />
                </div>
              </div>
            </>
          )}
        </main>
      </div>

      <AppFooter
        highContrast={highContrast}
        onToggleContrast={toggleHighContrast}
        language={language}
        onLanguageChange={setLanguage}
        t={t}
      />
      <div id="a11y-help" className="sr-only" tabIndex={-1}>
        Keyboard: Tab moves focus, Enter activates buttons, Escape dismisses toasts when focused.
        Navigation uses aria-current for the active page. Status messages use live regions.
        Enable High contrast from the header or footer for stronger colors and borders.
      </div>
    </div>
  );
}
