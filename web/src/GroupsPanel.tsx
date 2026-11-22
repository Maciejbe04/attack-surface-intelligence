import { FormEvent, useMemo, useState } from "react";
import {
  GroupSchedule,
  GroupScheduleInput,
  ScanDetail,
  ScanModule,
  ScheduleFrequency,
  TargetGroup,
  apiErrorMessage,
  createGroup,
  deleteGroup,
  deleteGroupSchedule,
  saveGroupSchedule,
  scanGroup,
  updateGroup,
} from "./api/scans";
import { Translate } from "./i18n";
import { summarizeFilters } from "./modules";
import { newUuid } from "./uuid";

const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

type ToastFn = (kind: "ok" | "error", title: string, message: string) => void;

export function describeSchedule(schedule: GroupSchedule | null, t: Translate): string {
  if (!schedule) return t("Not scheduled");
  let text: string;
  if (schedule.frequency === "hourly") {
    text = `${t("Every")} ${schedule.interval_hours} h`;
  } else if (schedule.frequency === "daily") {
    text = `${t("Daily at")} ${schedule.time_of_day} UTC`;
  } else {
    text = `${t(WEEKDAYS[schedule.weekday])} ${schedule.time_of_day} UTC`;
  }
  return schedule.enabled ? text : `${text} · ${t("paused")}`;
}

function describeModules(modules: ScanModule[]): string {
  if (modules.length === 0) return "—";
  return modules.map((module) => `${module.id} (${summarizeFilters(module.filters)})`).join("; ");
}

type Draft = GroupScheduleInput & { useCurrentModules: boolean };

function draftFor(group: TargetGroup): Draft {
  const schedule = group.schedule;
  return {
    enabled: schedule?.enabled ?? true,
    frequency: schedule?.frequency ?? "daily",
    interval_hours: schedule?.interval_hours ?? 24,
    time_of_day: schedule?.time_of_day ?? "02:00",
    weekday: schedule?.weekday ?? 0,
    modules: schedule?.modules ?? [],
    useCurrentModules: !schedule,
  };
}

export function GroupsPanel({
  groups,
  loading,
  canMutate,
  isAdmin = false,
  currentModules,
  onGroupsChanged,
  onScanQueued,
  onShowHosts,
  pushToast,
  t,
}: {
  groups: TargetGroup[];
  loading: boolean;
  canMutate: boolean;
  isAdmin?: boolean;
  /** Modules currently selected on the Dashboard; used for "Scan now" and new schedules. */
  currentModules: () => ScanModule[];
  onGroupsChanged: () => void;
  onScanQueued: (scan: ScanDetail) => void;
  onShowHosts: (groupId: number) => void;
  pushToast: ToastFn;
  t: Translate;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [createPending, setCreatePending] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [renamingId, setRenamingId] = useState<number | null>(null);
  const [renameName, setRenameName] = useState("");
  const [renameDescription, setRenameDescription] = useState("");
  const [renamePending, setRenamePending] = useState(false);
  const [groupQuery, setGroupQuery] = useState("");
  const [scheduleFilter, setScheduleFilter] = useState<
    "" | "scheduled" | "enabled" | "paused" | "none"
  >("");
  const [hostsFilter, setHostsFilter] = useState<"" | "with_hosts" | "empty">("");

  const editing = groups.find((group) => group.id === editingId) ?? null;

  const filteredGroups = useMemo(() => {
    const query = groupQuery.trim().toLowerCase();
    return groups.filter((group) => {
      if (hostsFilter === "with_hosts" && group.target_count <= 0) return false;
      if (hostsFilter === "empty" && group.target_count > 0) return false;

      const schedule = group.schedule;
      if (scheduleFilter === "none" && schedule) return false;
      if (scheduleFilter === "scheduled" && !schedule) return false;
      if (scheduleFilter === "enabled" && !(schedule && schedule.enabled)) return false;
      if (scheduleFilter === "paused" && !(schedule && !schedule.enabled)) return false;

      if (!query) return true;
      const haystack = [
        group.name,
        group.description || "",
        schedule ? describeSchedule(schedule, t) : "",
        schedule?.last_status || "",
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(query);
    });
  }, [groups, groupQuery, scheduleFilter, hostsFilter, t]);

  const filtersActive = Boolean(groupQuery || scheduleFilter || hostsFilter);

  async function onCreate(event: FormEvent) {
    event.preventDefault();
    if (!name.trim() || createPending) return;
    setCreatePending(true);
    try {
      const group = await createGroup({ name: name.trim(), description: description.trim() });
      setName("");
      setDescription("");
      pushToast("ok", t("Group created"), group.name);
      onGroupsChanged();
    } catch (error) {
      pushToast("error", t("Group not created"), apiErrorMessage(error, t("Could not create the group.")));
    } finally {
      setCreatePending(false);
    }
  }

  const [scanWindowSeconds, setScanWindowSeconds] = useState<number>(3600);
  const windowOptions = [1800, 3600, 7200];
  const effectiveWindowSeconds = isAdmin ? scanWindowSeconds : 3600;

  async function onScanNow(group: TargetGroup) {
    const modules = currentModules();
    if (modules.length === 0) {
      pushToast("error", t("No modules"), t("Select at least one discovery module."));
      return;
    }
    setBusyId(group.id);
    try {
      const scan = await scanGroup(
        group.id,
        modules,
        newUuid(),
        undefined,
        Number(effectiveWindowSeconds) || 3600,
      );
      pushToast(
        "ok",
        t("Scan queued"),
        `${group.name} · ${t("Targets")}: ${scan.total_batches}`,
      );
      onScanQueued(scan);
    } catch (error) {
      pushToast("error", t("Scan not queued"), apiErrorMessage(error, t("Could not queue scan.")));
    } finally {
      setBusyId(null);
    }
  }

  async function onDelete(group: TargetGroup) {
    const message = t("Delete group \"{name}\"? Hosts and past scans are kept.").replace(
      "{name}",
      group.name,
    );
    if (!window.confirm(message)) return;
    setBusyId(group.id);
    try {
      await deleteGroup(group.id);
      if (editingId === group.id) closeEditor();
      if (renamingId === group.id) closeRename();
      pushToast("ok", t("Group deleted"), group.name);
      onGroupsChanged();
    } catch (error) {
      pushToast("error", t("Group not deleted"), apiErrorMessage(error, t("Could not delete the group.")));
    } finally {
      setBusyId(null);
    }
  }

  function openRename(group: TargetGroup) {
    setRenamingId(group.id);
    setRenameName(group.name);
    setRenameDescription(group.description || "");
    window.requestAnimationFrame(() =>
      document.getElementById(`group-rename-${group.id}`)?.focus(),
    );
  }

  function closeRename() {
    setRenamingId(null);
    setRenameName("");
    setRenameDescription("");
    setRenamePending(false);
  }

  async function onRename(event: FormEvent) {
    event.preventDefault();
    if (!renamingId || !renameName.trim() || renamePending) return;
    const group = groups.find((item) => item.id === renamingId);
    if (!group) return;
    const nextName = renameName.trim();
    const nextDescription = renameDescription.trim();
    if (nextName === group.name && nextDescription === (group.description || "")) {
      closeRename();
      return;
    }
    setRenamePending(true);
    setBusyId(group.id);
    try {
      const updated = await updateGroup(group.id, {
        name: nextName,
        description: nextDescription,
      });
      pushToast("ok", t("Group renamed"), updated.name);
      closeRename();
      onGroupsChanged();
    } catch (error) {
      pushToast(
        "error",
        t("Group not renamed"),
        apiErrorMessage(error, t("Could not rename the group.")),
      );
    } finally {
      setRenamePending(false);
      setBusyId(null);
    }
  }

  function openEditor(group: TargetGroup) {
    setEditingId(group.id);
    setDraft(draftFor(group));
    window.requestAnimationFrame(() =>
      document.getElementById("group-schedule-editor")?.scrollIntoView({ block: "start", behavior: "smooth" }),
    );
  }

  function closeEditor() {
    setEditingId(null);
    setDraft(null);
  }

  async function onSaveSchedule(event: FormEvent) {
    event.preventDefault();
    if (!editing || !draft) return;
    const modules = draft.useCurrentModules ? currentModules() : draft.modules;
    if (modules.length === 0) {
      pushToast("error", t("No modules"), t("Select at least one discovery module."));
      return;
    }
    setBusyId(editing.id);
    try {
      const updated = await saveGroupSchedule(editing.id, {
        enabled: draft.enabled,
        frequency: draft.frequency,
        interval_hours: draft.interval_hours,
        time_of_day: draft.time_of_day,
        weekday: draft.weekday,
        modules,
      });
      pushToast("ok", t("Schedule saved"), `${updated.name} · ${describeSchedule(updated.schedule, t)}`);
      closeEditor();
      onGroupsChanged();
    } catch (error) {
      pushToast("error", t("Schedule not saved"), apiErrorMessage(error, t("Could not save the schedule.")));
    } finally {
      setBusyId(null);
    }
  }

  async function onRemoveSchedule() {
    if (!editing) return;
    setBusyId(editing.id);
    try {
      await deleteGroupSchedule(editing.id);
      pushToast("ok", t("Schedule removed"), editing.name);
      closeEditor();
      onGroupsChanged();
    } catch (error) {
      pushToast("error", t("Schedule not removed"), apiErrorMessage(error, t("Could not remove the schedule.")));
    } finally {
      setBusyId(null);
    }
  }

  function update<K extends keyof Draft>(key: K, value: Draft[K]) {
    setDraft((prev) => (prev ? { ...prev, [key]: value } : prev));
  }

  return (
    <>
      <header className="page-header">
        <h1>{t("Groups")}</h1>
        <p>
          {t(
            "Group hosts to scan them together, now or on a schedule. A host can belong to several groups.",
          )}
        </p>
      </header>

      {canMutate && (
        <section className="panel">
          <div className="panel__header">
            <h2>{t("Create group")}</h2>
          </div>
          <form className="panel__body" onSubmit={onCreate} aria-busy={createPending}>
            <div className="form-row">
              <label htmlFor="group-name">{t("Name")}</label>
              <div>
                <input
                  id="group-name"
                  className="input"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="DMZ · Warsaw office · PCI scope"
                  maxLength={100}
                  autoComplete="off"
                />
              </div>
            </div>
            <div className="form-row">
              <label htmlFor="group-description">{t("Description (optional)")}</label>
              <div>
                <input
                  id="group-description"
                  className="input"
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  maxLength={500}
                  autoComplete="off"
                />
              </div>
            </div>
            <div className="actions">
              <button type="submit" className="btn btn--primary" disabled={!name.trim() || createPending}>
                {createPending ? t("Creating…") : t("Create group")}
              </button>
            </div>
          </form>
        </section>
      )}

      <section className="panel">
        <div className="table-toolbar">
          <div className="table-toolbar__count">
            {filteredGroups.length === groups.length
              ? `${groups.length} ${t("groups")}`
              : `${filteredGroups.length} / ${groups.length} ${t("groups")}`}
          </div>
          {canMutate && isAdmin && (
            <label className="table-toolbar__window">
              <span className="field-help">{t("Scan window")}</span>
              <select
                className="input input--select"
                value={String(effectiveWindowSeconds)}
                onChange={(event) => setScanWindowSeconds(Number(event.target.value) || 3600)}
                aria-label={t("Scan window")}
                title={t(
                  "Required deadline for every scan; unfinished batches pause and can be resumed. The window selector is admin-only — other roles always run with a 1h maximum.",
                )}
              >
                {windowOptions.map((seconds) => (
                  <option key={seconds} value={String(seconds)}>
                    {seconds === 1800 ? "30m" : seconds === 3600 ? "1h" : "2h"}
                  </option>
                ))}
              </select>
            </label>
          )}
          {canMutate && !isAdmin && (
            <span className="table-toolbar__window field-help">
              {t(
                "Fixed 1h deadline for your role. Only admins can change the window length; unfinished batches pause and can be resumed.",
              )}
            </span>
          )}
        </div>
        <div className="target-filters">
          <div className="target-filters__field">
            <label htmlFor="groups-filter-query">{t("Filter")}</label>
            <input
              id="groups-filter-query"
              className="input"
              type="search"
              value={groupQuery}
              onChange={(event) => setGroupQuery(event.target.value)}
              placeholder={t("Group name or description")}
            />
          </div>
          <div className="target-filters__field">
            <label htmlFor="groups-filter-schedule">{t("Schedule")}</label>
            <select
              id="groups-filter-schedule"
              className="input input--select"
              value={scheduleFilter}
              onChange={(event) =>
                setScheduleFilter(
                  event.target.value as "" | "scheduled" | "enabled" | "paused" | "none",
                )
              }
            >
              <option value="">{t("All schedules")}</option>
              <option value="scheduled">{t("Scheduled")}</option>
              <option value="enabled">{t("Schedule enabled")}</option>
              <option value="paused">{t("Schedule paused")}</option>
              <option value="none">{t("Not scheduled")}</option>
            </select>
          </div>
          <div className="target-filters__field">
            <label htmlFor="groups-filter-hosts">{t("Hosts")}</label>
            <select
              id="groups-filter-hosts"
              className="input input--select"
              value={hostsFilter}
              onChange={(event) =>
                setHostsFilter(event.target.value as "" | "with_hosts" | "empty")
              }
            >
              <option value="">{t("Any host count")}</option>
              <option value="with_hosts">{t("With hosts")}</option>
              <option value="empty">{t("Empty groups")}</option>
            </select>
          </div>
          {filtersActive && (
            <div className="target-filters__field target-filters__field--action">
              <label className="sr-only">{t("Clear filters")}</label>
              <button
                type="button"
                className="btn"
                onClick={() => {
                  setGroupQuery("");
                  setScheduleFilter("");
                  setHostsFilter("");
                }}
              >
                {t("Clear filters")}
              </button>
            </div>
          )}
        </div>
        <div className="table-wrap" aria-busy={loading}>
          {groups.length === 0 ? (
            <div className="empty">
              <strong>{t("No groups")}</strong>
              {t("Create a group here, add hosts from the Targets page, or assign a group when importing a file.")}
            </div>
          ) : filteredGroups.length === 0 ? (
            <div className="empty">
              <strong>{t("No groups match filters")}</strong>
              {t("Try another schedule, host count, or search term.")}
            </div>
          ) : (
            <table className="hosts hosts--groups">
              <caption className="sr-only">{t("Host groups")}</caption>
              <thead>
                <tr>
                  <th scope="col">{t("Group")}</th>
                  <th scope="col">{t("Hosts")}</th>
                  <th scope="col">{t("Schedule")}</th>
                  <th scope="col">{t("Next run")}</th>
                  <th scope="col">{t("Last scheduled run")}</th>
                  <th scope="col">{t("Actions")}</th>
                </tr>
              </thead>
              <tbody>
                {filteredGroups.map((group) => {
                  const busy = busyId === group.id;
                  const schedule = group.schedule;
                  return (
                    <tr key={group.id} className={editingId === group.id || renamingId === group.id ? "is-selected" : undefined}>
                      <td>
                        {renamingId === group.id ? (
                          <form className="group-rename" onSubmit={onRename}>
                            <label className="sr-only" htmlFor={`group-rename-${group.id}`}>
                              {t("Name")}
                            </label>
                            <input
                              id={`group-rename-${group.id}`}
                              value={renameName}
                              onChange={(event) => setRenameName(event.target.value)}
                              disabled={renamePending}
                              required
                              maxLength={120}
                              autoComplete="off"
                            />
                            <label className="sr-only" htmlFor={`group-rename-desc-${group.id}`}>
                              {t("Description (optional)")}
                            </label>
                            <input
                              id={`group-rename-desc-${group.id}`}
                              value={renameDescription}
                              onChange={(event) => setRenameDescription(event.target.value)}
                              disabled={renamePending}
                              placeholder={t("Description (optional)")}
                              maxLength={500}
                              autoComplete="off"
                            />
                            <div className="scan-actions">
                              <button
                                type="submit"
                                className="btn btn--primary"
                                disabled={!renameName.trim() || renamePending}
                                aria-busy={renamePending}
                              >
                                {renamePending ? t("Saving…") : t("Save")}
                              </button>
                              <button
                                type="button"
                                className="btn btn--normal"
                                onClick={closeRename}
                                disabled={renamePending}
                              >
                                {t("Cancel")}
                              </button>
                            </div>
                          </form>
                        ) : (
                          <>
                            <strong>{group.name}</strong>
                            {group.description && (
                              <span className="group-description">{group.description}</span>
                            )}
                          </>
                        )}
                      </td>
                      <td className="mono">{group.target_count}</td>
                      <td>
                        <span className={`schedule-state ${schedule?.enabled ? "is-on" : ""}`}>
                          {describeSchedule(schedule, t)}
                        </span>
                      </td>
                      <td>
                        {schedule?.next_run_at ? new Date(schedule.next_run_at).toLocaleString() : "—"}
                      </td>
                      <td className="schedule-last">
                        {schedule?.last_status || "—"}
                      </td>
                      <td className="group-actions">
                        <button type="button" className="btn btn--normal" onClick={() => onShowHosts(group.id)}>
                          {t("Show hosts")}
                        </button>
                        {canMutate && (
                          <>
                            <button
                              type="button"
                              className="btn btn--primary"
                              onClick={() => onScanNow(group)}
                              disabled={busy || group.target_count === 0 || renamingId === group.id}
                              aria-busy={busy}
                            >
                              {t("Scan now")}
                            </button>
                            <button
                              type="button"
                              className="btn btn--normal"
                              onClick={() => openRename(group)}
                              disabled={busy || renamingId === group.id}
                            >
                              {t("Rename")}
                            </button>
                            <button
                              type="button"
                              className="btn btn--normal"
                              onClick={() => openEditor(group)}
                              disabled={busy || renamingId === group.id}
                            >
                              {schedule ? t("Edit schedule") : t("Schedule")}
                            </button>
                            <button
                              type="button"
                              className="btn btn--danger"
                              onClick={() => onDelete(group)}
                              disabled={busy || renamingId === group.id}
                            >
                              {t("Delete")}
                            </button>
                          </>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </section>

      {canMutate && editing && draft && (
        <section className="panel" id="group-schedule-editor">
          <div className="panel__header">
            <h2>
              {t("Schedule")}: {editing.name}
            </h2>
          </div>
          <form className="panel__body" onSubmit={onSaveSchedule} aria-busy={busyId === editing.id}>
            <div className="form-row">
              <label htmlFor="schedule-enabled">{t("Active")}</label>
              <div>
                <label className="filter-row filter-row--bool" htmlFor="schedule-enabled">
                  <input
                    id="schedule-enabled"
                    type="checkbox"
                    checked={draft.enabled}
                    onChange={(event) => update("enabled", event.target.checked)}
                  />
                  <span className="field-help">{t("Uncheck to pause without losing the settings.")}</span>
                </label>
              </div>
            </div>
            <div className="form-row">
              <label htmlFor="schedule-frequency">{t("Repeat")}</label>
              <div>
                <select
                  id="schedule-frequency"
                  className="input input--select"
                  value={draft.frequency}
                  onChange={(event) => update("frequency", event.target.value as ScheduleFrequency)}
                >
                  <option value="hourly">{t("Every N hours")}</option>
                  <option value="daily">{t("Daily")}</option>
                  <option value="weekly">{t("Weekly")}</option>
                </select>
              </div>
            </div>
            {draft.frequency === "hourly" ? (
              <div className="form-row">
                <label htmlFor="schedule-interval">{t("Interval (hours)")}</label>
                <div>
                  <input
                    id="schedule-interval"
                    className="input"
                    type="number"
                    min={1}
                    max={168}
                    value={draft.interval_hours}
                    onChange={(event) => update("interval_hours", Number(event.target.value))}
                  />
                  <p className="field-help">{t("1–168. Counted from the moment the schedule is saved.")}</p>
                </div>
              </div>
            ) : (
              <>
                {draft.frequency === "weekly" && (
                  <div className="form-row">
                    <label htmlFor="schedule-weekday">{t("Day")}</label>
                    <div>
                      <select
                        id="schedule-weekday"
                        className="input input--select"
                        value={draft.weekday}
                        onChange={(event) => update("weekday", Number(event.target.value))}
                      >
                        {WEEKDAYS.map((day, index) => (
                          <option key={day} value={index}>
                            {t(day)}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>
                )}
                <div className="form-row">
                  <label htmlFor="schedule-time">{t("Time (UTC)")}</label>
                  <div>
                    <input
                      id="schedule-time"
                      className="input"
                      type="time"
                      value={draft.time_of_day}
                      onChange={(event) => update("time_of_day", event.target.value)}
                      required
                    />
                    <p className="field-help">
                      {t("Scans start within about a minute of this time. Missed runs are not replayed.")}
                    </p>
                  </div>
                </div>
              </>
            )}
            <div className="form-row">
              <label htmlFor="schedule-modules">{t("Modules")}</label>
              <div>
                {editing.schedule ? (
                  <label className="filter-row filter-row--bool" htmlFor="schedule-modules">
                    <input
                      id="schedule-modules"
                      type="checkbox"
                      checked={draft.useCurrentModules}
                      onChange={(event) => update("useCurrentModules", event.target.checked)}
                    />
                    <span className="field-help">{t("Replace with the modules selected on the Dashboard")}</span>
                  </label>
                ) : null}
                <p className="field-help mono" id="schedule-modules-summary">
                  {describeModules(draft.useCurrentModules ? currentModules() : draft.modules)}
                </p>
                {!editing.schedule && (
                  <p className="field-help">{t("New schedules use the modules selected on the Dashboard.")}</p>
                )}
              </div>
            </div>
            <div className="flash" role="note">
              <div>
                <p>{t("Results of every finished scheduled scan are sent to DefectDojo automatically when it is configured.")}</p>
              </div>
            </div>
            <div className="actions">
              <button type="submit" className="btn btn--primary" disabled={busyId === editing.id}>
                {t("Save schedule")}
              </button>
              {editing.schedule && (
                <button
                  type="button"
                  className="btn btn--danger"
                  onClick={onRemoveSchedule}
                  disabled={busyId === editing.id}
                >
                  {t("Remove schedule")}
                </button>
              )}
              <button type="button" className="btn btn--normal" onClick={closeEditor}>
                {t("Cancel")}
              </button>
            </div>
          </form>
        </section>
      )}
    </>
  );
}
