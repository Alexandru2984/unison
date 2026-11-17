import { useEffect, useRef, useState, type FormEvent } from "react";
import Icon from "./Icon";
import { apiError } from "../lib/ideas";
const reasons = [
  { id: "spam", name: "Spam or advertising" },
  { id: "harassment", name: "Harassment or hateful content" },
  { id: "privacy", name: "Personal or confidential information" },
  { id: "unsafe", name: "Dangerous or harmful content" },
  { id: "other", name: "Another concern" },
];
export default function ReportDialog({
  ideaId,
  onClose,
}: {
  ideaId: number;
  onClose: () => void;
}) {
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
      if (!response.ok) throw new Error(await apiError(response));
      if (!request.signal.aborted) setSent(true);
    } catch (failure) {
      if (!request.signal.aborted)
        setError(
          failure instanceof Error && failure.name !== "TimeoutError"
            ? failure.message
            : "The report could not be sent. Please try again.",
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
      <div className="inspector-heading">
        <span className="eyebrow">KEEP THE GARDEN WELCOMING</span>
        <button
          className="icon-button"
          onClick={onClose}
          aria-label="Close report"
        >
          <Icon name="close" />
        </button>
      </div>
      <h2 id="report-title">
        {sent ? "Report received." : `Report idea #${ideaId}`}
      </h2>
      {sent ? (
        <>
          <p role="status">
            Thank you. Your report is in the private review queue. The site
            operator reviews reports before taking action.
          </p>
          <button className="button primary full" onClick={onClose} autoFocus>
            Done
          </button>
        </>
      ) : (
        <form onSubmit={(event) => void submit(event)}>
          <fieldset disabled={busy}>
            <legend>Why are you reporting this idea?</legend>
            {reasons.map((item) => (
              <label className="report-option" key={item.id}>
                <input
                  type="radio"
                  name="reason"
                  value={item.id}
                  checked={reason === item.id}
                  onChange={() => setReason(item.id)}
                />
                <span>{item.name}</span>
              </label>
            ))}
          </fieldset>
          <p className="privacy-note">
            Reports are private. The report record contains the idea ID, your
            selected reason and submission time. Repeated reports do not
            automatically remove an idea.
          </p>
          {error && (
            <p role="alert" className="error-text small">
              {error}
            </p>
          )}
          <div className="report-actions">
            <button className="button subtle" type="button" onClick={onClose}>
              Cancel
            </button>
            <button
              className="button primary"
              type="submit"
              disabled={!reason || busy}
            >
              {busy ? (
                <>
                  <span className="spinner" /> Sending…
                </>
              ) : (
                "Send report"
              )}
            </button>
          </div>
        </form>
      )}
    </dialog>
  );
}
