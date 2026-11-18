import { useEffect, useRef, useState, type FormEvent } from "react";
import Icon from "./Icon";
import { apiError } from "../lib/ideas";
import { useI18n } from "../lib/useI18n";
const reasons = ["spam", "harassment", "privacy", "unsafe", "other"] as const;
export default function ReportDialog({
  ideaId,
  onClose,
}: {
  ideaId: number;
  onClose: () => void;
}) {
  const { t, lang } = useI18n();
  const dialog = useRef<HTMLDialogElement>(null),
    controller = useRef<AbortController | null>(null),
    locked = useRef(false);
  const [reason, setReason] = useState(""),
    [busy, setBusy] = useState(false),
    [sent, setSent] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => {
      controller.current?.abort();
      element?.close();
    };
  }, []);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!reason || locked.current) return;
    locked.current = true;
    setBusy(true);
    setError("");
    const request = new AbortController();
    controller.current = request;
    try {
      const response = await fetch(`/api/idea/${ideaId}/report`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reason }),
        signal: AbortSignal.any([request.signal, AbortSignal.timeout(10_000)]),
      });
      if (!response.ok) throw new Error(await apiError(response, lang));
      if (!request.signal.aborted) setSent(true);
    } catch (failure) {
      if (!request.signal.aborted)
        setError(
          failure instanceof Error && failure.name !== "TimeoutError"
            ? failure.message
            : t("report.failed"),
        );
    } finally {
      locked.current = false;
      if (!request.signal.aborted) setBusy(false);
    }
  }
  return (
    <dialog
      ref={dialog}
      className="help-dialog report-dialog"
      aria-labelledby="report-title"
      onCancel={onClose}
    >
      <div className="dialog-heading">
        <span className="eyebrow">{t("report.eyebrow")}</span>
        <button
          className="icon-button"
          onClick={onClose}
          aria-label={t("report.close")}
        >
          <Icon name="close" />
        </button>
      </div>
      <h2 id="report-title">
        {sent ? t("report.received") : t("report.title", { id: ideaId })}
      </h2>
      {sent ? (
        <>
          <p role="status">{t("report.thanks")}</p>
          <button className="button primary full" onClick={onClose} autoFocus>
            {t("report.done")}
          </button>
        </>
      ) : (
        <form onSubmit={(event) => void submit(event)}>
          <fieldset disabled={busy}>
            <legend>{t("report.why")}</legend>
            {reasons.map((item) => (
              <label className="report-option" key={item}>
                <input
                  type="radio"
                  name="reason"
                  value={item}
                  checked={reason === item}
                  onChange={() => setReason(item)}
                />
                <span>{t(`report.${item}`)}</span>
              </label>
            ))}
          </fieldset>
          <p className="privacy-note">{t("report.note")}</p>
          {error && (
            <p role="alert" className="error-text small">
              {error}
            </p>
          )}
          <div className="report-actions">
            <button className="button subtle" type="button" onClick={onClose}>
              {t("report.cancel")}
            </button>
            <button
              className="button primary"
              type="submit"
              disabled={!reason || busy}
            >
              {busy ? (
                <>
                  <span className="spinner" /> {t("report.sending")}
                </>
              ) : (
                t("report.send")
              )}
            </button>
          </div>
        </form>
      )}
    </dialog>
  );
}
