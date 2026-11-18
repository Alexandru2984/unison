import { useEffect, useState } from "react";
import Icon, { type IconName } from "./Icon";
import {
  DISCOVER_SECTIONS,
  fetchDiscoveries,
  type DiscoverSection,
  type Discoveries,
} from "../lib/api";
import type { Idea, Stats } from "../lib/ideas";
import type { MessageKey } from "../lib/i18n";
import { ideaLabel, shortId } from "../lib/rules";
import { dailySpark } from "../lib/spark";
import { useI18n } from "../lib/useI18n";

const sectionInfo: Record<DiscoverSection, { icon: IconName; label: MessageKey }> = {
  trending: { icon: "drop", label: "discover.trending" },
  branching: { icon: "branch", label: "discover.branching" },
  unexplored: { icon: "leaf", label: "discover.unexplored" },
  fresh: { icon: "spark", label: "discover.fresh" },
  deepest: { icon: "history", label: "discover.deepest" },
};
interface Props {
  version: string;
  stats: Stats | null;
  water: Record<number, number>;
  surprising: boolean;
  onSelect: (idea: Idea) => void;
  onPlant: (text: string) => void;
  onSurprise: () => void;
}
interface State {
  version: string;
  data: Discoveries | null;
  error: string;
}
function Pulse({ activity }: { activity: { day: string; ideas: number }[] }) {
  const { t, lang } = useI18n();
  const peak = Math.max(1, ...activity.map((d) => d.ideas)),
    total = activity.reduce((sum, d) => sum + d.ideas, 0);
  const format = new Intl.DateTimeFormat(lang, {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
  return (
    <section className="pulse-card">
      <div className="section-label">
        <span>{t("discover.pulse")}</span>
        <strong>{total}</strong>
      </div>
      <p className="small muted">{t("discover.pulseText")}</p>
      <div
        className="pulse-bars"
        role="img"
        aria-label={`${t("discover.pulseText")}: ${total}`}
      >
        {activity.map((day) => (
          <span
            key={day.day}
            title={t("discover.pulseDay", {
              day: format.format(new Date(`${day.day}T00:00:00Z`)),
              n: day.ideas,
            })}
            style={{ height: `${Math.max(6, (day.ideas / peak) * 100)}%` }}
            className={day.ideas ? "" : "empty"}
          />
        ))}
      </div>
    </section>
  );
}
export default function Discover({
  version,
  stats,
  water,
  surprising,
  onSelect,
  onPlant,
  onSurprise,
}: Props) {
  const { t, lang } = useI18n();
  const [state, setState] = useState<State>({
    version: "",
    data: null,
    error: "",
  });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    fetchDiscoveries(lang, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setState({ version, data, error: "" });
      })
      .catch((reason) => {
        if (!controller.signal.aborted)
          setState((previous) => ({
            version,
            data: previous.data,
            error:
              reason instanceof Error ? reason.message : t("discover.error"),
          }));
      });
    return () => controller.abort();
  }, [version, lang, attempt, t]);
  const spark = dailySpark(lang);
  const data = state.data;
  return (
    <div className="discover" aria-label={t("discover.label")} role="region">
      <div className="discover-hero">
        <section className="spark-card" aria-label={t("discover.sparkLabel")}>
          <span className="eyebrow">{t("discover.spark")}</span>
          <p className="spark-text">{spark}</p>
          <div className="spark-actions">
            <button className="button primary" onClick={() => onPlant(spark)}>
              <Icon name="spark" size={16} /> {t("discover.sparkPlant")}
            </button>
            <button
              className="button subtle"
              onClick={onSurprise}
              disabled={surprising}
            >
              {surprising ? (
                <span className="spinner" />
              ) : (
                <Icon name="dice" size={16} />
              )}
              {t("discover.surprise")}
            </button>
          </div>
        </section>
        {stats?.activity && stats.activity.length > 0 && (
          <Pulse activity={stats.activity} />
        )}
      </div>
      {state.error && (
        <div className="error-banner" role="alert">
          <span>{state.error}</span>
          <button
            className="text-button"
            onClick={() => setAttempt((n) => n + 1)}
          >
            {t("discover.retry")}
          </button>
        </div>
      )}
      {!data && !state.error && (
        <div className="empty-state">
          <span className="spinner" />
          <p>{t("discover.loading")}</p>
        </div>
      )}
      {data &&
        DISCOVER_SECTIONS.map((name) => (
          <section key={name} className="discover-section">
            <h2>
              <Icon name={sectionInfo[name].icon} size={17} />
              {t(sectionInfo[name].label)}
            </h2>
            {data[name].length ? (
              <ul className="discover-row">
                {data[name].map((idea) => (
                  <li key={idea.id}>
                    <button
                      className={`discover-card ${idea.mutation}`}
                      onClick={() => onSelect(idea)}
                    >
                      <span className="list-meta">
                        <span className={`tag ${idea.mutation}`}>
                          {ideaLabel(t, idea)}
                        </span>
                        <span>{shortId(idea.id)}</span>
                      </span>
                      <span className="discover-text">{idea.content}</span>
                      <span className="counters">
                        <span>
                          <Icon name="branch" size={14} /> {idea.children ?? 0}
                          <span className="sr-only">
                            {" "}
                            {t("inspector.branches")}
                          </span>
                        </span>
                        <span
                          className={
                            (water[idea.id] ?? idea.water ?? 0) ? "has-water" : ""
                          }
                        >
                          <Icon name="drop" size={14} />{" "}
                          {water[idea.id] ?? idea.water ?? 0}
                          <span className="sr-only">
                            {" "}
                            {t("inspector.water")}
                          </span>
                        </span>
                        <span>
                          {t("idea.depth")} {idea.depth}
                        </span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="small muted discover-empty">
                {t("discover.empty")}
              </p>
            )}
          </section>
        ))}
    </div>
  );
}
