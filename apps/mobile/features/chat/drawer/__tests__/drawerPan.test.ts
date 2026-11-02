import { cappedDrawerWidth, DRAWER_MAX_WIDTH } from "@/features/chat/drawer/drawerPan";

describe("cappedDrawerWidth", () => {
  it("keeps the 82% ratio on phones", () => {
    expect(cappedDrawerWidth(390)).toBeCloseTo(390 * 0.82);
  });

  it("caps on tablets so chat keeps a gutter", () => {
    expect(cappedDrawerWidth(768)).toBe(DRAWER_MAX_WIDTH);
    expect(cappedDrawerWidth(1024)).toBe(DRAWER_MAX_WIDTH);
  });
});
