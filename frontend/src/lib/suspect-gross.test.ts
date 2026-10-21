import { describe, expect, it } from "vitest";

import { grossFromUnitQtyTare } from "./suspect-gross";

describe("grossFromUnitQtyTare", () => {
  it("rewrites the sample rows to 7.5 and 9.5", () => {
    expect(grossFromUnitQtyTare(4, 1.8, 0.3)).toBe(7.5);
    expect(grossFromUnitQtyTare(4, 2.3, 0.3)).toBe(9.5);
  });
});
