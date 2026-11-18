import Icon from "./Icon";
import { useI18n } from "../lib/useI18n";

interface Props {
  theme: string;
  onToggleTheme: () => void;
  onToggleLanguage: () => void;
  onHelp: () => void;
  onNewIdea: () => void;
}
export default function Header({
  theme,
  onToggleTheme,
  onToggleLanguage,
  onHelp,
  onNewIdea,
}: Props) {
  const { t, lang } = useI18n();
  const other = lang === "en" ? "ro" : "en";
  return (
    <header className="topbar">
      <a className="brand" href="/">
        <span className="brand-mark">
          <Icon name="graph" size={22} />
        </span>
        <span className="brand-name">
          idea<span className="brand-light">evolution</span>
          <small>{t("brand.tagline")}</small>
        </span>
      </a>
      <div className="header-center">
        <span className="public-dot" /> {t("header.community")}
        <span className="pill">{t("header.public")}</span>
      </div>
      <div className="top-actions">
        <button
          className="icon-button lang-button"
          onClick={onToggleLanguage}
          lang={other}
          aria-label={`${other.toUpperCase()} · ${t("header.language")}`}
          title={t("lang.switchTo")}
        >
          {other.toUpperCase()}
        </button>
        <button
          className="icon-button"
          onClick={onHelp}
          aria-label={t("header.help")}
          title={t("header.help")}
        >
          <Icon name="help" />
        </button>
        <button
          className="icon-button"
          onClick={onToggleTheme}
          aria-label={
            theme === "light" ? t("header.themeDark") : t("header.themeLight")
          }
        >
          <Icon name={theme === "light" ? "moon" : "sun"} />
        </button>
        <button className="button primary new-idea-top" onClick={onNewIdea}>
          <Icon name="plus" /> {t("header.newIdea")}
        </button>
      </div>
    </header>
  );
}
