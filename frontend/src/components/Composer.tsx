import { useRef, useState, type FormEvent, type RefObject } from "react";
import Icon from "./Icon";
import { previewDraft, type PreviewRow } from "../lib/api";
import { mutations } from "../lib/ideas";
import { ruleName } from "../lib/rules";
import { starters } from "../lib/starters";
import { useI18n } from "../lib/useI18n";

interface Props {
  draft: string;
  onDraft: (text: string) => void;
  branchFrom: number | null;
  planting: boolean;
  disabled: boolean;
  storageAvailable: boolean;
  composerRef: RefObject<HTMLTextAreaElement | null>;
  onSubmit: (event: FormEvent) => void;
  onCancelBranch: () => void;
  onStarter: (text: string) => void;
}
interface PreviewState {
  text: string;
  rows: PreviewRow[];
  error: string;
}
const symbols = new Map(mutations.map((m) => [m.id as string, m.symbol]));

export default function Composer({
  draft,
  onDraft,
  branchFrom,
  planting,
  disabled,
  storageAvailable,
  composerRef,
  onSubmit,
  onCancelBranch,
  onStarter,
}: Props) {
  const { t, lang } = useI18n();
  const [preview, setPreview] = useState<PreviewState | null>(null),
    [previewing, setPreviewing] = useState(false);
  const request = useRef<AbortController | null>(null);
  const text = draft.trim();
  // A preview belongs to the exact text it was computed for.
  const shown = preview && preview.text === text ? preview : null;

  async function runPreview() {
    if (!text || previewing) return;
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setPreviewing(true);
    try {
      const rows = await previewDraft(
        text,
        lang,
        AbortSignal.any([controller.signal, AbortSignal.timeout(15_000)]),
      );
      if (!controller.signal.aborted) setPreview({ text, rows, error: "" });
    } catch (reason) {
      if (!controller.signal.aborted)
        setPreview({
          text,
          rows: [],
          error:
            reason instanceof Error && reason.name !== "TimeoutError"
              ? reason.message
              : t("inspector.previewUnavailable"),
        });
    } finally {
      if (request.current === controller) setPreviewing(false);
    }
  }

  return (
    <form className="composer" onSubmit={onSubmit}>
      <div className="composer-heading">
        <span className="composer-icon">
          <Icon name={branchFrom !== null ? "branch" : "spark"} />
        </span>
        <div>
          <h2>
            {branchFrom !== null
              ? t("composer.branchTitle")
              : t("composer.title")}
          </h2>
          <p>
            {branchFrom !== null
              ? t("composer.branchSubtitle", { id: branchFrom })
              : t("composer.subtitle")}
          </p>
        </div>
      </div>
      <label className="sr-only" htmlFor="idea-draft">
        {t("composer.label")}
      </label>
      <textarea
        id="idea-draft"
        ref={composerRef}
        value={draft}
        maxLength={2000}
        rows={4}
        onChange={(event) => onDraft(event.target.value)}
        placeholder={t("composer.placeholder")}
        onKeyDown={(event) => {
          if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
            event.preventDefault();
            event.currentTarget.form?.requestSubmit();
          }
        }}
      />
      <div className="composer-meta">
        <span>
          {storageAvailable
            ? t("composer.draftLocal")
            : t("composer.noStorage")}
        </span>
        <span>{draft.length}/2000</span>
      </div>
      <button
        className="button primary full"
        type="submit"
        disabled={!text || disabled}
      >
        {planting ? (
          <>
            <span className="spinner" /> {t("composer.planting")}
          </>
        ) : (
          <>
            {t("composer.plant")} <Icon name="arrow" size={17} />
          </>
        )}
      </button>
      {branchFrom === null && (
        <button
          type="button"
          className="button subtle full"
          disabled={!text || previewing}
          aria-expanded={!!shown}
          aria-controls="draft-preview"
          onClick={() => (shown ? setPreview(null) : void runPreview())}
        >
          {previewing ? (
            <>
              <span className="spinner" /> {t("composer.previewing")}
            </>
          ) : (
            <>
              <Icon name="eye" size={16} />
              {shown ? t("composer.previewHide") : t("composer.preview")}
            </>
          )}
        </button>
      )}
      {shown && (
        <section
          id="draft-preview"
          className="draft-preview"
          aria-live="polite"
          aria-label={t("composer.previewTitle")}
        >
          <div className="section-label">
            <span>{t("composer.previewTitle")}</span>
          </div>
          {shown.error ? (
            <p className="error-text small" role="alert">
              {shown.error}
            </p>
          ) : (
            <ul>
              {shown.rows.map((row) => (
                <li key={row.mutation} className={row.mutation}>
                  <span className="transform-symbol" aria-hidden="true">
                    {symbols.get(row.mutation) ?? "•"}
                  </span>
                  <span>
                    <strong>{ruleName(t, row.mutation)}</strong>
                    <span className={row.unchanged ? "muted" : ""}>
                      {row.content === null
                        ? t("inspector.previewUnavailable")
                        : row.unchanged
                          ? t("inspector.previewUnchanged")
                          : row.content}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          )}
          <p className="small muted">{t("composer.previewNote")}</p>
        </section>
      )}
      {branchFrom !== null && (
        <button type="button" className="text-button" onClick={onCancelBranch}>
          {t("composer.separate")}
        </button>
      )}
      <details className="composer-starters">
        <summary>{t("composer.starters")}</summary>
        {starters.map((starter) => (
          <button
            type="button"
            key={starter.key}
            onClick={() => onStarter(starter.text[lang])}
          >
            {t(starter.key)}
            <Icon name="arrow" size={13} />
          </button>
        ))}
      </details>
      <p className="privacy-note">
        <Icon name="lock" size={13} /> {t("composer.privacy")}
      </p>
    </form>
  );
}
