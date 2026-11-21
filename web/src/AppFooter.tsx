import { APP_NAME, APP_VERSION } from "./version";

type Props = {
  highContrast: boolean;
  onToggleContrast: () => void;
};

export function AppFooter({ highContrast, onToggleContrast }: Props) {
  return (
    <footer className="app-footer" role="contentinfo">
      <div className="app-footer__left">
        <span>
          {APP_NAME}{" "}
          <span className="mono" aria-label={`version ${APP_VERSION}`}>
            v{APP_VERSION}
          </span>
        </span>
        <span className="app-footer__sep" aria-hidden="true">
          ·
        </span>
        <span>Local discovery console</span>
      </div>
      <div className="app-footer__right">
        <button
          type="button"
          className="btn btn--normal app-footer__contrast"
          aria-pressed={highContrast}
          aria-label={
            highContrast ? "Switch to standard contrast" : "Switch to high contrast"
          }
          onClick={onToggleContrast}
        >
          {highContrast ? "Standard contrast" : "High contrast"}
        </button>
        <button
          type="button"
          className="btn btn--normal"
          onClick={() => document.getElementById("a11y-help")?.focus()}
        >
          Accessibility tips
        </button>
      </div>
    </footer>
  );
}
