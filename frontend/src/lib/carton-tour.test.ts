import { describe, expect, it } from "vitest";

import { CARTON_TOUR_BUTTONS } from "@/lib/carton-tour";

describe("carton tour buttons", () => {
  it("uses Chinese labels instead of Previous and Next", () => {
    expect(CARTON_TOUR_BUTTONS.prevBtnText).toBe("上一步");
    expect(CARTON_TOUR_BUTTONS.nextBtnText).toBe("下一步");
    expect(CARTON_TOUR_BUTTONS.doneBtnText).toBe("完成");
    expect(Object.values(CARTON_TOUR_BUTTONS).join(" ")).not.toMatch(/Previous|Next|Done/);
  });
});
