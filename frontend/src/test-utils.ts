import { vi } from "vitest";

import type { SessionPlan } from "./api/sessions";

type Handler = (request: Request) => Response | Promise<Response>;

/** Replaces `fetch` for the test. The handler receives the real Request the client built. */
export function stubFetch(handler: Handler) {
  const mock = vi.fn(async (input: Request) => handler(input));
  vi.stubGlobal("fetch", mock);
  return mock;
}

export function json(body: unknown, status = 200, contentType = "application/json"): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": contentType },
  });
}

export function problem(status: number, title: string, detail: string, reasons: string[]) {
  return json(
    { type: "about:blank", title, status, detail, reasons },
    status,
    "application/problem+json",
  );
}

/** A fetch that never answers on its own and rejects as a real one does when aborted. */
export function hangingFetch() {
  return stubFetch(
    (request) =>
      new Promise<Response>((_, reject) => {
        request.signal.addEventListener("abort", () =>
          reject(new DOMException("The operation was aborted.", "AbortError")),
        );
      }),
  );
}

export const PLAN: SessionPlan = {
  session_id: "sess-123",
  level: "beginner",
  goal: "endurance",
  duration_min: 30,
  verdict: "review",
  duration_gap_s: 20,
  warnings: ["low_confidence_track"],
  created_at: "2026-10-05T10:00:00Z",
  segments: [
    {
      order: 1,
      role: "endurance",
      zone: "Z3",
      duration_s: 245,
      track: {
        track_id: "t2",
        title: "Second Song",
        artist: "Band B",
        duration_s: 245,
        bpm_effective: 123.046875,
        zone: "Z3",
        confidence: 0.6,
      },
    },
    {
      order: 0,
      role: "warmup",
      zone: "Z1",
      duration_s: 180,
      track: {
        track_id: "t1",
        title: "First Song",
        artist: "Band A",
        duration_s: 180,
        bpm_effective: 92,
        zone: "Z1",
        confidence: 0.9,
      },
    },
  ],
};
