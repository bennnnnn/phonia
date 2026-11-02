import { shadowElevated, shadowGlow, shadowOverlay, shadowRaised } from "@/lib/shadow";
import { darkTheme, lightTheme } from "@/lib/theme";

describe("shadowRaised", () => {
  it("uses a lighter opacity in light mode than dark", () => {
    const light = shadowRaised(lightTheme);
    const dark = shadowRaised(darkTheme);
    expect(light.shadowOpacity).toBeLessThan(dark.shadowOpacity as number);
  });
});

describe("shadowOverlay", () => {
  it("keeps stronger elevation for menus", () => {
    expect(shadowOverlay(lightTheme).elevation).toBe(20);
    expect(shadowOverlay(darkTheme).shadowOpacity).toBeGreaterThan(
      shadowRaised(darkTheme).shadowOpacity as number,
    );
  });
});

describe("shadowElevated", () => {
  it("scales opacity by theme for floating chrome", () => {
    const light = shadowElevated(lightTheme, "fab");
    const dark = shadowElevated(darkTheme, "fab");
    expect(light.elevation).toBe(8);
    expect(light.shadowOpacity).toBeLessThan(dark.shadowOpacity as number);
  });
});

describe("shadowGlow", () => {
  it("tints the shadow with the supplied brand color", () => {
    const glow = shadowGlow(lightTheme, lightTheme.primary);
    expect(glow.shadowColor).toBe(lightTheme.primary);
    expect(glow.elevation).toBe(8);
  });

  it("uses a stronger opacity in dark mode than light", () => {
    const light = shadowGlow(lightTheme, lightTheme.primary);
    const dark = shadowGlow(darkTheme, darkTheme.primary);
    expect(dark.shadowOpacity).toBeGreaterThan(light.shadowOpacity as number);
  });
});
