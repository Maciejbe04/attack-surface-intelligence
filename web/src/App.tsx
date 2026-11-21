import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  ACTIVE_SCAN_STATUSES,
  apiErrorMessage,
  cancelScan,
  createScan,
  createTarget,
  deleteTarget,
  getScan,
  importTargetsFile,
  listGroups,
  listScans,
  listTargets,
  resumeScan,
  Scan,
  ScanDetail,
  ScanModule,
  ScanStatus,
  Target,
  TargetGroup,
  TargetType,
  createGroup,
  scanGroup,
  updateGroupMembers,
} from "./api/scans";
import { apiFetch, AuthUser } from "./auth";
import { HostSearch } from "./HostSearch";
import { newUuid } from "./uuid";
import { AppFooter } from "./AppFooter";
import { FindingsPanel, LifecycleKpis } from "./FindingsPanel";
import { Language, Translate, useLanguage } from "./i18n";
import { LanguageSelect } from "./LanguageSelect";
import { Logo } from "./Logo";
import { GroupsPanel } from "./GroupsPanel";
import { ModulePanel } from "./ModulePanel";
import {
  createInitialModuleState,
  ModuleRegistryState,
  summarizeFilters,
} from "./modules";
import { ScanConsole } from "./ScanConsole";
import { SystemLockButton, SystemPanel } from "./SystemPanel";
import { useHighContrast } from "./useHighContrast";
import { APP_NAME, APP_VERSION } from "./version";

function formatEta(seconds: number | null | undefined): string {
  if (seconds == null || seconds <= 0) return "";
  if (seconds < 60) return `~${seconds}s`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `~${minutes}m`;
  return `~${Math.round(minutes / 60)}h`;
}

type NavId = "dashboard" | "targets" | "groups" | "scans" | "system";

/** Select value meaning "create a new group with the typed name". */
const NEW_GROUP = "__new__";
/** Filter value for hosts that are not in any group. */
const NO_GROUP = "__none__";

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
  cancellingIds,
  focusedScanId,
  resumingIds,
  onCancel,
  onResume,
  onOpenConsole,
  t,
}: {
  scans: Scan[];
  emptyTitle: string;
  emptyMessage: string;
  canMutate: boolean;
  cancellingIds: Set<number>;
  focusedScanId: number | null;
  resumingIds: Set<number>;
  onCancel: (scan: Scan) => void;
  onResume: (scan: Scan) => void;
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
          const resuming = resumingIds.has(scan.id);
          const focused = focusedScanId === scan.id;
          const eta = formatEta(scan.eta_seconds);
          return (
            <tr key={scan.id} className={focused ? "is-selected" : undefined}>
              <td className="mono">#{scan.id}</td>
              <td className="scan-targets">
                {scan.group_name && (
                  <span className="scan-origin">
                    <span className="group-chip">{scan.group_name}</span>
                    {scan.scheduled && <span className="scan-origin__schedule">{t("scheduled")}</span>}
                  </span>
                )}
                {scan.targets.length > 0 ? scan.targets.join(", ") : "—"}
              </td>
              <td className="scan-modules">
                <div
                  className="scan-modules__list"
                  title={scan.modules
                    .map((module) => `${module.id} (${summarizeFilters(module.filters)})`)
                    .join("; ")}
                >
                  {scan.modules.length > 0
                    ? scan.modules.map((module) => module.id).join(", ")
                    : "—"}
                </div>
              </td>
              <td className="scan-status-cell">
                <div className="scan-status">
                  <span className={`status-badge status-badge--${scan.status}`}>
                    {t(STATUS_LABELS[scan.status])}
                  </span>
                  {scan.resume_available && (
                    <span className="status-badge status-badge--partial">{t("Paused")}</span>
                  )}
                </div>
                {scan.error && <span className="scan-error">{scan.error}</span>}
              </td>
              <td>
                <div className="scan-progress">
                  <progress value={scan.progress} max={100} aria-label={t("Scan progress")} />
                  <span>
                    {scan.progress}%
                    {eta ? ` · ${eta}` : ""}
                  </span>
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
                {scan.resume_available && canMutate && (
                  <button
                    type="button"
                    className="btn btn--normal"
                    onClick={() => onResume(scan)}
                    disabled={resuming}
                    aria-busy={resuming}
                  >
                    {resuming ? t("Resuming…") : t("Resume")}
                  </button>
                )}
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
  const [probeMode, setProbeMode] = useState<"group" | "host">("group");
  const [probeTarget, setProbeTarget] = useState<Target | null>(null);
  const [probeGroupId, setProbeGroupId] = useState("");
  const [groups, setGroups] = useState<TargetGroup[]>([]);
  const [groupsLoading, setGroupsLoading] = useState(false);
  const [groupsRefreshKey, setGroupsRefreshKey] = useState(0);
  const [targetQuery, setTargetQuery] = useState("");
  const [targetGroupFilter, setTargetGroupFilter] = useState("");
  const [bulkGroupChoice, setBulkGroupChoice] = useState("");
  const [bulkGroupName, setBulkGroupName] = useState("");
  const [groupPending, setGroupPending] = useState(false);
  const [assigningTargetId, setAssigningTargetId] = useState<number | null>(null);
  const [importGroupChoice, setImportGroupChoice] = useState("");
  const [importGroupName, setImportGroupName] = useState("");
  const [addGroupChoice, setAddGroupChoice] = useState("");
  const [addGroupName, setAddGroupName] = useState("");
  const [addPending, setAddPending] = useState(false);
  const [importPending, setImportPending] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importStartScan, setImportStartScan] = useState(true);
  const [removePending, setRemovePending] = useState(false);
  const [scanPending, setScanPending] = useState<"dashboard" | "targets" | null>(null);
  const [cancellingIds, setCancellingIds] = useState<Set<number>>(new Set());
  const [resumingIds, setResumingIds] = useState<Set<number>>(new Set());
  const [consoleScanId, setConsoleScanId] = useState<number | null>(null);
  const [consoleScan, setConsoleScan] = useState<ScanDetail | null>(null);
  const [consoleLoading, setConsoleLoading] = useState(false);
  const [consoleReloadKey, setConsoleReloadKey] = useState(0);
  const [scanWindowSeconds, setScanWindowSeconds] = useState<number | "">("");
  const [moduleState, setModuleState] = useState<ModuleRegistryState>(() =>
    createInitialModuleState(),
  );
  const canMutate = user?.role === "admin" || user?.role === "operator";
  const canExport =
    user?.role === "admin" || user?.role === "operator" || user?.role === "analyst";

  function pushToast(kind: Toast["kind"], title: string, message: string) {
    const id = newUuid();
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
      setProbeTarget(null);
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
        // Fast while something runs; slow otherwise so scans started by a
        // group schedule (server-side, no user action) still show up.
        const active = nextScans.some((scan) => ACTIVE_SCAN_STATUSES.has(scan.status));
        timer = window.setTimeout(poll, active ? 2000 : 15000);
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
    // nav: refetch immediately when the user switches pages.
  }, [user?.id, language, scanRefreshKey, nav]);

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
      if (disposed || document.hidden) return;
      controller?.abort();
      const request = new AbortController();
      controller = request;
      setConsoleLoading(true);
      try {
        const detail = await getScan(consoleScanId, request.signal);
        if (disposed || controller !== request) return;
        setConsoleScan({
          ...detail,
          events: detail.events ?? [],
          batches: detail.batches ?? [],
        });

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
                  defectdojo_export_status: detail.defectdojo_export_status,
                  defectdojo_export_detail: detail.defectdojo_export_detail,
                  started_at: detail.started_at,
                  finished_at: detail.finished_at,
                }
              : item,
          ),
        );
        const exportInFlight =
          detail.defectdojo_export_status === "pending" ||
          detail.defectdojo_export_status === "sending";
        if (ACTIVE_SCAN_STATUSES.has(detail.status) || exportInFlight) {
          timer = window.setTimeout(pollDetail, 1500);
        }
      } catch (error) {
        if (disposed || controller !== request || isAbortError(error)) return;
        pushToast(
          "error",
          t("Console unavailable"),
          apiErrorMessage(error, t("Could not load scan activity.")),
        );
        timer = window.setTimeout(pollDetail, 4000);
      } finally {
        if (controller === request) controller = null;
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
  }, [user?.id, language, consoleScanId, scanRefreshKey, consoleReloadKey]);

  function openScanConsole(scanId: number) {
    setConsoleScanId(scanId);
    setConsoleReloadKey((value) => value + 1);
    window.requestAnimationFrame(() => {
      document.getElementById("scan-activity-console")?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    });
  }

  useEffect(() => {
    if (!user) {
      setGroups([]);
      return;
    }
    const controller = new AbortController();
    setGroupsLoading(true);
    listGroups(controller.signal)
      .then(setGroups)
      .catch((error: unknown) => {
        if (!isAbortError(error)) {
          pushToast("error", t("Groups unavailable"), apiErrorMessage(error, t("Could not load groups.")));
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setGroupsLoading(false);
      });
    return () => controller.abort();
  }, [user?.id, language, groupsRefreshKey]);

  function refreshGroups() {
    setGroupsRefreshKey((value) => value + 1);
  }

  async function refreshTargets() {
    try {
      setTargets(await listTargets());
    } catch (error) {
      pushToast("error", t("Targets unavailable"), apiErrorMessage(error, t("Could not load targets.")));
    }
  }

  // Filter on the loaded list so selection, bulk actions and counts stay in sync.
  const visibleTargets = useMemo(() => {
    const query = targetQuery.trim().toLowerCase();
    const ungroupedOnly = targetGroupFilter === NO_GROUP;
    const groupId =
      targetGroupFilter && targetGroupFilter !== NO_GROUP ? Number(targetGroupFilter) : null;
    return targets.filter((target) => {
      if (ungroupedOnly && (target.groups?.length ?? 0) > 0) return false;
      if (groupId !== null && !target.groups.some((group) => group.id === groupId)) return false;
      if (!query) return true;
      return (
        target.address.toLowerCase().includes(query) ||
        target.comment.toLowerCase().includes(query) ||
        target.groups.some((group) => group.name.toLowerCase().includes(query))
      );
    });
  }, [targets, targetQuery, targetGroupFilter]);

  const visibleSelectedCount = visibleTargets.filter((target) => selected.has(target.id)).length;
  const allSelected = visibleTargets.length > 0 && visibleSelectedCount === visibleTargets.length;
  const someSelected = visibleSelectedCount > 0 && !allSelected;
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
    // Acts on the filtered rows only, so "filter, select all, scan" is a bulk scan.
    setSelected((prev) => {
      const next = new Set(prev);
      for (const target of visibleTargets) {
        if (allSelected) next.delete(target.id);
        else next.add(target.id);
      }
      return next;
    });
  }

  function showGroupHosts(groupId: number) {
    setTargetGroupFilter(String(groupId));
    setTargetQuery("");
    setNav("targets");
  }

  async function resolveGroupChoice(choice: string, newName: string): Promise<TargetGroup | null> {
    if (choice === NEW_GROUP) return createGroup({ name: newName.trim() });
    return groups.find((group) => String(group.id) === choice) ?? null;
  }

  async function changeSelectedMembership(action: "add" | "remove") {
    if (!canMutate || groupPending || selected.size === 0) return;
    const choice = action === "remove" ? targetGroupFilter : bulkGroupChoice;
    if (!choice || choice === NO_GROUP || (choice === NEW_GROUP && !bulkGroupName.trim())) return;
    setGroupPending(true);
    try {
      const group = await resolveGroupChoice(choice, bulkGroupName);
      if (!group) return;
      const result = await updateGroupMembers(group.id, action, [...selected]);
      await refreshTargets();
      refreshGroups();
      if (choice === NEW_GROUP) {
        setBulkGroupChoice(String(group.id));
        setBulkGroupName("");
      }
      if (action === "remove") setSelected(new Set());
      setFlash(
        action === "add"
          ? `${t("Added to group")} ${result.name}: ${result.changed_count}`
          : `${t("Removed from group")} ${result.name}: ${result.changed_count}`,
      );
    } catch (error) {
      pushToast("error", t("Group not updated"), apiErrorMessage(error, t("Could not update the group.")));
      refreshGroups();
    } finally {
      setGroupPending(false);
    }
  }

  async function assignTargetGroup(target: Target, choice: string) {
    if (!canMutate || !choice || assigningTargetId !== null) return;
    let newName = "";
    if (choice === NEW_GROUP) {
      newName = window.prompt(t("New group name"))?.trim() ?? "";
      if (!newName) return;
    }
    setAssigningTargetId(target.id);
    try {
      const group = await resolveGroupChoice(choice, newName);
      if (!group) return;
      await updateGroupMembers(group.id, "add", [target.id]);
      await refreshTargets();
      refreshGroups();
      setFlash(`${t("Added to group")} ${group.name}: ${target.address}`);
    } catch (error) {
      pushToast("error", t("Group not updated"), apiErrorMessage(error, t("Could not update the group.")));
      refreshGroups();
    } finally {
      setAssigningTargetId(null);
    }
  }

  async function removeTargetFromGroup(target: Target, groupId: number) {
    if (!canMutate || assigningTargetId !== null) return;
    setAssigningTargetId(target.id);
    try {
      const group = groups.find((item) => item.id === groupId);
      await updateGroupMembers(groupId, "remove", [target.id]);
      await refreshTargets();
      refreshGroups();
      setFlash(
        `${t("Removed from group")} ${group?.name ?? groupId}: ${target.address}`,
      );
    } catch (error) {
      pushToast("error", t("Group not updated"), apiErrorMessage(error, t("Could not update the group.")));
      refreshGroups();
    } finally {
      setAssigningTargetId(null);
    }
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
    if (addGroupChoice === NEW_GROUP && !addGroupName.trim()) {
      setDraftError(t("Type a name for the new group."));
      return;
    }

    setAddPending(true);
    try {
      let target = await createTarget({
        address: value,
        type: detectType(value),
        comment: draftComment.trim(),
      });
      let groupLabel = "";
      if (addGroupChoice) {
        const group = await resolveGroupChoice(addGroupChoice, addGroupName);
        if (group) {
          await updateGroupMembers(group.id, "add", [target.id]);
          target = { ...target, groups: [{ id: group.id, name: group.name }] };
          groupLabel = group.name;
          refreshGroups();
          if (addGroupChoice === NEW_GROUP) {
            setAddGroupChoice(String(group.id));
            setAddGroupName("");
          }
        }
      }
      setTargets((prev) =>
        [...prev.filter((item) => item.id !== target.id), target].sort((a, b) =>
          a.address.localeCompare(b.address),
        ),
      );
      setDraft("");
      setDraftComment("");
      setDraftError(null);
      setFlash(
        groupLabel
          ? `${t("Added")} ${target.address} · ${t("Group")}: ${groupLabel}`
          : `${t("Added")} ${target.address}`,
      );
      if (!probeTarget) setProbeTarget(target);
    } catch (error) {
      const message = apiErrorMessage(error, t("Could not add target."));
      setDraftError(message);
      pushToast("error", t("Target not added"), message);
    } finally {
      setAddPending(false);
    }
  }

  async function onImportFile(event: FormEvent) {
    event.preventDefault();
    if (!canMutate || importPending || !importFile) return;
    const modules = selectedModules();
    if (importStartScan && modules.length === 0) {
      pushToast("error", t("No modules"), t("Select at least one discovery module."));
      return;
    }
    if (importGroupChoice === NEW_GROUP && !importGroupName.trim()) {
      pushToast("error", t("Group name required"), t("Type a name for the new group."));
      return;
    }
    setImportPending(true);
    try {
      const result = await importTargetsFile(importFile, {
        startScan: importStartScan,
        modules: importStartScan ? modules : undefined,
        clientRequestId: newUuid(),
        groupId:
          importGroupChoice && importGroupChoice !== NEW_GROUP ? Number(importGroupChoice) : undefined,
        groupName: importGroupChoice === NEW_GROUP ? importGroupName.trim() : undefined,
      });
      refreshGroups();
      setImportGroupName("");
      const groupNote =
        result.groups.length > 0
          ? ` · ${t("Groups")}: ${result.groups.map((group) => group.name).join(", ")}`
          : "";
      const refreshed = await listTargets();
      setTargets(refreshed);
      setImportFile(null);
      const fileInput = document.getElementById("targets-import-file") as HTMLInputElement | null;
      if (fileInput) fileInput.value = "";
      setFlash(
        `${t("Imported targets")}: ${result.total_count} ` +
          `(${t("new")}: ${result.created_count}, ${t("existing")}: ${result.existing_count})` +
          (result.scan ? ` · ${t("Scan")} #${result.scan.id}` : "") +
          groupNote,
      );
      if (result.scan) {
        setScans((prev) => [result.scan!, ...prev.filter((item) => item.id !== result.scan!.id)]);
        setConsoleScan({
          ...result.scan,
          events: result.scan.events ?? [],
          batches: result.scan.batches ?? [],
        });
        openScanConsole(result.scan.id);
        setScanRefreshKey((value) => value + 1);
        setNav("scans");
      }
      if (result.parse_errors.length > 0) {
        pushToast(
          "error",
          t("Some rows were skipped"),
          result.parse_errors.slice(0, 3).join(" · "),
        );
      } else {
        pushToast(
          "ok",
          t("Import finished"),
          result.scan
            ? t("Hosts loaded and scan queued automatically.")
            : t("Hosts loaded into the target list."),
        );
      }
    } catch (error) {
      pushToast(
        "error",
        t("Import failed"),
        apiErrorMessage(error, t("Could not import the host file.")),
      );
    } finally {
      setImportPending(false);
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
    if (removedTargets.some((target) => target.id === probeTarget?.id)) setProbeTarget(null);
    if (removedIds.size > 0) refreshGroups();
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
      const windowSeconds =
        source === "dashboard" && scanWindowSeconds !== ""
          ? Number(scanWindowSeconds)
          : undefined;
      const scan = await createScan({
        target_ids: targetIds,
        modules,
        client_request_id: newUuid(),
        ...(windowSeconds != null ? { window_seconds: windowSeconds } : {}),
      });
      setScans((prev) => [scan, ...prev.filter((item) => item.id !== scan.id)]);
      setConsoleScan({
        ...scan,
        events: scan.events ?? [],
        batches: scan.batches ?? [],
      });
      openScanConsole(scan.id);
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

  async function runProbe() {
    if (!canMutate || scanPending !== null) return;
    const modules = selectedModules();
    if (modules.length === 0) {
      pushToast("error", t("No modules"), t("Select at least one discovery module."));
      return;
    }
    if (probeMode === "host") {
      if (!probeTarget) {
        pushToast("error", t("Host required"), t("Choose a saved host to scan."));
        return;
      }
      await queueScan([probeTarget.id], "dashboard");
      return;
    }
    const group = groups.find((item) => String(item.id) === probeGroupId);
    if (!group) {
      pushToast("error", t("Group required"), t("Choose a target group to scan."));
      return;
    }
    if (group.target_count === 0) {
      pushToast("error", t("Empty group"), t("The selected group has no hosts yet."));
      return;
    }
    setScanPending("dashboard");
    try {
      const windowSeconds =
        scanWindowSeconds === "" ? null : Number(scanWindowSeconds);
      const scan = await scanGroup(
        group.id,
        modules,
        newUuid(),
        undefined,
        windowSeconds,
      );
      setScans((prev) => [scan, ...prev.filter((item) => item.id !== scan.id)]);
      setConsoleScan({
        ...scan,
        events: scan.events ?? [],
        batches: scan.batches ?? [],
      });
      openScanConsole(scan.id);
      setScanRefreshKey((value) => value + 1);
      refreshGroups();
      pushToast(
        "ok",
        t("Scan queued"),
        `${t("Group")}: ${group.name} · ${group.target_count} ${t("hosts")} · ${t("Modules")}: ${modules.length}`,
      );
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

  function onGroupScanQueued(scan: ScanDetail) {
    setScans((prev) => [scan, ...prev.filter((item) => item.id !== scan.id)]);
    setConsoleScan({ ...scan, events: scan.events ?? [], batches: scan.batches ?? [] });
    openScanConsole(scan.id);
    setScanRefreshKey((value) => value + 1);
    setNav("scans");
  }

  async function onResumeScan(scan: Scan) {
    if (!canMutate || resumingIds.has(scan.id) || !scan.resume_available) return;
    setResumingIds((prev) => new Set(prev).add(scan.id));
    try {
      const updated = await resumeScan(scan.id);
      setScans((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
      if (consoleScanId === updated.id) {
        setConsoleScan({
          ...updated,
          events: updated.events ?? [],
          batches: updated.batches ?? [],
        });
        setConsoleReloadKey((value) => value + 1);
      }
      setScanRefreshKey((value) => value + 1);
      pushToast("ok", t("Scan resumed"), `#${updated.id}`);
    } catch (error) {
      pushToast(
        "error",
        t("Resume failed"),
        apiErrorMessage(error, t("Could not resume scan.")),
      );
    } finally {
      setResumingIds((prev) => {
        const next = new Set(prev);
        next.delete(scan.id);
        return next;
      });
    }
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
        <SystemLockButton
          className="topnav__system"
          onClick={() => setNav("system")}
          t={t}
        />
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
            className={`sidenav__item ${nav === "groups" ? "is-active" : ""}`}
            aria-current={nav === "groups" ? "page" : undefined}
            onClick={() => setNav("groups")}
          >
            {t("Groups")}
          </button>
          <button
            type="button"
            className={`sidenav__item ${nav === "scans" ? "is-active" : ""}`}
            aria-current={nav === "scans" ? "page" : undefined}
            onClick={() => setNav("scans")}
          >
            {t("Scans")}
          </button>
          <button
            type="button"
            className={`sidenav__item ${nav === "system" ? "is-active" : ""}`}
            aria-current={nav === "system" ? "page" : undefined}
            onClick={() => setNav("system")}
          >
            {t("System")}
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
                    "Pick a target group or host and run discovery modules. SurfaceX probes only — no login, brute force, or exploitation.",
                  )}
                </p>
              </header>

              <section className="panel">
                <div className="panel__header panel__header--split">
                  <h2>{probeMode === "group" ? t("Target group") : t("Target host")}</h2>
                  <div className="mode-toggle" role="group" aria-label={t("Probe target mode")}>
                    <button
                      type="button"
                      className={`mode-toggle__btn ${probeMode === "group" ? "is-active" : ""}`}
                      aria-pressed={probeMode === "group"}
                      onClick={() => setProbeMode("group")}
                    >
                      {t("Target group")}
                    </button>
                    <button
                      type="button"
                      className={`mode-toggle__btn ${probeMode === "host" ? "is-active" : ""}`}
                      aria-pressed={probeMode === "host"}
                      onClick={() => setProbeMode("host")}
                    >
                      {t("Target host")}
                    </button>
                  </div>
                </div>
                <div className="panel__body">
                  {probeMode === "group" ? (
                    <div className="form-row">
                      <label htmlFor="probe-group">{t("Group")}</label>
                      <div>
                        <select
                          id="probe-group"
                          className="input input--select"
                          value={probeGroupId}
                          onChange={(e) => setProbeGroupId(e.target.value)}
                          disabled={groupsLoading}
                        >
                          <option value="">{t("Choose group…")}</option>
                          {groups.map((group) => (
                            <option key={group.id} value={group.id}>
                              {group.name} ({group.target_count} {t("hosts")})
                            </option>
                          ))}
                        </select>
                        <p className="field-help">
                          {(() => {
                            const selected = groups.find((group) => String(group.id) === probeGroupId);
                            return selected
                              ? `${t("Selected")}: ${selected.name} · ${selected.target_count} ${t("hosts")}`
                              : t("Choose a target group to scan all of its hosts.");
                          })()}
                        </p>
                      </div>
                    </div>
                  ) : (
                    <div className="form-row">
                      <label htmlFor="probe-host">{t("Host / IP")}</label>
                      <div>
                        <HostSearch
                          id="probe-host"
                          selected={probeTarget}
                          onSelect={setProbeTarget}
                          t={t}
                        />
                        <p className="field-help">
                          {probeTarget
                            ? `${t("Selected")}: ${probeTarget.address}`
                            : t("Type an address or choose from saved targets.")}
                        </p>
                      </div>
                    </div>
                  )}
                  <div className="form-row">
                    <label htmlFor="scan-window">{t("Scan window")}</label>
                    <div>
                      <select
                        id="scan-window"
                        className="input input--select"
                        value={scanWindowSeconds === "" ? "" : String(scanWindowSeconds)}
                        onChange={(e) =>
                          setScanWindowSeconds(e.target.value ? Number(e.target.value) : "")
                        }
                      >
                        <option value="">{t("Off (no deadline)")}</option>
                        <option value="1800">30m</option>
                        <option value="3600">1h</option>
                        <option value="7200">2h</option>
                      </select>
                      <p className="field-help">
                        {t("Optional deadline; unfinished batches pause and can be resumed.")}
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
                onRun={() => void runProbe()}
                canRun={
                  canMutate &&
                  scanPending === null &&
                  (probeMode === "group" ? Boolean(probeGroupId) : Boolean(probeTarget))
                }
                runPending={scanPending === "dashboard"}
                t={t}
              />

              <LifecycleKpis scans={scans} t={t} />

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
                    cancellingIds={cancellingIds}
                    focusedScanId={consoleScanId}
                    resumingIds={resumingIds}
                    onCancel={onCancelScan}
                    onResume={onResumeScan}
                    onOpenConsole={(scan) => openScanConsole(scan.id)}
                    t={t}
                  />
                </div>
              </section>

              <FindingsPanel
                scan={consoleScan}
                canMutate={canMutate}
                canExport={canExport}
                onScanUpdated={(updated) => {
                  setScans((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
                  setConsoleScan({
                    ...updated,
                    events: (updated as ScanDetail).events ?? consoleScan?.events ?? [],
                    batches: (updated as ScanDetail).batches ?? consoleScan?.batches ?? [],
                  });
                  setScanRefreshKey((value) => value + 1);
                }}
                pushToast={pushToast}
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
                <>
                <section className="panel">
                  <div className="panel__header">
                    <h2>{t("Import hosts file")}</h2>
                  </div>
                  <form
                    className="panel__body"
                    onSubmit={onImportFile}
                    aria-busy={importPending}
                  >
                    <div className="form-row">
                      <label htmlFor="targets-import-file">{t("Host list file")}</label>
                      <div>
                        <input
                          id="targets-import-file"
                          className="input"
                          type="file"
                          accept=".txt,.csv,.json,text/csv,text/plain,application/json"
                          onChange={(e) => {
                            const file = e.target.files?.[0] ?? null;
                            if (file && file.size === 0 && !file.name.includes(".")) {
                              setImportFile(null);
                              pushToast(
                                "error",
                                t("Import failed"),
                                t("Pick a .txt, .csv, or .json file — not a folder."),
                              );
                              e.target.value = "";
                              return;
                            }
                            setImportFile(file);
                          }}
                        />
                        {importFile && (
                          <p className="field-help mono">
                            {t("Selected")}: {importFile.name} ({importFile.size} B)
                          </p>
                        )}
                        <p className="field-help">
                          {t(
                            "TXT: one host per line. CSV/JSON: value/address column. Up to 10 000 hosts. Uses modules selected on the Dashboard.",
                          )}
                        </p>
                      </div>
                    </div>
                    <div className="form-row">
                      <label htmlFor="targets-import-group">{t("Add to group")}</label>
                      <div>
                        <select
                          id="targets-import-group"
                          className="input input--select"
                          value={importGroupChoice}
                          onChange={(e) => setImportGroupChoice(e.target.value)}
                        >
                          <option value="">{t("No group")}</option>
                          {groups.map((group) => (
                            <option key={group.id} value={group.id}>
                              {group.name} ({group.target_count})
                            </option>
                          ))}
                          <option value={NEW_GROUP}>{t("New group…")}</option>
                        </select>
                        {importGroupChoice === NEW_GROUP && (
                          <input
                            id="targets-import-group-name"
                            className="input group-name-input"
                            value={importGroupName}
                            onChange={(e) => setImportGroupName(e.target.value)}
                            placeholder={t("New group name")}
                            aria-label={t("New group name")}
                            maxLength={100}
                          />
                        )}
                        <p className="field-help">
                          {t(
                            "Every host in the file joins this group. CSV files can also set groups per row in a group column (several names separated by ;).",
                          )}
                        </p>
                      </div>
                    </div>
                    <div className="form-row">
                      <label htmlFor="targets-import-autoscan">
                        {t("Start scan automatically")}
                      </label>
                      <div>
                        <label className="filter-row filter-row--bool" htmlFor="targets-import-autoscan">
                          <input
                            id="targets-import-autoscan"
                            type="checkbox"
                            checked={importStartScan}
                            onChange={(e) => setImportStartScan(e.target.checked)}
                          />
                          <span className="field-help">
                            {t(
                              "After import, queue discovery for every loaded host and send results to DefectDojo when finished.",
                            )}
                          </span>
                        </label>
                      </div>
                    </div>
                    <div className="actions">
                      <button
                        type="submit"
                        className="btn btn--primary"
                        disabled={!importFile || importPending}
                        aria-busy={importPending}
                      >
                        {importPending
                          ? t("Importing…")
                          : importStartScan
                            ? t("Import and scan")
                            : t("Import hosts")}
                      </button>
                    </div>
                  </form>
                </section>

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
                  <div className="form-row">
                    <label htmlFor="add-target-group">{t("Group")}</label>
                    <div>
                      <select
                        id="add-target-group"
                        className="input input--select"
                        value={addGroupChoice}
                        onChange={(e) => setAddGroupChoice(e.target.value)}
                      >
                        <option value="">{t("No group")}</option>
                        {groups.map((group) => (
                          <option key={group.id} value={group.id}>
                            {group.name} ({group.target_count})
                          </option>
                        ))}
                        <option value={NEW_GROUP}>{t("New group…")}</option>
                      </select>
                      {addGroupChoice === NEW_GROUP && (
                        <input
                          id="add-target-group-name"
                          className="input group-name-input"
                          value={addGroupName}
                          onChange={(e) => setAddGroupName(e.target.value)}
                          placeholder={t("New group name")}
                          aria-label={t("New group name")}
                          maxLength={100}
                        />
                      )}
                      <p className="field-help">
                        {t("Optional. Assign the new host to a group so it can be scanned with others.")}
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
                </>
              ) : (
                <div className="flash" role="note">
                  <div>
                    <strong>{t("Read-only access")}</strong>
                    <p>{t("Your role can view targets and scans but cannot change them.")}</p>
                  </div>
                </div>
              )}

              <section className="panel">
                <div className="target-filters">
                  <div className="target-filters__field">
                    <label htmlFor="targets-filter-query">{t("Filter")}</label>
                    <input
                      id="targets-filter-query"
                      className="input"
                      type="search"
                      value={targetQuery}
                      onChange={(e) => setTargetQuery(e.target.value)}
                      placeholder={t("Address, comment, or group")}
                      autoComplete="off"
                      spellCheck={false}
                    />
                  </div>
                  <div className="target-filters__field">
                    <label htmlFor="targets-filter-group">{t("Group")}</label>
                    <select
                      id="targets-filter-group"
                      className="input input--select"
                      value={targetGroupFilter}
                      onChange={(e) => setTargetGroupFilter(e.target.value)}
                    >
                      <option value="">{t("All hosts")}</option>
                      <option value={NO_GROUP}>{t("No group (none)")}</option>
                      {groups.map((group) => (
                        <option key={group.id} value={group.id}>
                          {group.name} ({group.target_count})
                        </option>
                      ))}
                    </select>
                  </div>
                  {canMutate && (
                    <div className="target-filters__field target-filters__bulk" aria-busy={groupPending}>
                      <label htmlFor="targets-bulk-group">{t("Add selected to group")}</label>
                      <div className="target-filters__inline">
                        <select
                          id="targets-bulk-group"
                          className="input input--select"
                          value={bulkGroupChoice}
                          onChange={(e) => setBulkGroupChoice(e.target.value)}
                        >
                          <option value="">{t("Choose group…")}</option>
                          {groups.map((group) => (
                            <option key={group.id} value={group.id}>
                              {group.name}
                            </option>
                          ))}
                          <option value={NEW_GROUP}>{t("New group…")}</option>
                        </select>
                        {bulkGroupChoice === NEW_GROUP && (
                          <input
                            className="input group-name-input"
                            value={bulkGroupName}
                            onChange={(e) => setBulkGroupName(e.target.value)}
                            placeholder={t("New group name")}
                            aria-label={t("New group name")}
                            maxLength={100}
                          />
                        )}
                        <button
                          type="button"
                          className="btn btn--normal"
                          disabled={
                            selected.size === 0 ||
                            groupPending ||
                            !bulkGroupChoice ||
                            (bulkGroupChoice === NEW_GROUP && !bulkGroupName.trim())
                          }
                          onClick={() => changeSelectedMembership("add")}
                        >
                          {t("Add")} ({selected.size})
                        </button>
                        {targetGroupFilter && (
                          <button
                            type="button"
                            className="btn btn--normal"
                            disabled={selected.size === 0 || groupPending}
                            onClick={() => changeSelectedMembership("remove")}
                          >
                            {t("Remove from this group")}
                          </button>
                        )}
                      </div>
                    </div>
                  )}
                </div>
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
                    {visibleTargets.length !== targets.length
                      ? `${visibleTargets.length} / ${targets.length} ${t("shown")}`
                      : `${targets.length} ${t("total")}`}
                  </div>
                </div>

                <div className="table-wrap">
                  {targets.length === 0 ? (
                    <div className="empty">
                      <strong>{t("No targets")}</strong>
                      {t("Add an IP address or hostname to start building the scan set.")}
                    </div>
                  ) : visibleTargets.length === 0 ? (
                    <div className="empty">
                      <strong>{t("No matching hosts")}</strong>
                      {t("Change the filter or choose another group.")}
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
                          <th scope="col">{t("Group")}</th>
                          <th scope="col">{t("Type")}</th>
                          <th scope="col">{t("Added")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {visibleTargets.map((target) => {
                          const isSelected = selected.has(target.id);
                          const memberships = target.groups ?? [];
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
                              <td className="target-groups">
                                {memberships.length === 0 ? (
                                  canMutate ? (
                                    <label className="target-groups__assign">
                                      <span className="target-groups__none">{t("none")}</span>
                                      <select
                                        className="input input--select target-groups__select"
                                        value=""
                                        disabled={assigningTargetId === target.id || groupPending}
                                        aria-label={`${t("Assign group")} ${target.address}`}
                                        aria-busy={assigningTargetId === target.id}
                                        onChange={(e) => {
                                          const value = e.target.value;
                                          e.target.value = "";
                                          if (value) void assignTargetGroup(target, value);
                                        }}
                                      >
                                        <option value="">{t("Choose group…")}</option>
                                        {groups.map((group) => (
                                          <option key={group.id} value={group.id}>
                                            {group.name}
                                          </option>
                                        ))}
                                        <option value={NEW_GROUP}>{t("New group…")}</option>
                                      </select>
                                    </label>
                                  ) : (
                                    <span className="target-groups__none">{t("none")}</span>
                                  )
                                ) : (
                                  <div className="target-groups__list">
                                    {memberships.map((group) => (
                                      <span key={group.id} className="target-groups__chip-row">
                                        <button
                                          type="button"
                                          className="group-chip group-chip--button"
                                          onClick={() => setTargetGroupFilter(String(group.id))}
                                          title={t("Show only this group")}
                                        >
                                          {group.name}
                                        </button>
                                        {canMutate && (
                                          <button
                                            type="button"
                                            className="group-chip-remove"
                                            disabled={assigningTargetId === target.id || groupPending}
                                            onClick={() => void removeTargetFromGroup(target, group.id)}
                                            aria-label={`${t("Remove from group")} ${group.name}`}
                                            title={t("Remove from group")}
                                          >
                                            ×
                                          </button>
                                        )}
                                      </span>
                                    ))}
                                    {canMutate && (
                                      <select
                                        className="input input--select target-groups__select target-groups__select--add"
                                        value=""
                                        disabled={assigningTargetId === target.id || groupPending}
                                        aria-label={`${t("Add to group")} ${target.address}`}
                                        onChange={(e) => {
                                          const value = e.target.value;
                                          e.target.value = "";
                                          if (value) void assignTargetGroup(target, value);
                                        }}
                                      >
                                        <option value="">+</option>
                                        {groups
                                          .filter(
                                            (group) =>
                                              !memberships.some((member) => member.id === group.id),
                                          )
                                          .map((group) => (
                                            <option key={group.id} value={group.id}>
                                              {group.name}
                                            </option>
                                          ))}
                                        <option value={NEW_GROUP}>{t("New group…")}</option>
                                      </select>
                                    )}
                                  </div>
                                )}
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

          {nav === "groups" && (
            <GroupsPanel
              groups={groups}
              loading={groupsLoading}
              canMutate={canMutate}
              currentModules={selectedModules}
              onGroupsChanged={refreshGroups}
              onScanQueued={onGroupScanQueued}
              onShowHosts={showGroupHosts}
              pushToast={pushToast}
              t={t}
            />
          )}

          {nav === "scans" && (
            <>
              <header className="page-header">
                <h1>{t("Scans")}</h1>
                <p>{t("Queued discovery jobs from the dashboard and target list.")}</p>
              </header>
              <div className="panel">
                <div className="table-wrap" aria-busy={dataLoading}>
                  <ScanTable
                    scans={scans}
                    emptyTitle="No scan runs yet"
                    emptyMessage="Use Dashboard modules to probe a host."
                    canMutate={canMutate}
                    cancellingIds={cancellingIds}
                    focusedScanId={consoleScanId}
                    resumingIds={resumingIds}
                    onCancel={onCancelScan}
                    onResume={onResumeScan}
                    onOpenConsole={(scan) => openScanConsole(scan.id)}
                    t={t}
                  />
                </div>
              </div>

              <FindingsPanel
                scan={consoleScan}
                canMutate={canMutate}
                canExport={canExport}
                onScanUpdated={(updated) => {
                  setScans((prev) => prev.map((item) => (item.id === updated.id ? updated : item)));
                  setConsoleScan({
                    ...updated,
                    events: (updated as ScanDetail).events ?? consoleScan?.events ?? [],
                    batches: (updated as ScanDetail).batches ?? consoleScan?.batches ?? [],
                  });
                  setScanRefreshKey((value) => value + 1);
                }}
                pushToast={pushToast}
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
            </>
          )}

          {nav === "system" && (
            <SystemPanel
              active
              isAdmin={user?.role === "admin"}
              canManageAllowlist={user?.role === "admin" || user?.role === "operator"}
              t={t}
            />
          )}
        </main>
      </div>

      <AppFooter
        highContrast={highContrast}
        onToggleContrast={toggleHighContrast}
        onOpenSystem={() => setNav("system")}
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
