import { lazy, Suspense, useEffect, useMemo, useState } from "react";
import Icon from "./Icon";
import type { Idea } from "../lib/ideas";
import { useI18n } from "../lib/useI18n";

const IdeaGraph = lazy(() => import("./IdeaGraph"));
interface Props {
  ideas: Idea[];
  selectedId: number | null;
  bookmarks: number[];
  water: Record<number, number>;
  branches: (idea: Idea) => number;
  fresh: number | null;
  theme: string;
  canFocus: boolean;
  focusPath: boolean;
  onFocusPath: () => void;
  onSelect: (idea: Idea) => void;
  onBookmark: (idea: Idea) => void;
}
export default function GraphView(props: Props) {
  const { t } = useI18n();
  const [horizontal, setHorizontal] = useState(false);
  // Replay shows the garden growing in creation order, one idea per step.
  const [replay, setReplay] = useState<number | null>(null),
    [playing, setPlaying] = useState(false);
  const ordered = useMemo(
    () => props.ideas.slice().sort((a, b) => a.id - b.id),
    [props.ideas],
  );
  const total = ordered.length,
    position = replay === null ? total : Math.min(Math.max(1, replay), total);
  const visible = useMemo(
    () => (replay === null ? props.ideas : ordered.slice(0, position)),
    [replay, props.ideas, ordered, position],
  );
  // Reaching the newest idea ends playback without another state update.
  const running = playing && replay !== null && position < total;
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(
      () => setReplay((current) => Math.min((current ?? 0) + 1, total)),
      650,
    );
    return () => clearInterval(timer);
  }, [running, total]);
  const startReplay = () => {
    if (running) return setPlaying(false);
    setReplay((current) =>
      current === null || current >= total ? 1 : current,
    );
    setPlaying(true);
  };
  return (
    <>
      <Suspense
        fallback={
          <div className="empty-state">
            <span className="spinner" />
            <p>{t("loading.graph")}</p>
          </div>
        }
      >
        <IdeaGraph
          ideas={visible}
          selectedId={props.selectedId}
          bookmarks={props.bookmarks}
          water={props.water}
          branches={props.branches}
          fresh={props.fresh}
          horizontal={horizontal}
          theme={props.theme}
          onSelect={props.onSelect}
          onBookmark={props.onBookmark}
        />
      </Suspense>
      <div className="canvas-tools">
        <button className="canvas-chip" onClick={() => setHorizontal((h) => !h)}>
          <Icon name="graph" size={15} />
          {horizontal ? t("graph.horizontal") : t("graph.vertical")}
        </button>
        {props.canFocus && (
          <button
            className={`canvas-chip ${props.focusPath ? "active" : ""}`}
            aria-pressed={props.focusPath}
            onClick={props.onFocusPath}
          >
            <Icon name="focus" size={15} />
            {props.focusPath ? t("graph.showAll") : t("graph.focus")}
          </button>
        )}
        {total > 1 && (
          <button
            className={`canvas-chip ${replay !== null ? "active" : ""}`}
            aria-pressed={running}
            onClick={startReplay}
          >
            <Icon name={running ? "pause" : "play"} size={15} />
            {running ? t("graph.pause") : t("graph.replay")}
          </button>
        )}
        {replay !== null && (
          <span className="replay-control">
            <input
              type="range"
              min={1}
              max={total}
              value={position}
              aria-label={t("graph.position")}
              aria-valuetext={`${position} / ${total}`}
              onChange={(event) => {
                setPlaying(false);
                setReplay(Number(event.target.value));
              }}
            />
            <span className="mono">
              {position}/{total}
            </span>
            <button
              className="icon-button tiny"
              aria-label={t("graph.showAll")}
              onClick={() => {
                setPlaying(false);
                setReplay(null);
              }}
            >
              <Icon name="close" size={14} />
            </button>
          </span>
        )}
      </div>
    </>
  );
}
