import type { RefObject } from "react";
import Icon from "./Icon";
import { mutations } from "../lib/ideas";
import { ruleDescription, ruleName } from "../lib/rules";
import { useI18n } from "../lib/useI18n";

export default function HelpDialog({
  ref,
}: {
  ref: RefObject<HTMLDialogElement | null>;
}) {
  const { t } = useI18n();
  const close = () => ref.current?.close();
  return (
    <dialog ref={ref} className="help-dialog" aria-labelledby="help-title">
      <div className="dialog-heading">
        <span className="eyebrow">{t("help.eyebrow")}</span>
        <button
          className="icon-button"
          aria-label={t("help.close")}
          onClick={close}
        >
          <Icon name="close" />
        </button>
      </div>
      <h2 id="help-title">{t("help.title")}</h2>
      <p>{t("help.intro")}</p>
      <div className="help-rules">
        {mutations.map((m) => (
          <div key={m.id} className={m.id}>
            <span className="transform-symbol" aria-hidden="true">
              {m.symbol}
            </span>
            <p>
              <strong>{ruleName(t, m.id)}</strong>
              {ruleDescription(t, m.id)}
            </p>
          </div>
        ))}
      </div>
      <p className="small muted">{t("help.english")}</p>
      <p>{t("help.more")}</p>
      <div className="shortcut-list">
        <span>
          <kbd>/</kbd> {t("help.search")}
        </span>
        <span>
          <kbd>N</kbd> {t("help.new")}
        </span>
        <span>
          <kbd>R</kbd> {t("help.random")}
        </span>
        <span>
          <kbd>↑ ↓ ← →</kbd> {t("help.navigate")}
        </span>
        <span>
          <kbd>Esc</kbd> {t("help.clear")}
        </span>
        <span>
          <kbd>Ctrl / ⌘ + Enter</kbd> {t("help.publish")}
        </span>
      </div>
      <p className="privacy-note">{t("help.privacy")}</p>
      <button className="button primary" onClick={close}>
        {t("help.go")} <Icon name="arrow" size={16} />
      </button>
    </dialog>
  );
}
