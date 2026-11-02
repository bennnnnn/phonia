import appJson from "../../app.json";

describe("androidKeyboardConfig", () => {
  it("uses resize mode for Reanimated keyboard tracking", () => {
    expect(appJson.expo.android.softwareKeyboardLayoutMode).toBe("resize");
  });
});
