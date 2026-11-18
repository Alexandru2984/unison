import { useEffect, useMemo, useState } from "react";
import Icon from "./Icon";
import { previewIdea, type PreviewRow } from "../lib/api";
import {
  mutations,
  wordCount,
  wordDiff,
  type Idea,
  type Mutation,
} from "../lib/ideas";
import { ideaLabel, ruleDescription, ruleName, shortId } from "../lib/rules";
import { starters } from "../lib/starters";
import { useI18n } from "../lib/useI18n";

const MAX_DEPTH = 32;
interface Props {
  selectedId: number | null;
  selected: Idea | null;
  parent: Idea | undefined;
  lineage: Idea[];
  loadedChildren: Idea[];
  branchCount: number;
  lineageError: string;
  saved: boolean;
  watered: boolean;
  waterTotal: number;
  watering: boolean;
  submitting: Mutation | null;
  tab: "detail" | "compare";
  epoch: number;
  onTab: (tab: "detail" | "compare") => void;
  onTransform: (mutation: Mutation) => void;
  onOpen: (idea: Idea) => void;
  onOpenId: (id: number) => void;
  onClose: () => void;
  onBookmark: (idea: Idea) => void;
  onWater: (idea: Idea) => void;
  onCopy: (idea: Idea) => void;
  onShare: (idea: Idea) => void;
  onCard: (idea: Idea) => void;
  onReport: (id: number) => void;
  onCustomBranch: () => void;
  onExportLineage: () => void;
  onStarter: (text: string) => void;
}
interface PreviewState {
  key: string;
  rows: Map<string, PreviewRow> | null;
}
/** Previews every rule for the selected idea; refreshed when its branches change. */
function usePreview(id: number | null, branches: number, epoch: number) {
  const { lang } = useI18n();
  const key = `${id}:${branches}:${epoch}`;
  const [state, setState] = useState<PreviewState>({ key: "", rows: null });
  useEffect(() => {
    if (id === null) return;
    const controller = new AbortController();
    previewIdea(id, lang, controller.signal)
      .then((rows) => {
        if (!controller.signal.aborted)
          setState({ key, rows: new Map(rows.map((r) => [r.mutation, r])) });
      })
      .catch(() => {
        if (!controller.signal.aborted) setState({ key, rows: null });
      });
    return () => controller.abort();
  }, [id, key, lang]);
  // Keep the last rows for the same idea while a refresh is in flight.
  const sameIdea = state.key.split(":")[0] === String(id);
  return {
    rows: sameIdea ? state.rows : null,
    loading: state.key !== key && !sameIdea,
  };
}

function Welcome({ onStarter }: { onStarter: (text: string) => void }) {
  const { t, lang } = useI18n();
  return (
    <>
      <div className="inspector-heading">
        <span className="eyebrow">{t("welcome.eyebrow")}</span>
        <Icon name="spark" size={16} />
      </div>
      <div className="inspector-welcome">
        <div className="garden-art" aria-hidden="true">
          <span />
          <span />
          <span />
          <span />
          <span />
          <Icon name="spark" size={26} />
        </div>
        <span className="eyebrow">{t("welcome.kicker")}</span>
        <h2>{t("welcome.title")}</h2>
        <p>{t("welcome.text")}</p>
      </div>
      <ol className="how-steps">
        {(["1", "2", "3"] as const).map((step) => (
          <li key={step}>
            <span>0{step}</span>
            <p>
              <strong>{t(`welcome.step${step}`)}</strong>
              {t(`welcome.step${step}Text`)}
            </p>
          </li>
        ))}
      </ol>
      <section className="starter-section">
        <div className="section-label">{t("welcome.starters")}</div>
        {starters.map((starter) => (
          <button key={starter.key} onClick={() => onStarter(starter.text[lang])}>
            <span>
              <small>{t(starter.key)}</small>
              <strong>{starter.text[lang]}</strong>
            </span>
            <Icon name="plus" size={16} />
          </button>
        ))}
      </section>
      <p className="engine-note">{t("welcome.engine")}</p>
    </>
  );
}

export default function Inspector(props: Props) {
  const { t } = useI18n();
  const {
    selected,
    selectedId,
    parent,
    lineage,
    loadedChildren,
    branchCount,
    lineageError,
    submitting,
    tab,
  } = props;
  const preview = usePreview(selected?.id ?? null, branchCount, props.epoch);
  const diff = useMemo(
    () =>
      parent && selected ? wordDiff(parent.content, selected.content) : null,
    [parent, selected],
  );
  if (!selected)
    return (
      <aside
        className={`inspector ${selectedId !== null ? "has-selection" : ""}`}
        aria-label={t("inspector.label")}
      >
        {selectedId !== null ? (
          <div className="inspector-welcome">
            <Icon name="search" size={28} />
            <h2>
              {lineageError
                ? t("inspector.outOfReach")
                : t("inspector.opening")}
            </h2>
            <p>{lineageError || t("inspector.tracing")}</p>
            <button className="button subtle" onClick={props.onClose}>
              {t("inspector.back")}
            </button>
          </div>
        ) : (
          <Welcome onStarter={props.onStarter} />
        )}
      </aside>
    );
  const atLimit = selected.depth >= MAX_DEPTH,
    words = wordCount(selected.content);
  const delta = parent ? words - wordCount(parent.content) : 0;
  return (
    <aside
      className="inspector has-selection"
      aria-label={t("inspector.label")}
    >
      <div className="sheet-handle" aria-hidden="true" />
      <div className="inspector-heading">
        <span className="eyebrow">{t("inspector.eyebrow")}</span>
        <button
          className="icon-button"
          onClick={props.onClose}
          aria-label={t("inspector.close")}
        >
          <Icon name="close" size={18} />
        </button>
      </div>
      <div className="selected-title">
        <span className={`tag ${selected.mutation}`}>
          {ideaLabel(t, selected)}
        </span>
        <span className="mono">{shortId(selected.id)}</span>
      </div>
      <h2>{t("inspector.heading")}</h2>
      <div
        className="inspector-tabs"
        role="group"
        aria-label={t("inspector.tabs")}
      >
        <button
          aria-pressed={tab === "detail"}
          onClick={() => props.onTab("detail")}
        >
          {t("inspector.overview")}
        </button>
        <button
          aria-pressed={tab === "compare"}
          disabled={!parent}
          onClick={() => props.onTab("compare")}
        >
          {t("inspector.compare")}
        </button>
      </div>
      {tab === "compare" && diff && parent ? (
        <div className="comparison">
          <div>
            <span className="eyebrow">
              {t("inspector.parent", { id: parent.id })}
            </span>
            <p>
              {diff.before.map((token, i) =>
                token.changed ? <del key={i}>{token.text}</del> : token.text,
              )}
            </p>
          </div>
          <div>
            <span className="eyebrow">
              {t("inspector.current", { id: selected.id })}
            </span>
            <p>
              {diff.after.map((token, i) =>
                token.changed ? <mark key={i}>{token.text}</mark> : token.text,
              )}
            </p>
          </div>
          {diff.truncated && (
            <p className="small muted">{t("inspector.truncated")}</p>
          )}
          <p className="small muted">
            {t("inspector.wordDelta", {
              n: `${delta >= 0 ? "+" : ""}${delta}`,
            })}
          </p>
        </div>
      ) : (
        <>
          <p className="selected-content">{selected.content}</p>
          <div className="idea-metrics">
            <span>
              <strong>{words}</strong> {t("inspector.words")}
            </span>
            <span>
              <strong>{selected.depth}</strong> {t("inspector.depth")}
            </span>
            <span>
              <strong>{branchCount}</strong> {t("inspector.branches")}
            </span>
            <span>
              <strong>{props.waterTotal}</strong> {t("inspector.water")}
            </span>
          </div>
          <div className="detail-actions">
            <button
              className={`button water-button ${props.watered ? "is-watered" : ""}`}
              aria-pressed={props.watered}
              disabled={props.watering}
              title={t("inspector.waterLabel")}
              onClick={() => props.onWater(selected)}
            >
              <Icon name="drop" size={16} />
              {props.watered
                ? t("inspector.watered")
                : t("inspector.waterAction")}
              <span className="water-count" key={props.waterTotal}>
                {props.waterTotal}
              </span>
            </button>
            <button
              className={`button subtle ${props.saved ? "is-saved" : ""}`}
              aria-pressed={props.saved}
              onClick={() => props.onBookmark(selected)}
            >
              <Icon name="star" size={16} />
              {props.saved ? t("inspector.saved") : t("inspector.save")}
            </button>
            <span className="action-icons">
              <button
                className="icon-button"
                onClick={() => props.onCopy(selected)}
                aria-label={t("inspector.copy")}
                title={t("inspector.copy")}
              >
                <Icon name="copy" size={17} />
              </button>
              <button
                className="icon-button"
                onClick={() => props.onShare(selected)}
                aria-label={t("inspector.share")}
                title={t("inspector.share")}
              >
                <Icon name="share" size={17} />
              </button>
              <button
                className="icon-button"
                onClick={() => props.onCard(selected)}
                aria-label={t("inspector.card")}
                title={t("inspector.card")}
              >
                <Icon name="image" size={17} />
              </button>
            </span>
          </div>
        </>
      )}
      <button
        className="text-button report-link"
        onClick={() => props.onReport(selected.id)}
      >
        <Icon name="flag" size={14} /> {t("inspector.report")}
      </button>
      {lineageError && (
        <p className="small error-text" role="alert">
          {lineageError}
        </p>
      )}
      <section className="transform-section">
        <div className="section-label">
          <span>{t("inspector.transformTitle")}</span>
          <Icon name="spark" size={14} />
        </div>
        <p className="small muted">{t("inspector.transformLead")}</p>
        <div className="transforms">
          {mutations.map((m) => {
            const row = preview.rows?.get(m.id);
            const existing = row?.existing_id ?? null,
              unchanged = !!row?.unchanged && existing === null;
            return (
              <button
                key={m.id}
                className={`transform-button ${m.id} ${existing !== null ? "exists" : ""}`}
                disabled={
                  submitting !== null || (atLimit && existing === null) || unchanged
                }
                onClick={() =>
                  existing !== null ? props.onOpenId(existing) : props.onTransform(m.id)
                }
              >
                <span className="transform-symbol" aria-hidden="true">
                  {submitting === m.id ? <span className="spinner" /> : m.symbol}
                </span>
                <span className="transform-copy">
                  <strong>{ruleName(t, m.id)}</strong>
                  {row?.content && !unchanged ? (
                    <q className="transform-preview">{row.content}</q>
                  ) : (
                    <small>
                      {unchanged
                        ? t("inspector.previewUnchanged")
                        : preview.loading
                          ? t("inspector.previewLoading")
                          : ruleDescription(t, m.id)}
                    </small>
                  )}
                  {existing !== null && (
                    <small className="exists-note">
                      <Icon name="check" size={12} />{" "}
                      {t("inspector.previewExisting")}
                    </small>
                  )}
                </span>
                <Icon name="chevron" size={15} />
              </button>
            );
          })}
        </div>
        <button
          className="button subtle full custom-branch"
          disabled={submitting !== null || atLimit}
          onClick={props.onCustomBranch}
        >
          <Icon name="branch" size={15} /> {t("inspector.custom")}
        </button>
        {atLimit && <p className="small muted">{t("inspector.depthLimit")}</p>}
        <p className="small muted keyboard-tip">{t("inspector.keyboard")}</p>
      </section>
      {lineage.length > 1 && (
        <section className="lineage-section">
          <div className="section-label">{t("inspector.path")}</div>
          <ol>
            {lineage.map((idea) => (
              <li key={idea.id}>
                <button
                  className={idea.id === selected.id ? "current" : ""}
                  aria-current={idea.id === selected.id ? "true" : undefined}
                  onClick={() => props.onOpen(idea)}
                >
                  <span className={`lineage-dot ${idea.mutation}`} />
                  <span>
                    <strong>
                      #{idea.id} · {ideaLabel(t, idea)}
                    </strong>
                    <small>{idea.content}</small>
                  </span>
                </button>
              </li>
            ))}
          </ol>
          <button className="text-button" onClick={props.onExportLineage}>
            <Icon name="download" size={14} /> {t("inspector.exportPath")}
          </button>
        </section>
      )}
      {loadedChildren.length > 0 && (
        <section className="children-section">
          <div className="section-label">
            {t("inspector.children", { n: loadedChildren.length })}
          </div>
          {loadedChildren.slice(0, 12).map((child) => (
            <button
              key={child.id}
              className="child-link"
              onClick={() => props.onOpen(child)}
            >
              <span className={`lineage-dot ${child.mutation}`} />
              <span>
                <strong>
                  #{child.id} · {ideaLabel(t, child)}
                </strong>
                <small>{child.content}</small>
              </span>
              <Icon name="arrow" size={14} />
            </button>
          ))}
        </section>
      )}
    </aside>
  );
}
