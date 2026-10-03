import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { App } from "./App";
import { json, PLAN, stubFetch } from "./test-utils";

describe("App", () => {
  it("wakes the API on load, then goes from the form to the session", async () => {
    const user = userEvent.setup();
    const fetchMock = stubFetch((request) =>
      new URL(request.url).pathname === "/health" ? json({ status: "ok" }) : json(PLAN),
    );
    render(<App />);

    const paths = () => fetchMock.mock.calls.map(([request]) => new URL(request.url).pathname);
    expect(paths()).toEqual(["/health"]);

    await user.click(screen.getByRole("button", { name: "Generate session" }));

    expect(await screen.findByRole("heading", { name: "Your session" })).toBeInTheDocument();
    expect(paths()).toEqual(["/health", "/v1/sessions/generate"]);

    await user.click(screen.getByRole("button", { name: "Plan another session" }));
    expect(screen.getByRole("heading", { name: "Plan a session" })).toBeInTheDocument();
  });

  it("keeps working when the warm-up call fails", async () => {
    stubFetch(() => {
      throw new TypeError("Failed to fetch");
    });
    render(<App />);
    expect(screen.getByRole("heading", { name: "Plan a session" })).toBeInTheDocument();
  });
});
