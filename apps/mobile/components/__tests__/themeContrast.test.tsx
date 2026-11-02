import { AA, compositeOver, contrastRatio } from "@/lib/__tests__/support/contrast";
import { darkTheme, lightTheme } from "@/lib/theme";

describe("semantic text contrast", () => {
  it.each([
    ["light", lightTheme],
    ["dark", darkTheme],
  ] as const)("%s textTertiary is AA on bg and surfaceAlt", (_name, theme) => {
    expect(contrastRatio(theme.textTertiary, theme.bg)).toBeGreaterThanOrEqual(AA);
    expect(contrastRatio(theme.textTertiary, theme.surfaceAlt)).toBeGreaterThanOrEqual(AA);
  });

  it.each([
    ["light", lightTheme],
    ["dark", darkTheme],
  ] as const)("%s textSecondary is AA on surfaceAlt", (_name, theme) => {
    expect(contrastRatio(theme.textSecondary, theme.surfaceAlt)).toBeGreaterThanOrEqual(AA);
  });

  it.each([
    ["light", lightTheme],
    ["dark", darkTheme],
  ] as const)("%s userText is AA on the user bubble", (_name, theme) => {
    expect(contrastRatio(theme.userText, theme.userBubble)).toBeGreaterThanOrEqual(AA);
  });

  it.each([
    ["light", lightTheme],
    ["dark", darkTheme],
  ] as const)("%s semantic foregrounds are AA on their fills", (_name, theme) => {
    expect(contrastRatio(theme.onDanger, theme.danger)).toBeGreaterThanOrEqual(AA);
    expect(contrastRatio(theme.onMedia, theme.mediaScrim)).toBeGreaterThanOrEqual(AA);
    expect(contrastRatio(theme.primaryDark, theme.primaryLight)).toBeGreaterThanOrEqual(AA);
    expect(
      contrastRatio(
        theme.text,
        compositeOver(theme.successLight, theme.surface),
      ),
    ).toBeGreaterThanOrEqual(AA);
  });

  // The pairs below are the ones the app draws: every text run in the component
  // tests, rendered in both schemes, paired with the plane it sits on.
  it.each([
    ["light", lightTheme],
    ["dark", darkTheme],
  ] as const)("%s body and secondary ink are AA on every plane they sit on", (_name, theme) => {
    const planes = [
      theme.bg,
      theme.surface,
      theme.surfaceAlt,
      theme.elevated,
      theme.control,
      theme.settingsSurface,
    ];
    for (const plane of planes) {
      expect(contrastRatio(theme.text, plane)).toBeGreaterThanOrEqual(AA);
      expect(contrastRatio(theme.textSecondary, plane)).toBeGreaterThanOrEqual(AA);
    }
    for (const plane of [theme.surface, theme.elevated]) {
      expect(contrastRatio(theme.textTertiary, plane)).toBeGreaterThanOrEqual(AA);
    }
    expect(contrastRatio(theme.codeLang, theme.codeBg)).toBeGreaterThanOrEqual(AA);
  });

  it.each([
    ["light", lightTheme],
    ["dark", darkTheme],
  ] as const)("%s status inks are AA on the page, cards and menus", (_name, theme) => {
    for (const plane of [theme.bg, theme.surface, theme.elevated]) {
      expect(contrastRatio(theme.danger, plane)).toBeGreaterThanOrEqual(AA);
    }
    expect(contrastRatio(theme.success, theme.bg)).toBeGreaterThanOrEqual(AA);
    expect(contrastRatio(theme.warning, theme.bg)).toBeGreaterThanOrEqual(AA);
  });

  // Sign out, Delete all chats and Delete account are danger rows in a Settings
  // group; the profile sheet's Remove photo and its error sit on surfaceAlt.
  it.each([
    ["light", lightTheme],
    ["dark", darkTheme],
  ] as const)("%s danger is AA on Settings groups and the profile sheet", (_name, theme) => {
    expect(contrastRatio(theme.danger, theme.settingsSurface)).toBeGreaterThanOrEqual(AA);
    expect(contrastRatio(theme.danger, theme.surfaceAlt)).toBeGreaterThanOrEqual(AA);
  });

  // A lesson array's lit cell: its index label in success on successLight, on the card's page.
  it.each([
    ["light", lightTheme],
    ["dark", darkTheme],
  ] as const)("%s success is AA on its own well", (_name, theme) => {
    expect(
      contrastRatio(theme.success, compositeOver(theme.successLight, theme.bg)),
    ).toBeGreaterThanOrEqual(AA);
  });

  // Home's overdue card (its due time) and the to-do editor's same-time note: danger on dangerLight.
  it.each([
    ["light", lightTheme],
    ["dark", darkTheme],
  ] as const)("%s danger is AA on its own well", (_name, theme) => {
    expect(contrastRatio(theme.danger, theme.dangerLight)).toBeGreaterThanOrEqual(AA);
  });

  it("textDisabled may sit below AA (placeholders / decoration only)", () => {
    expect(contrastRatio(lightTheme.textDisabled, lightTheme.surfaceAlt)).toBeLessThan(AA);
    expect(contrastRatio(darkTheme.textDisabled, darkTheme.surfaceAlt)).toBeLessThan(AA);
  });
});

describe("inline code pill", () => {
  it.each([
    ["light", lightTheme],
    ["dark", darkTheme],
  ] as const)("%s code ink is AAA on the pill wherever it sits", (_name, theme) => {
    for (const plane of [theme.bg, theme.surface, theme.userBubble]) {
      const pill = compositeOver(theme.codeInlineBg, plane);
      expect(contrastRatio(theme.text, pill)).toBeGreaterThanOrEqual(7);
    }
  });

  it.each([
    ["light", lightTheme],
    ["dark", darkTheme],
  ] as const)("%s pill shows on the page but stays a tint", (_name, theme) => {
    const pill = compositeOver(theme.codeInlineBg, theme.bg);
    expect(contrastRatio(pill, theme.bg)).toBeGreaterThanOrEqual(1.15);
    expect(contrastRatio(pill, theme.bg)).toBeLessThan(1.6);
  });
});

/** A one-pixel line fainter than this disappears on a phone screen. */
const HAIRLINE_MIN = 1.25;

describe("hairline contrast", () => {
  it.each([
    ["light", lightTheme],
    ["dark", darkTheme],
  ] as const)("%s separator shows on every plane it divides", (_name, theme) => {
    for (const plane of [theme.bg, theme.surface, theme.elevated]) {
      expect(contrastRatio(theme.separator, plane)).toBeGreaterThanOrEqual(HAIRLINE_MIN);
    }
  });

  it.each([
    ["light", lightTheme],
    ["dark", darkTheme],
  ] as const)("%s separator stays quieter than border", (_name, theme) => {
    expect(contrastRatio(theme.separator, theme.bg)).toBeLessThan(
      contrastRatio(theme.border, theme.bg),
    );
  });

  it.each([
    ["light", lightTheme],
    ["dark", darkTheme],
  ] as const)("%s quote rule (textDisabled) reads as a line on the page", (_name, theme) => {
    expect(contrastRatio(theme.textDisabled, theme.bg)).toBeGreaterThanOrEqual(3);
  });
});
