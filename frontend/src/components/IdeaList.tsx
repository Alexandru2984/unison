import { useEffect, useRef } from "react";
import Icon from "./Icon";
import { highlight, type Idea } from "../lib/ideas";
import { ideaLabel, shortId } from "../lib/rules";
import { useI18n } from "../lib/useI18n";

interface Props {
  ideas: Idea[];
  selectedId: number | null;
  bookmarks: number[];
  water: Record<number, number>;
  branches: (idea: Idea) => number;
  query: string;
  fresh: number | null;
  hasMore: boolean;
  moreBusy: boolean;
  onLoadMore: () => void;
  onSelect: (idea: Idea) => void;
  onBookmark: (idea: Idea) => void;
}
export default function IdeaList({
  ideas,
  selectedId,
  bookmarks,
  water,
  branches,
  query,
  fresh,
  hasMore,
  moreBusy,
  onLoadMore,
  onSelect,
  onBookmark,
}: Props) {
  const { t, lang } = useI18n();
  const sentinel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const target = sentinel.current;
    if (!target || !hasMore || typeof IntersectionObserver === "undefined")
      return;
    // Older pages load as the reader approaches the end of the list.
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) onLoadMore();
      },
      { rootMargin: "400px 0px" },
    );
    observer.observe(target);
    return () => observer.disconnect();
  }, [hasMore, onLoadMore]);
  const dateFormat = new Intl.DateTimeFormat(lang, {
    month: "short",
    day: "numeric",
  });
  return (
    <div className="idea-list">
      {ideas
        .slice()
        .reverse()
        .map((idea) => {
          const saved = bookmarks.includes(idea.id),
            count = branches(idea),
            drops = water[idea.id] ?? idea.water ?? 0;
          return (
            <article
              key={idea.id}
              className={`idea-list-card ${idea.mutation} ${idea.id === selectedId ? "selected" : ""} ${idea.id === fresh ? "just-planted" : ""}`}
            >
              <button
                className="list-idea-content"
                onClick={() => onSelect(idea)}
              >
                <span className="list-meta">
                  <span className={`tag ${idea.mutation}`}>
                    {ideaLabel(t, idea)}
                  </span>
                  <span>
                    {shortId(idea.id)} · {t("idea.depth")} {idea.depth}
                  </span>
                </span>
                <p>
                  {highlight(idea.content, query).map((part, index) =>
                    part.match ? (
                      <mark key={index}>{part.text}</mark>
                    ) : (
                      part.text
                    ),
                  )}
                </p>
                <span className="list-bottom">
                  <span>
                    {idea.created_at
                      ? dateFormat.format(new Date(idea.created_at))
                      : t("idea.earlier")}
                  </span>
                  <span className="counters">
                    <span>
                      <Icon name="branch" size={14} /> {count}
                      <span className="sr-only">
                        {" "}
                        {t("inspector.branches")}
                      </span>
                    </span>
                    <span className={drops ? "has-water" : ""}>
                      <Icon name="drop" size={14} /> {drops}
                      <span className="sr-only"> {t("inspector.water")}</span>
                    </span>
                  </span>
                  <span className="explore">
                    {t("idea.explore")} <Icon name="arrow" size={14} />
                  </span>
                </span>
              </button>
              <button
                className={`icon-button list-save ${saved ? "is-saved" : ""}`}
                aria-label={
                  saved
                    ? t("idea.unsave", { id: idea.id })
                    : t("idea.save", { id: idea.id })
                }
                aria-pressed={saved}
                onClick={() => onBookmark(idea)}
              >
                <Icon name="star" size={18} />
              </button>
            </article>
          );
        })}
      <div ref={sentinel} className="list-sentinel" aria-hidden="true" />
      {hasMore ? (
        moreBusy && (
          <p className="list-status" role="status">
            <span className="spinner" /> {t("list.loadingMore")}
          </p>
        )
      ) : ideas.length > 12 ? (
        <p className="list-status muted">{t("list.end")}</p>
      ) : null}
    </div>
  );
}
