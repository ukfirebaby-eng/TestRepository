import { describe, expect, it } from "vitest";
import { getFocusTarget, getLinkFocusTarget, seededPosition } from "./spatialLayout";

describe("spatial layout helpers", () => {
  it("creates deterministic node positions", () => {
    const first = seededPosition(4, 12, 8);
    const second = seededPosition(4, 12, 8);

    expect(first).toEqual(second);
  });

  it("places camera focus beyond a selected node", () => {
    const position = seededPosition(2, 8, 16);
    const focus = getFocusTarget(position);

    expect(focus.lookAt).toEqual(position);
    expect(focus.camera.z).toBeGreaterThan(position.z);
    expect(focus.camera.y).toBeGreaterThan(position.y);
  });

  it("focuses links at their midpoint", () => {
    const source = { x: -2, y: 1, z: 0 };
    const target = { x: 4, y: 3, z: 2 };
    const focus = getLinkFocusTarget(source, target);

    expect(focus.lookAt).toEqual({ x: 1, y: 2, z: 1 });
    expect(focus.camera.z).toBeGreaterThan(focus.lookAt.z);
  });
});
