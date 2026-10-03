import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { json, PLAN, problem, stubFetch } from "../test-utils";
import { SessionView } from "./SessionView";

describe("SessionView", () => {
  it("lists the segments in order (the API counts from 0) with role, zone, BPM, confidence and duration", () => {
    render(<SessionView plan={PLAN} onRestart={() => {}} />);

    const rows = screen.getAllByRole("row").slice(1); // drop the header row
    expect(rows).toHaveLength(2);
    const first = within(rows[0]!).getAllByRole("cell").map((c) => c.textContent);
    expect(first).toEqual(["1", "warmup", "Z1", "First Song Band A", "92", "0.9", "3:00"]);
    const second = within(rows[1]!).getAllByRole("cell").map((c) => c.textContent);
    expect(second).toEqual(["2", "endurance", "Z3", "Second Song Band B", "123", "0.6", "4:05"]);
  });

  it("shows the total duration, the verdict and the warnings", () => {
    render(<SessionView plan={PLAN} onRestart={() => {}} />);

    expect(screen.getByRole("table")).toHaveAccessibleName(/Total duration 7:05 \(\+0:20/);
    expect(screen.getByText("review")).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("low_confidence_track");
  });

  it("sends the feedback to the session and confirms it", async () => {
    const user = userEvent.setup();
    const fetchMock = stubFetch(() =>
      json({ session_id: "sess-123", rating: "up", note: "great", created_at: "2026-10-05T10:00:00Z" }, 201),
    );
    render(<SessionView plan={PLAN} onRestart={() => {}} />);

    expect(screen.getByRole("button", { name: "Send feedback" })).toBeDisabled();
    await user.click(screen.getByLabelText("Good"));
    await user.type(screen.getByLabelText(/Note/), "great");
    await user.click(screen.getByRole("button", { name: "Send feedback" }));

    expect(await screen.findByRole("status")).toHaveTextContent("feedback was recorded");
    const request = fetchMock.mock.calls[0]![0];
    expect(new URL(request.url).pathname).toBe("/v1/sessions/sess-123/feedback");
    expect(await request.clone().json()).toEqual({ rating: "up", note: "great" });
  });

  it("shows the reasons when the feedback is refused", async () => {
    const user = userEvent.setup();
    stubFetch(() => problem(422, "Unprocessable Entity", "Bad feedback.", ["note: too long"]));
    render(<SessionView plan={PLAN} onRestart={() => {}} />);

    await user.click(screen.getByLabelText("Not good"));
    await user.click(screen.getByRole("button", { name: "Send feedback" }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("note: too long"));
  });

  it("lets the user start over", async () => {
    const user = userEvent.setup();
    const onRestart = vi.fn();
    render(<SessionView plan={PLAN} onRestart={onRestart} />);

    await user.click(screen.getByRole("button", { name: "Plan another session" }));
    expect(onRestart).toHaveBeenCalledOnce();
  });
});
