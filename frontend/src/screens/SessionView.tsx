import { useState, type FormEvent } from "react";

import { submitFeedback, type ApiFailure, type SessionPlan } from "../api/sessions";
import { formatDuration, formatSignedDuration } from "../format";
import { ErrorNotice } from "./ErrorNotice";

const NOTE_MAX = 1000; // openapi.yaml: FeedbackRequest.note.maxLength

function FeedbackForm({ sessionId }: { sessionId: string }) {
  const [rating, setRating] = useState<"up" | "down" | null>(null);
  const [note, setNote] = useState("");
  const [pending, setPending] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<ApiFailure | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (rating === null) return;
    setPending(true);
    setError(null);
    const result = await submitFeedback(sessionId, { rating, note: note.trim() || null });
    setPending(false);
    if (result.ok) setSent(true);
    else setError(result.error);
  }

  if (sent) {
    return (
      <p role="status" className="notice notice--ok">
        Thanks, your feedback was recorded.
      </p>
    );
  }

  return (
    <form onSubmit={handleSubmit} aria-busy={pending}>
      <h3>How was this session?</h3>
      <fieldset>
        <legend>Rating</legend>
        <label>
          <input
            type="radio"
            name="rating"
            value="up"
            checked={rating === "up"}
            onChange={() => setRating("up")}
          />{" "}
          Good
        </label>
        <label>
          <input
            type="radio"
            name="rating"
            value="down"
            checked={rating === "down"}
            onChange={() => setRating("down")}
          />{" "}
          Not good
        </label>
      </fieldset>
      <div className="field">
        <label htmlFor="note">Note (optional)</label>
        <textarea
          id="note"
          rows={3}
          maxLength={NOTE_MAX}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
      </div>
      <button type="submit" disabled={pending || rating === null}>
        {pending ? "Sending..." : "Send feedback"}
      </button>
      {error && <ErrorNotice error={error} />}
    </form>
  );
}

export function SessionView({ plan, onRestart }: { plan: SessionPlan; onRestart: () => void }) {
  const total = plan.segments.reduce((sum, segment) => sum + segment.duration_s, 0);
  const segments = [...plan.segments].sort((a, b) => a.order - b.order);

  return (
    <div>
      <h2>Your session</h2>
      <p>
        {plan.level} / {plan.goal} / target {plan.duration_min} min
      </p>
      <p>
        Verdict:{" "}
        <strong className={`verdict verdict--${plan.verdict}`}>{plan.verdict}</strong>
      </p>

      {plan.warnings.length > 0 && (
        <div role="note" className="notice notice--warn">
          <strong>Warnings</strong>
          <ul>
            {plan.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      )}

      <table>
        <caption>
          Total duration {formatDuration(total)} ({formatSignedDuration(plan.duration_gap_s)} against
          the target)
        </caption>
        <thead>
          <tr>
            <th scope="col">#</th>
            <th scope="col">Role</th>
            <th scope="col">Zone</th>
            <th scope="col">Track</th>
            <th scope="col">BPM</th>
            <th scope="col">Confidence</th>
            <th scope="col">Duration</th>
          </tr>
        </thead>
        <tbody>
          {segments.map((segment) => (
            <tr key={segment.order}>
              <td>{segment.order + 1}</td>
              <td>{segment.role}</td>
              <td>{segment.zone}</td>
              <td>
                {segment.track.title} <span className="muted">{segment.track.artist}</span>
              </td>
              <td>{segment.track.bpm_effective == null ? "-" : Math.round(segment.track.bpm_effective)}</td>
              <td>{segment.track.confidence ?? "-"}</td>
              <td>{formatDuration(segment.duration_s)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <FeedbackForm sessionId={plan.session_id} />

      <p>
        <button type="button" className="secondary" onClick={onRestart}>
          Plan another session
        </button>
      </p>
    </div>
  );
}
