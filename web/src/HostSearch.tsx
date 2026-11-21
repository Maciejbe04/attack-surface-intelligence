import { KeyboardEvent, useEffect, useRef, useState } from "react";
import { Target, apiErrorMessage, searchTargets } from "./api/scans";
import { Translate } from "./i18n";

const DEBOUNCE_MS = 200;
const RESULT_LIMIT = 8;

type SearchState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ready"; results: Target[] }
  | { kind: "error"; message: string };

function looksLikeTarget(value: string): boolean {
  const v = value.trim();
  if (!v || v.includes(" ")) return false;
  if (v.includes("/")) {
    const [ip, prefix] = v.split("/");
    const p = Number(prefix);
    if (!/^\d{1,3}(\.\d{1,3}){3}$/.test(ip)) return false;
    if (!Number.isInteger(p) || p < 0 || p > 32) return false;
    return ip.split(".").every((part) => {
      const n = Number(part);
      return Number.isInteger(n) && n >= 0 && n <= 255;
    });
  }
  if (/^\d{1,3}(\.\d{1,3}){3}$/.test(v)) {
    return v.split(".").every((part) => {
      const n = Number(part);
      return Number.isInteger(n) && n >= 0 && n <= 255;
    });
  }
  return /^[a-z0-9.-]+$/i.test(v) && v.includes(".");
}

/**
 * Typeahead over saved targets (ARIA 1.2 combobox). Searches address and comment
 * on the server, so it stays fast with thousands of hosts. When nothing matches,
 * Enter / Add target creates the host on the target list.
 */
export function HostSearch({
  id,
  selected,
  onSelect,
  onCreateMissing,
  t,
}: {
  id: string;
  selected: Target | null;
  onSelect: (target: Target | null) => void;
  onCreateMissing?: (address: string) => Promise<Target | null>;
  t: Translate;
}) {
  const [query, setQuery] = useState(selected?.address ?? "");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [state, setState] = useState<SearchState>({ kind: "idle" });
  const [creating, setCreating] = useState(false);
  const [missingQuery, setMissingQuery] = useState<string | null>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const listId = `${id}-results`;

  useEffect(() => {
    if (selected && selected.address !== query) setQuery(selected.address);
    // Only react to the parent choosing a different target.
  }, [selected?.id]);

  useEffect(() => {
    const text = query.trim();
    if (!open || !text) {
      setState({ kind: "idle" });
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setState({ kind: "loading" });
      searchTargets(text, RESULT_LIMIT, controller.signal)
        .then((results) => {
          setState({ kind: "ready", results });
          setActive(0);
          setMissingQuery(results.length === 0 ? text : null);
        })
        .catch((error: unknown) => {
          if (error instanceof DOMException && error.name === "AbortError") return;
          setState({ kind: "error", message: apiErrorMessage(error, t("Search failed.")) });
        });
    }, DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [query, open]);

  useEffect(() => {
    function onPointerDown(event: PointerEvent) {
      if (!wrapperRef.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, []);

  const results = state.kind === "ready" ? state.results : [];
  const trimmed = query.trim();
  const showCreateOption =
    Boolean(onCreateMissing) &&
    state.kind === "ready" &&
    results.length === 0 &&
    looksLikeTarget(trimmed);
  const canCreate =
    Boolean(onCreateMissing) &&
    !creating &&
    looksLikeTarget(trimmed) &&
    missingQuery === trimmed;
  const createOptionId = `${listId}-create`;

  function choose(target: Target) {
    onSelect(target);
    setQuery(target.address);
    setMissingQuery(null);
    setOpen(false);
  }

  async function createMissing() {
    if (!onCreateMissing || !canCreate) return;
    setCreating(true);
    try {
      const target = await onCreateMissing(trimmed);
      if (target) choose(target);
    } finally {
      setCreating(false);
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setOpen(true);
      setActive((index) => Math.min(index + 1, Math.max(results.length - 1, 0)));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((index) => Math.max(index - 1, 0));
    } else if (event.key === "Enter") {
      if (open && results[active]) {
        event.preventDefault();
        choose(results[active]);
      } else if (canCreate) {
        event.preventDefault();
        void createMissing();
      }
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  }

  const expanded = open && state.kind !== "idle";

  return (
    <div className="host-search" ref={wrapperRef}>
      <div className="host-search__row">
        <input
          id={id}
          className="input mono"
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={expanded}
          aria-controls={listId}
          aria-activedescendant={
            expanded && results[active]
              ? `${listId}-${results[active].id}`
              : expanded && showCreateOption
                ? createOptionId
                : undefined
          }
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setMissingQuery(null);
            setOpen(true);
            if (selected && event.target.value !== selected.address) onSelect(null);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={onKeyDown}
          placeholder=""
          autoComplete="off"
          spellCheck={false}
        />
        {onCreateMissing && (
          <button
            type="button"
            className="btn btn--normal host-search__add"
            disabled={!canCreate}
            aria-busy={creating}
            onClick={() => void createMissing()}
          >
            {creating ? t("Adding…") : t("Add target")}
          </button>
        )}
      </div>
      {expanded && (
        <div className="host-search__popup">
          {state.kind === "loading" && (
            <p className="host-search__note" role="status">
              {t("Searching…")}
            </p>
          )}
          {state.kind === "error" && (
            <p className="host-search__note host-search__note--error" role="alert">
              {state.message}
            </p>
          )}
          {state.kind === "ready" && results.length === 0 && !showCreateOption && (
            <p className="host-search__note" role="status">
              {onCreateMissing
                ? t("No saved host matches. Type a valid IP, CIDR, or hostname.")
                : t("No saved host matches. Add it on the Targets page first.")}
            </p>
          )}
          {showCreateOption && (
            <ul id={listId} role="listbox" className="host-search__list" aria-label={t("Matching hosts")}>
              <li
                id={createOptionId}
                role="option"
                aria-selected
                className="host-search__option host-search__option--create is-active"
                onPointerDown={(event) => event.preventDefault()}
                onClick={() => void createMissing()}
              >
                <span className="host-search__address mono">{trimmed}</span>
                <span className="host-search__type">{t("Add target")}</span>
                <span className="host-search__comment">
                  {t("Not on the target list — press Enter to add.")}
                </span>
              </li>
            </ul>
          )}
          {results.length > 0 && (
            <ul id={listId} role="listbox" className="host-search__list" aria-label={t("Matching hosts")}>
              {results.map((target, index) => (
                <li
                  key={target.id}
                  id={`${listId}-${target.id}`}
                  role="option"
                  aria-selected={index === active}
                  className={`host-search__option ${index === active ? "is-active" : ""}`}
                  onPointerDown={(event) => event.preventDefault()}
                  onClick={() => choose(target)}
                  onMouseEnter={() => setActive(index)}
                >
                  <span className="host-search__address mono">{target.address}</span>
                  <span className="host-search__type">{target.type}</span>
                  {target.groups.length > 0 && (
                    <span className="host-search__groups">
                      {target.groups.map((group) => (
                        <span key={group.id} className="group-chip">
                          {group.name}
                        </span>
                      ))}
                    </span>
                  )}
                  {target.comment && (
                    <span className="host-search__comment">{target.comment}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
