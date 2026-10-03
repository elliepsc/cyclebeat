import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { REQUEST_TIMEOUT_MS } from "../api/sessions";
import { SLOW_NOTICE_AFTER_MS } from "../useSlowNotice";
import { hangingFetch, json, PLAN, problem, stubFetch } from "../test-utils";
import { DURATION_MAX, DURATION_MIN, GenerateForm } from "./GenerateForm";

describe("GenerateForm", () => {
  it("exposes labelled controls bounded by the contract", () => {
    render(<GenerateForm onGenerated={() => {}} />);
    expect(screen.getByLabelText("Level")).toBeInTheDocument();
    expect(screen.getByLabelText("Goal")).toBeInTheDocument();
    const duration = screen.getByLabelText(/Duration/);
    expect(duration).toHaveAttribute("min", String(DURATION_MIN));
    expect(duration).toHaveAttribute("max", String(DURATION_MAX));
  });

  it("posts the demo source with the chosen values and hands the plan over", async () => {
    const user = userEvent.setup();
    const onGenerated = vi.fn();
    const fetchMock = stubFetch(() => json(PLAN));
    render(<GenerateForm onGenerated={onGenerated} />);

    await user.selectOptions(screen.getByLabelText("Level"), "advanced");
    await user.selectOptions(screen.getByLabelText("Goal"), "intervals");
    await user.clear(screen.getByLabelText(/Duration/));
    await user.type(screen.getByLabelText(/Duration/), "45");
    await user.click(screen.getByRole("button", { name: "Generate session" }));

    await waitFor(() => expect(onGenerated).toHaveBeenCalledWith(PLAN));
    const request = fetchMock.mock.calls[0]![0];
    expect(request.method).toBe("POST");
    expect(new URL(request.url).pathname).toBe("/v1/sessions/generate");
    expect(await request.clone().json()).toEqual({
      source: { type: "demo", value: "" },
      level: "advanced",
      goal: "intervals",
      duration_min: 45,
    });
  });

  it("shows an explicit loading state, then the cold-start message", async () => {
    vi.useFakeTimers();
    hangingFetch();
    render(<GenerateForm onGenerated={() => {}} />);

    fireEvent.click(screen.getByRole("button", { name: "Generate session" }));
    expect(screen.getByRole("status")).toHaveTextContent("Building your session");
    expect(screen.getByRole("button", { name: "Generating..." })).toBeDisabled();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(SLOW_NOTICE_AFTER_MS);
    });
    expect(screen.getByRole("status")).toHaveTextContent("The API is waking up");
  });

  it("gives up after the timeout with its own message", async () => {
    vi.useFakeTimers();
    hangingFetch();
    render(<GenerateForm onGenerated={() => {}} />);

    fireEvent.click(screen.getByRole("button", { name: "Generate session" }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(REQUEST_TIMEOUT_MS);
    });
    expect(screen.getByRole("alert")).toHaveTextContent("did not answer within 90 seconds");
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("shows the 422 title, detail and every reason returned by the API", async () => {
    const user = userEvent.setup();
    stubFetch(() =>
      problem(422, "Unprocessable Entity", "No valid session can be built.", [
        "no_cooldown_candidate",
        "no_warmup_candidate",
      ]),
    );
    render(<GenerateForm onGenerated={() => {}} />);

    await user.click(screen.getByRole("button", { name: "Generate session" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Unprocessable Entity (422)");
    expect(alert).toHaveTextContent("No valid session can be built.");
    expect(alert).toHaveTextContent("no_cooldown_candidate");
    expect(alert).toHaveTextContent("no_warmup_candidate");
  });

  it("shows a network error distinct from an API refusal", async () => {
    const user = userEvent.setup();
    stubFetch(() => {
      throw new TypeError("Failed to fetch");
    });
    render(<GenerateForm onGenerated={() => {}} />);

    await user.click(screen.getByRole("button", { name: "Generate session" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Cannot reach the API");
    expect(alert).not.toHaveTextContent("Reasons returned");
  });
});
