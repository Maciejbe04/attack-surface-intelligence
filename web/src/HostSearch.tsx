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

/**
 * Typeahead over saved targets (ARIA 1.2 combobox). Searches address and comment
 * on the server, so it stays fast with thousands of hosts.
 */
export function HostSearch({
  id,
  selected,
  onSelect,
  t,
}: {
  id: string;
  selected: Target | null;
  onSelect: (target: Target | null) => void;
  t: Translate;
}) {
  const [query, setQuery] = useState(selected?.address ?? "");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [state, setState] = useState<SearchState>({ kind: "idle" });
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

  function choose(target: Target) {
    onSelect(target);
    setQuery(target.address);
    setOpen(false);
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setOpen(true);
      setActive((index) => Math.min(index + 1, Math.max(results.length - 1, 0)));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((index) => Math.max(index - 1, 0));
    } else if (event.key === "Enter" && open && results[active]) {
      event.preventDefault();
      choose(results[active]);
    } else if (event.key === "Escape") {
      setOpen(false);
    }
  }

  const expanded = open && state.kind !== "idle";

  return (
    <div className="host-search" ref={wrapperRef}>
      <input
        id={id}
        className="input mono"
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={expanded}
        aria-controls={listId}
        aria-activedescendant={
          expanded && results[active] ? `${listId}-${results[active].id}` : undefined
        }
        value={query}
        onChange={(event) => {
          setQuery(event.target.value);
          setOpen(true);
          if (selected && event.target.value !== selected.address) onSelect(null);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        placeholder=""
        autoComplete="off"
        spellCheck={false}
      />
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
          {state.kind === "ready" && results.length === 0 && (
            <p className="host-search__note" role="status">
              {t("No saved host matches. Add it on the Targets page first.")}
            </p>
          )}
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
        </div>
      )}
    </div>
  );
}
