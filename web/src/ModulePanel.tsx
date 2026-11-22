import { Translate } from "./i18n";
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
  t: Translate;
};

const CATEGORY_LABEL: Record<ProbeModule["category"], string> = {
  discovery: "Discovery",
  http: "HTTP",
  tls: "TLS",
  signatures: "Signatures",
  pipeline: "Pipeline",
};

const CATEGORY_DESCRIPTION: Record<ProbeModule["category"], string> = {
  discovery: "Find live hosts and exposed network services.",
  http: "Inspect web endpoints and response metadata.",
  tls: "Collect certificate and TLS configuration details.",
  signatures: "Match observed services against known fingerprints.",
  pipeline: "Run a combined discovery workflow.",
};

const CATEGORY_ORDER: ProbeModule["category"][] = [
  "discovery",
  "http",
  "tls",
  "signatures",
  "pipeline",
];

function FilterControl({
  moduleId,
  field,
  value,
  onChange,
  t,
}: {
  moduleId: string;
  field: FilterField;
  value: string | number | boolean;
  onChange: (key: string, value: string | number | boolean) => void;
  t: Translate;
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
          <span className="filter-row__label">{t(field.label)}</span>
          {field.help && <span className="field-help">{t(field.help)}</span>}
        </span>
      </label>
    );
  }

  return (
    <div className="filter-row">
      <label htmlFor={inputId}>{t(field.label)}</label>
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
                {t(opt.label)}
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
        {field.help && <p className="field-help">{t(field.help)}</p>}
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
  t,
}: {
  module: ProbeModule;
  enabled: boolean;
  expanded: boolean;
  filters: ModuleFilterValues;
  onToggleEnabled: () => void;
  onToggleExpanded: () => void;
  onFilterChange: (key: string, value: string | number | boolean) => void;
  t: Translate;
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
        <div className="module-tile__identity">
          <label className="module-tile__check">
            <input
              type="checkbox"
              checked={enabled}
              onChange={onToggleEnabled}
              aria-describedby={`${titleId}-summary`}
            />
            <span className="sr-only">{t("Enabled")} {t(module.name)}</span>
          </label>
          <div>
            <h3 className="module-tile__name" id={titleId}>
              {t(module.name)}
            </h3>
            <p className="module-tile__summary" id={`${titleId}-summary`}>
              {t(module.summary)}
            </p>
          </div>
        </div>

        <div className="module-tile__meta">
          <span className="module-tile__tool mono">{module.tool}</span>
          {hasFilters && (
            <span className="module-tile__chip mono" title={filterPreview}>
              {filterPreview}
            </span>
          )}
        </div>
      </div>

      <footer className="module-tile__footer">
        <span className={`module-tile__state ${enabled ? "is-on" : ""}`}>
          {enabled ? t("Enabled") : t("Disabled")}
        </span>
        <div className="module-tile__actions">
          <button
            type="button"
            className="btn btn--normal module-tile__filters-btn"
            aria-expanded={expanded}
            aria-controls={filtersId}
            disabled={!hasFilters && !expanded}
            onClick={onToggleExpanded}
          >
            {expanded ? t("Hide filters") : hasFilters ? t("Filters") : t("No filters")}
          </button>
        </div>
      </footer>

      {expanded && hasFilters && (
        <section
          className="module-tile__drawer"
          id={filtersId}
          aria-label={`${module.name} filters`}
        >
          <div className="module-tile__drawer-head">
            <strong>{t("Module filters")}</strong>
            <span>{t("Configure this module before running discovery.")}</span>
          </div>
          <div className="module-tile__filter-grid">
            {module.filters.map((field) => (
              <FilterControl
                key={field.key}
                moduleId={module.id}
                field={field}
                value={filters[field.key] ?? field.default}
                onChange={onFilterChange}
                t={t}
              />
            ))}
          </div>
          <div className="module-tile__drawer-bottom">
            <p className="module-tile__preview mono">{t("Active")}: {filterPreview}</p>
            <button type="button" className="btn btn--normal" onClick={onToggleExpanded}>
              {t("Close filters")}
            </button>
          </div>
        </section>
      )}
    </article>
  );
}

export function ModulePanel({
  state,
  onToggleEnabled,
  onToggleExpanded,
  onFilterChange,
  t,
}: Props) {
  const enabledCount = Object.values(state).filter((s) => s.enabled).length;

  return (
    <section className="panel">
      <div className="panel__header">
        <h2>{t("Discovery modules")}</h2>
      </div>
      <div className="module-groups">
        {CATEGORY_ORDER.map((category) => {
          const modules = PROBE_MODULES.filter((module) => module.category === category);
          if (modules.length === 0) return null;

          return (
            <section
              className={`module-group module-group--${category}`}
              key={category}
              aria-labelledby={`module-category-${category}`}
            >
              <header className="module-group__header">
                <div>
                  <h3 id={`module-category-${category}`}>{t(CATEGORY_LABEL[category])}</h3>
                  <p>{t(CATEGORY_DESCRIPTION[category])}</p>
                </div>
                <span>{modules.length}</span>
              </header>
              <div className="module-list" role="list">
                {modules.map((mod) => {
                  const cfg = state[mod.id];
                  if (!cfg) return null;
                  return (
                    <div key={mod.id} role="listitem">
                      <ModuleTile
                        module={mod}
                        enabled={cfg.enabled}
                        expanded={cfg.expanded}
                        filters={cfg.filters}
                        onToggleEnabled={() => onToggleEnabled(mod.id)}
                        onToggleExpanded={() => onToggleExpanded(mod.id)}
                        onFilterChange={(key, value) => onFilterChange(mod.id, key, value)}
                        t={t}
                      />
                    </div>
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>
      <div className="panel__footer">
        <span className="table-toolbar__count">
          {enabledCount} module{enabledCount === 1 ? "" : "s"} selected · filters expand below
          each module
        </span>
      </div>
    </section>
  );
}
