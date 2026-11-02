import {
  MERMAID_MAX_EXPANDED,
  MERMAID_MAX_HEIGHT,
  MERMAID_MIN_HEIGHT,
  MERMAID_PREVIEW_HEIGHT,
} from "@/lib/mermaidPreviewHeight";

const { clamp: clampMermaidPreviewHeight, next: nextMermaidPreviewHeight } = MERMAID_PREVIEW_HEIGHT;

describe("clampMermaidPreviewHeight", () => {
  it("floors empty reports at the min placeholder", () => {
    expect(clampMermaidPreviewHeight(0, MERMAID_MAX_HEIGHT)).toBe(MERMAID_MIN_HEIGHT);
    expect(clampMermaidPreviewHeight(-8, MERMAID_MAX_HEIGHT)).toBe(MERMAID_MIN_HEIGHT);
  });

  it("caps an 8-step flowchart under the default max, not the old 220 clip", () => {
    expect(clampMermaidPreviewHeight(520, MERMAID_MAX_HEIGHT)).toBe(520);
    expect(MERMAID_MAX_HEIGHT).toBeGreaterThan(220);
  });

  it("does not grow past the active max", () => {
    expect(clampMermaidPreviewHeight(900, MERMAID_MAX_HEIGHT)).toBe(MERMAID_MAX_HEIGHT);
    expect(clampMermaidPreviewHeight(1200, MERMAID_MAX_EXPANDED)).toBe(MERMAID_MAX_EXPANDED);
  });
});

describe("nextMermaidPreviewHeight", () => {
  it("grows from the placeholder toward the reported SVG height", () => {
    expect(nextMermaidPreviewHeight(520, MERMAID_MIN_HEIGHT, MERMAID_MAX_HEIGHT)).toBe(520);
  });

  it("ignores sub-pixel chatter", () => {
    expect(nextMermaidPreviewHeight(163, MERMAID_MIN_HEIGHT, MERMAID_MAX_HEIGHT)).toBeNull();
  });

  it("does not shrink after first paint", () => {
    expect(nextMermaidPreviewHeight(180, 400, MERMAID_MAX_HEIGHT)).toBeNull();
  });
});
