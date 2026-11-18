import type { ReactNode } from "react";
import Icon, { type IconName } from "./Icon";
import type { Idea } from "../lib/ideas";
import type { MessageKey } from "../lib/i18n";
import { useI18n } from "../lib/useI18n";

export type Scope = "all" | "saved" | "mine" | "leaves";
const scopes: { id: Scope; icon: IconName; label: MessageKey }[] = [
  { id: "all", icon: "graph", label: "library.all" },
  { id: "saved", icon: "star", label: "library.saved" },
  { id: "mine", icon: "user", label: "library.mine" },
  { id: "leaves", icon: "leaf", label: "library.unexplored" },
];
interface Props {
  open: boolean;
  scope: Scope;
  root: string;
  counts: Partial<Record<Scope, number | undefined>>;
  seeds: Idea[];
  seedTotal: number | undefined;
  onClose: () => void;
  onScope: (scope: Scope) => void;
  onSeed: (idea: Idea) => void;
  children: ReactNode;
}
export default function Library({
  open,
  scope,
  root,
  counts,
  seeds,
  seedTotal,
  onClose,
  onScope,
  onSeed,
  children,
}: Props) {
  const { t } = useI18n();
  return (
    <aside
      className={`library ${open ? "mobile-open" : ""}`}
      aria-label={t("library.label")}
    >
      <div className="library-title">
        <span className="eyebrow">{t("library.title")}</span>
        <button
          className="icon-button mobile-close"
          onClick={onClose}
          aria-label={t("library.close")}
        >
          <Icon name="close" />
        </button>
      </div>
      <nav className="library-nav" aria-label={t("library.filters")}>
        {scopes.map((item) => (
          <button
            key={item.id}
            className={scope === item.id && !root ? "active" : ""}
            aria-pressed={scope === item.id && !root}
            onClick={() => onScope(item.id)}
          >
            <Icon name={item.icon} />
            <span>{t(item.label)}</span>
            {item.id !== "leaves" && (
              <span className="count">{counts[item.id] ?? "—"}</span>
            )}
          </button>
        ))}
      </nav>
      {children}
      <div className="seed-browser">
        <div className="section-label">
          <span>{t("library.seeds")}</span>
          <span>{seedTotal ?? "—"}</span>
        </div>
        <div className="seed-list">
          {seeds
            .slice()
            .reverse()
            .map((idea) => (
              <button
                key={idea.id}
                className={root === String(idea.id) ? "active" : ""}
                onClick={() => onSeed(idea)}
              >
                <span className="seed-dot" />
                <span>{idea.content}</span>
                <Icon name="chevron" size={13} />
              </button>
            ))}
          {!seeds.length && (
            <p className="muted small">{t("library.noSeeds")}</p>
          )}
        </div>
      </div>
      <div className="library-footer">
        <span className="unison-mark">u</span>
        <span>
          {t("footer.powered")} <strong>Unison</strong>
          <small>{t("footer.pure")}</small>
        </span>
      </div>
    </aside>
  );
}
