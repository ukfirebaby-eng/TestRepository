import { describe, expect, it } from "vitest";
import { advanceFocusAnimation } from "./cameraFocus";

describe("advanceFocusAnimation", () => {
  it("starts a new focus animation when the selected graph element changes", () => {
    expect(advanceFocusAnimation({ key: null, frames: 0, active: false }, "node:a")).toEqual({
      key: "node:a",
      frames: 1,
      active: true,
    });
  });

  it("releases camera control after the focus animation settles", () => {
    expect(advanceFocusAnimation({ key: "node:a", frames: 90, active: true }, "node:a", 90)).toEqual({
      key: "node:a",
      frames: 91,
      active: false,
    });
  });
});
