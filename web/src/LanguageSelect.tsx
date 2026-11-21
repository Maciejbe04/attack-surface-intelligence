import { Language } from "./i18n";

export function LanguageSelect({
  language,
  onChange,
  label = "Language",
  className = "",
}: {
  language: Language;
  onChange: (language: Language) => void;
  label?: string;
  className?: string;
}) {
  return (
    <label className={`language-select ${className}`.trim()}>
      <span className="sr-only">{label}</span>
      <select
        value={language}
        onChange={(event) => onChange(event.target.value as Language)}
        aria-label={label}
      >
        <option value="pl">Polski</option>
        <option value="en">English</option>
      </select>
    </label>
  );
}
