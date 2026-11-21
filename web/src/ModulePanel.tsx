import {
  FilterField,
  ModuleFilterValues,
  ModuleRegistryState,
  PROBE_MODULES,
  ProbeModule,
  summarizeFilters,
} from "./modules";

type Props = {
  state: ModuleRegistryState;
  onToggleEnabled: (id: string) => void;
  onToggleExpanded: (id: string) => void;
  onFilterChange: (id: string, key: string, value: string | number | boolean) => void;
  onRun: () => void;
};

const CATEGORY_LABEL: Record<ProbeModule["category"], string> = {
  discovery: "Discovery",
  http: "HTTP",
  tls: "TLS",
  signatures: "Signatures",
  pipeline: "Pipeline",
};

function FilterControl({
  moduleId,
  field,
  value,
  onChange,
}: {
  moduleId: string;
  field: FilterField;
  value: string | number | boolean;
  onChange: (key: string, value: string | number | boolean) => void;
}) {
  const inputId = `${moduleId}-${field.key}`;

  if (field.type === "boolean") {
    return (
      <label className="filter-row filter-row--bool" htmlFor={inputId}>
        <input
          id={inputId}
          type="checkbox"
          checked={Boolean(value)}
          onChange={(e) => onChange(field.key, e.target.checked)}
        />
        <span>
          <span className="filter-row__label">{field.label}</span>
          {field.help && <span className="field-help">{field.help}</span>}
        </span>
      </label>
    );
  }

  return (
    <div className="filter-row">
      <label htmlFor={inputId}>{field.label}</label>
      <div>
        {field.type === "select" && (
          <select
            id={inputId}
            className="input input--select"
            value={String(value)}
            onChange={(e) => onChange(field.key, e.target.value)}
          >
            {field.options.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        )}
        {field.type === "text" && (
          <input
            id={inputId}
            className="input"
            value={String(value)}
            placeholder={field.placeholder}
            onChange={(e) => onChange(field.key, e.target.value)}
            spellCheck={false}
          />
        )}
        {field.type === "number" && (
          <input
            id={inputId}
            className="input"
            type="number"
            value={Number(value)}
            min={field.min}
            max={field.max}
            onChange={(e) => onChange(field.key, Number(e.target.value))}
          />
        )}
        {field.help && <p className="field-help">{field.help}</p>}
      </div>
    </div>
  );
}

function ModuleTile({
  module,
  enabled,
  expanded,
  filters,
  onToggleEnabled,
  onToggleExpanded,
  onFilterChange,
}: {
  module: ProbeModule;
  enabled: boolean;
  expanded: boolean;
  filters: ModuleFilterValues;
  onToggleEnabled: () => void;
  onToggleExpanded: () => void;
  onFilterChange: (key: string, value: string | number | boolean) => void;
}) {
  const titleId = `module-title-${module.id}`;
  const filtersId = `module-filters-${module.id}`;
  const filterPreview = summarizeFilters(filters);
  const hasFilters = module.filters.length > 0;

  return (
    <article
      className={[
        "module-tile",
        `module-tile--${module.category}`,
        enabled ? "is-selected" : "",
        expanded ? "is-open" : "",
      ]
        .filter(Boolean)
        .join(" ")}
      aria-labelledby={titleId}
    >
      <div className="module-tile__face">
        <div className="module-tile__top">
          <span className="module-tile__category">{CATEGORY_LABEL[module.category]}</span>
          <label className="module-tile__check">
            <input
              type="checkbox"
              checked={enabled}
              onChange={onToggleEnabled}
              aria-describedby={`${titleId}-summary`}
            />
            <span className="sr-only">Enable {module.name}</span>
          </label>
        </div>

        <h3 className="module-tile__name" id={titleId}>
          {module.name}
        </h3>
        <p className="module-tile__summary" id={`${titleId}-summary`}>
          {module.summary}
        </p>
        <p className="module-tile__tool mono">{module.tool}</p>

        <div className="module-tile__actions">
          <button
            type="button"
            className="btn btn--normal module-tile__filters-btn"
            aria-expanded={expanded}
            aria-controls={filtersId}
            disabled={!hasFilters && !expanded}
            onClick={onToggleExpanded}
          >
            {expanded ? "Hide filters" : hasFilters ? "Filters" : "No filters"}
          </button>
          {enabled && (
            <span className="module-tile__status" aria-hidden="true">
              On
            </span>
          )}
        </div>

        {!expanded && hasFilters && (
          <p className="module-tile__chip mono" title={filterPreview}>
            {filterPreview}
          </p>
        )}
      </div>

      {expanded && hasFilters && (
        <div
          className="module-drawer-backdrop"
          onMouseDown={onToggleExpanded}
          onKeyDown={(event) => {
            if (event.key === "Escape") onToggleExpanded();
          }}
        >
          <aside
            className="module-drawer"
            id={filtersId}
            role="dialog"
            aria-modal="true"
            aria-labelledby={`${titleId}-drawer`}
            onMouseDown={(event) => event.stopPropagation()}
          >
            <header className="module-drawer__header">
              <div>
                <span className="module-tile__category">{CATEGORY_LABEL[module.category]}</span>
                <h2 id={`${titleId}-drawer`}>{module.name} filters</h2>
                <p>{module.summary}</p>
              </div>
              <button
                type="button"
                className="module-drawer__close"
                aria-label={`Close ${module.name} filters`}
                onClick={onToggleExpanded}
                autoFocus
              >
                ×
              </button>
            </header>
            <div className="module-drawer__body">
              {module.filters.map((field) => (
                <FilterControl
                  key={field.key}
                  moduleId={module.id}
                  field={field}
                  value={filters[field.key] ?? field.default}
                  onChange={onFilterChange}
                />
              ))}
            </div>
            <footer className="module-drawer__footer">
              <p className="module-tile__preview mono">Active: {filterPreview}</p>
              <button type="button" className="btn btn--primary" onClick={onToggleExpanded}>
                Done
              </button>
            </footer>
          </aside>
        </div>
      )}
    </article>
  );
}

export function ModulePanel({
  state,
  onToggleEnabled,
  onToggleExpanded,
  onFilterChange,
  onRun,
}: Props) {
  const enabledCount = Object.values(state).filter((s) => s.enabled).length;

  return (
    <section className="panel">
      <div className="panel__header">
        <h2>Discovery modules</h2>
        <div className="actions">
          <button type="button" className="btn btn--primary" onClick={onRun}>
            Run selected
          </button>
        </div>
      </div>
      <div className="module-grid" role="list">
        {PROBE_MODULES.map((mod) => {
          const cfg = state[mod.id];
          if (!cfg) return null;
          return (
            <div key={mod.id} role="listitem" className="module-grid__item">
              <ModuleTile
                module={mod}
                enabled={cfg.enabled}
                expanded={cfg.expanded}
                filters={cfg.filters}
                onToggleEnabled={() => onToggleEnabled(mod.id)}
                onToggleExpanded={() => onToggleExpanded(mod.id)}
                onFilterChange={(key, value) => onFilterChange(mod.id, key, value)}
              />
            </div>
          );
        })}
      </div>
      <div className="panel__footer">
        <span className="table-toolbar__count">
          {enabledCount} module{enabledCount === 1 ? "" : "s"} selected · filters open in a side
          panel
        </span>
      </div>
    </section>
  );
}
