// @vitest-environment node
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import { DURATION_MAX, DURATION_MIN } from "../screens/GenerateForm";

// The generated types carry no numeric bounds, so the form's constants are checked against
// the contract itself.
describe("form constants vs openapi.yaml", () => {
  const contract = readFileSync(new URL("../../../openapi.yaml", import.meta.url), "utf-8");

  it("duration_min bounds match", () => {
    const match =
      /duration_min:\s*\n\s*type: integer\s*\n\s*minimum: (\d+)\s*\n\s*maximum: (\d+)/.exec(contract);
    expect(match, "duration_min bounds not found in openapi.yaml").not.toBeNull();
    expect([DURATION_MIN, DURATION_MAX]).toEqual([Number(match![1]), Number(match![2])]);
  });
});
