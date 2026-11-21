import { Language, Translate } from "./i18n";
import { LanguageSelect } from "./LanguageSelect";
import { SystemLockButton } from "./SystemPanel";
import { ThemeToggle } from "./ThemeToggle";
import { APP_NAME, APP_VERSION } from "./version";

type Props = {
  darkMode: boolean;
  onToggleDarkMode: () => void;
  highContrast: boolean;
  onToggleContrast: () => void;
  onOpenSystem?: () => void;
  language: Language;
  onLanguageChange: (language: Language) => void;
  t: Translate;
};

export function AppFooter({
  darkMode,
  onToggleDarkMode,
  highContrast,
  onToggleContrast,
  onOpenSystem,
  language,
  onLanguageChange,
  t,
}: Props) {
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
        <span>{t("Local discovery console")}</span>
      </div>
      <div className="app-footer__right">
        <LanguageSelect
          language={language}
          onChange={onLanguageChange}
          label={t("Language")}
        />
        <ThemeToggle darkMode={darkMode} onToggle={onToggleDarkMode} t={t} />
        <button
          type="button"
          className="btn btn--normal app-footer__contrast"
          aria-pressed={highContrast}
          aria-label={
            highContrast
              ? t("Switch to standard contrast")
              : t("Switch to high contrast")
          }
          onClick={onToggleContrast}
        >
          {highContrast ? t("Standard contrast") : t("High contrast")}
        </button>
        {onOpenSystem && <SystemLockButton onClick={onOpenSystem} t={t} />}
        <button
          type="button"
          className="btn btn--normal"
          onClick={() => document.getElementById("a11y-help")?.focus()}
        >
          {t("Accessibility tips")}
        </button>
      </div>
    </footer>
  );
}
