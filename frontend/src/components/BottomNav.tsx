import Icon, { type IconName } from "./Icon";
import { useI18n } from "../lib/useI18n";
import type { MessageKey } from "../lib/i18n";

export type NavTarget = "garden" | "discover" | "plant" | "saved";
const items: { id: NavTarget; icon: IconName; label: MessageKey }[] = [
  { id: "garden", icon: "graph", label: "nav.garden" },
  { id: "discover", icon: "compass", label: "nav.discover" },
  { id: "plant", icon: "plus", label: "nav.plant" },
  { id: "saved", icon: "star", label: "nav.saved" },
];
export default function BottomNav({
  active,
  savedCount,
  onNavigate,
}: {
  active: NavTarget;
  savedCount: number;
  onNavigate: (target: NavTarget) => void;
}) {
  const { t } = useI18n();
  return (
    <nav className="bottom-nav" aria-label={t("nav.label")}>
      {items.map((item) => (
        <button
          key={item.id}
          className={item.id === "plant" ? "plant" : ""}
          aria-current={active === item.id ? "true" : undefined}
          onClick={() => onNavigate(item.id)}
        >
          <span className="bottom-icon">
            <Icon name={item.icon} size={item.id === "plant" ? 22 : 20} />
            {item.id === "saved" && savedCount > 0 && (
              <span className="bottom-badge" aria-hidden="true">
                {savedCount > 99 ? "99+" : savedCount}
              </span>
            )}
          </span>
          <span>{t(item.label)}</span>
        </button>
      ))}
    </nav>
  );
}
