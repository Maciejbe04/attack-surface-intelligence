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

function ModuleCard({
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
  return (
    <article className={`module-card ${enabled ? "is-selected" : ""} ${expanded ? "is-open" : ""}`}>
      <div className="module-card__head">
        <label className="module-card__enable">
          <input type="checkbox" checked={enabled} onChange={onToggleEnabled} />
          <span className="module-card__body">
            <span className="module-card__name">{module.name}</span>
            <span className="module-card__summary">{module.summary}</span>
            <span className="module-card__tool">{module.tool}</span>
          </span>
        </label>
        <button
          type="button"
          className="btn btn--normal module-card__expand"
          aria-expanded={expanded}
          onClick={onToggleExpanded}
        >
          {expanded ? "Hide filters" : "Filters"}
        </button>
      </div>

      {expanded && (
        <div className="module-card__filters">
          {module.filters.length === 0 ? (
            <p className="field-help">No configurable filters for this module yet.</p>
          ) : (
            module.filters.map((field) => (
              <FilterControl
                key={field.key}
                moduleId={module.id}
                field={field}
                value={filters[field.key] ?? field.default}
                onChange={onFilterChange}
              />
            ))
          )}
          <p className="module-card__preview mono">Active: {summarizeFilters(filters)}</p>
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
      <div className="module-list">
        {PROBE_MODULES.map((mod) => {
          const cfg = state[mod.id];
          if (!cfg) return null;
          return (
            <ModuleCard
              key={mod.id}
              module={mod}
              enabled={cfg.enabled}
              expanded={cfg.expanded}
              filters={cfg.filters}
              onToggleEnabled={() => onToggleEnabled(mod.id)}
              onToggleExpanded={() => onToggleExpanded(mod.id)}
              onFilterChange={(key, value) => onFilterChange(mod.id, key, value)}
            />
          );
        })}
      </div>
      <div className="panel__footer">
        <span className="table-toolbar__count">
          {enabledCount} module{enabledCount === 1 ? "" : "s"} selected · filters are per module
        </span>
      </div>
    </section>
  );
}
