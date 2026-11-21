import { Translate } from "./i18n";

type Props = {
  darkMode: boolean;
  onToggle: () => void;
  t: Translate;
  className?: string;
};

function MoonIcon() {
  return (
    <svg
      className="theme-toggle__icon"
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
    >
      <path
        fill="currentColor"
        d="M21 14.3A9 9 0 0 1 9.7 3 7.2 7.2 0 1 0 21 14.3Z"
      />
    </svg>
  );
}

function SunIcon() {
  return (
    <svg
      className="theme-toggle__icon"
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
    >
      <circle cx="12" cy="12" r="4" fill="currentColor" />
      <path
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        d="M12 2v2.2M12 19.8V22M4.9 4.9l1.6 1.6M17.5 17.5l1.6 1.6M2 12h2.2M19.8 12H22M4.9 19.1l1.6-1.6M17.5 6.5l1.6-1.6"
      />
    </svg>
  );
}

export function ThemeToggle({ darkMode, onToggle, t, className = "" }: Props) {
  return (
    <button
      type="button"
      className={`btn theme-toggle ${className}`.trim()}
      aria-pressed={darkMode}
      aria-label={darkMode ? t("Switch to light mode") : t("Switch to dark mode")}
      title={darkMode ? t("Switch to light mode") : t("Switch to dark mode")}
      onClick={onToggle}
    >
      {darkMode ? <SunIcon /> : <MoonIcon />}
    </button>
  );
}
