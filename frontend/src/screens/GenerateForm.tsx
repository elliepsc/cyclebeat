import { useState, type FormEvent } from "react";

import {
  generateSession,
  type ApiFailure,
  type Goal,
  type Level,
  type SessionPlan,
} from "../api/sessions";
import { useSlowNotice } from "../useSlowNotice";
import { ErrorNotice } from "./ErrorNotice";

// openapi.yaml: GenerateSessionRequest.duration_min. A test compares these to the contract.
export const DURATION_MIN = 20;
export const DURATION_MAX = 120;

// Record<...> keeps these exhaustive: a new enum value in the contract fails the type check.
const LEVEL_LABELS: Record<Level, string> = {
  beginner: "Beginner",
  intermediate: "Intermediate",
  advanced: "Advanced",
};
const GOAL_LABELS: Record<Goal, string> = {
  endurance: "Endurance",
  intervals: "Intervals",
  recovery: "Recovery",
};

export function GenerateForm({ onGenerated }: { onGenerated: (plan: SessionPlan) => void }) {
  const [level, setLevel] = useState<Level>("beginner");
  const [goal, setGoal] = useState<Goal>("endurance");
  const [duration, setDuration] = useState(DURATION_MIN + 10);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<ApiFailure | null>(null);
  const slow = useSlowNotice(pending);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const result = await generateSession({
      source: { type: "demo", value: "" },
      level,
      goal,
      duration_min: duration,
    });
    setPending(false);
    if (result.ok) onGenerated(result.data);
    else setError(result.error);
  }

  return (
    <form onSubmit={handleSubmit} aria-busy={pending}>
      <h2>Plan a session</h2>
      <p className="hint">Tracks come from the demo catalogue.</p>

      <div className="field">
        <label htmlFor="level">Level</label>
        <select id="level" value={level} onChange={(e) => setLevel(e.target.value as Level)}>
          {(Object.keys(LEVEL_LABELS) as Level[]).map((value) => (
            <option key={value} value={value}>
              {LEVEL_LABELS[value]}
            </option>
          ))}
        </select>
      </div>

      <div className="field">
        <label htmlFor="goal">Goal</label>
        <select id="goal" value={goal} onChange={(e) => setGoal(e.target.value as Goal)}>
          {(Object.keys(GOAL_LABELS) as Goal[]).map((value) => (
            <option key={value} value={value}>
              {GOAL_LABELS[value]}
            </option>
          ))}
        </select>
      </div>

      <div className="field">
        <label htmlFor="duration">
          Duration (minutes, {DURATION_MIN} to {DURATION_MAX})
        </label>
        <input
          id="duration"
          type="number"
          min={DURATION_MIN}
          max={DURATION_MAX}
          step={1}
          required
          value={duration}
          onChange={(e) => setDuration(Number(e.target.value))}
        />
      </div>

      <button type="submit" disabled={pending}>
        {pending ? "Generating..." : "Generate session"}
      </button>

      {pending && (
        <p role="status" className="notice notice--info">
          {slow
            ? "The API is waking up. The free server sleeps when idle, so the first request can take up to a minute."
            : "Building your session..."}
        </p>
      )}
      {error && <ErrorNotice error={error} />}
    </form>
  );
}
