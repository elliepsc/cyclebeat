// The only module that talks to the network. The types come from the generated schema.d.ts.
import type { components } from "./schema";
import { client } from "./client";

type Schemas = components["schemas"];
export type Level = Schemas["Level"];
export type Goal = Schemas["Goal"];
export type Zone = Schemas["Zone"];
export type Verdict = Schemas["Verdict"];
export type SegmentRole = Schemas["SegmentRole"];
export type GenerateSessionRequest = Schemas["GenerateSessionRequest"];
export type SessionPlan = Schemas["SessionPlan"];
export type Segment = Schemas["Segment"];
export type FeedbackRequest = Schemas["FeedbackRequest"];
export type Feedback = Schemas["Feedback"];

// The free Render instance sleeps; a cold start can take a minute.
export const REQUEST_TIMEOUT_MS = 90_000;

export type ApiFailure =
  | { kind: "problem"; status: number; title: string; detail?: string; reasons: string[] }
  | { kind: "network" }
  | { kind: "timeout"; afterMs: number };

export type ApiResult<T> = { ok: true; data: T } | { ok: false; error: ApiFailure };

interface Outcome<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

function toProblem(status: number, body: unknown): ApiFailure {
  const problem: Record<string, unknown> =
    typeof body === "object" && body !== null ? (body as Record<string, unknown>) : {};
  const reasons = Array.isArray(problem.reasons)
    ? problem.reasons.filter((r): r is string => typeof r === "string")
    : [];
  return {
    kind: "problem",
    status,
    title: typeof problem.title === "string" ? problem.title : `HTTP ${status}`,
    detail: typeof problem.detail === "string" ? problem.detail : undefined,
    reasons,
  };
}

async function call<T>(
  run: (signal: AbortSignal) => Promise<Outcome<T>>,
  timeoutMs: number,
): Promise<ApiResult<T>> {
  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  try {
    const { data, error, response } = await run(controller.signal);
    if (response.ok && data !== undefined) return { ok: true, data };
    return { ok: false, error: toProblem(response.status, error) };
  } catch {
    return {
      ok: false,
      error: timedOut ? { kind: "timeout", afterMs: timeoutMs } : { kind: "network" },
    };
  } finally {
    clearTimeout(timer);
  }
}

export function generateSession(
  body: GenerateSessionRequest,
  timeoutMs = REQUEST_TIMEOUT_MS,
): Promise<ApiResult<SessionPlan>> {
  return call((signal) => client.POST("/v1/sessions/generate", { body, signal }), timeoutMs);
}

export function submitFeedback(
  sessionId: string,
  body: FeedbackRequest,
  timeoutMs = REQUEST_TIMEOUT_MS,
): Promise<ApiResult<Feedback>> {
  return call(
    (signal) =>
      client.POST("/v1/sessions/{session_id}/feedback", {
        params: { path: { session_id: sessionId } },
        body,
        signal,
      }),
    timeoutMs,
  );
}

/** Wakes a sleeping API ahead of the first real call. The outcome does not matter. */
export async function warmUp(timeoutMs = REQUEST_TIMEOUT_MS): Promise<void> {
  await call((signal) => client.GET("/health", { signal }), timeoutMs);
}
