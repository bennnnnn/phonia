import {
  CHART_MAX_EXPANDED,
  CHART_MAX_HEIGHT,
  CHART_MIN_HEIGHT,
  CHART_PREVIEW_HEIGHT,
} from "@/lib/chartPreviewHeight";

const {
  clamp: clampChartPreviewHeight,
  next: nextChartPreviewHeight,
  isClipped: chartPreviewIsClipped,
  toggled: chartTogglePreviewHeight,
} = CHART_PREVIEW_HEIGHT;

describe("clampChartPreviewHeight", () => {
  it("floors empty reports at the min placeholder", () => {
    expect(clampChartPreviewHeight(0, CHART_MAX_HEIGHT)).toBe(CHART_MIN_HEIGHT);
  });

  it("caps at the active max", () => {
    expect(clampChartPreviewHeight(900, CHART_MAX_HEIGHT)).toBe(CHART_MAX_HEIGHT);
  });
});

describe("nextChartPreviewHeight", () => {
  it("grows from the placeholder toward the reported SVG height", () => {
    expect(nextChartPreviewHeight(240, CHART_MIN_HEIGHT, CHART_MAX_HEIGHT)).toBe(240);
  });

  it("does not shrink after first paint", () => {
    expect(nextChartPreviewHeight(160, 300, CHART_MAX_HEIGHT)).toBeNull();
  });
});

describe("chartPreviewIsClipped", () => {
  it("is false when the SVG already fits the card", () => {
    expect(chartPreviewIsClipped(240, 240)).toBe(false);
    expect(chartPreviewIsClipped(240, CHART_MAX_HEIGHT)).toBe(false);
  });

  it("is true when the raw SVG is taller than the clamped WebView", () => {
    expect(chartPreviewIsClipped(600, CHART_MAX_HEIGHT)).toBe(true);
  });
});

describe("chartTogglePreviewHeight", () => {
  it("grows to the raw SVG size instead of the already-clamped ref", () => {
    expect(chartTogglePreviewHeight(600, true)).toBe(600);
    expect(chartTogglePreviewHeight(600, false)).toBe(CHART_MAX_HEIGHT);
  });

  it("caps expand at CHART_MAX_EXPANDED", () => {
    expect(chartTogglePreviewHeight(1200, true)).toBe(CHART_MAX_EXPANDED);
  });
});
