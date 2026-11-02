import { addFabClearance, FAB_SIZE, fabBottom } from "../addFabLayout";

describe("addFabLayout", () => {
  it.each([
    // No home indicator: the 12pt floor, then 8pt.
    [0, 20],
    // A home indicator inset replaces the floor.
    [34, 42],
  ])("sits the FAB above a %ppt inset at %ppt", (inset, bottom) => {
    expect(fabBottom(inset)).toBe(bottom);
  });

  it("clears the FAB's top edge with room to spare", () => {
    for (const inset of [0, 34]) {
      expect(addFabClearance(inset)).toBeGreaterThan(fabBottom(inset) + FAB_SIZE);
    }
  });
});
