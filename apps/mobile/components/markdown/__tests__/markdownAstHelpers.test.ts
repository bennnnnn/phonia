import {
  immediateAncestorType,
  listItemDisplayNumber,
  listItemHasNestedList,
  shouldNumberListItem,
  listLargestNumber,
  numberColumnWidth,
  bulletDiscMetrics,
} from "@/components/markdown/markdownAstHelpers";

describe("nested list numbering", () => {
  it("does not number a top-level bullet list", () => {
    const parent = [{ type: "bullet_list" }];
    expect(immediateAncestorType(parent)).toBe("bullet_list");
    expect(shouldNumberListItem(parent)).toBe(false);
  });

  it("keeps bullets nested under another bullet list unordered", () => {
    const parent = [
      { type: "bullet_list" },
      { type: "list_item" },
      { type: "bullet_list" },
    ];
    expect(shouldNumberListItem(parent)).toBe(false);
    expect(listItemDisplayNumber(parent, 0)).toBe(1);
    expect(listItemDisplayNumber(parent, 1)).toBe(2);
  });

  it("numbers a real ordered list even when it sits under a bullet", () => {
    const parent = [
      { type: "ordered_list", attributes: { start: 3 } },
      { type: "list_item" },
      { type: "bullet_list" },
    ];
    expect(shouldNumberListItem(parent)).toBe(true);
    expect(listItemDisplayNumber(parent, 0)).toBe(3);
  });
});

describe("listItemHasNestedList", () => {
  it("is false for a leaf bullet", () => {
    expect(
      listItemHasNestedList({
        key: "a",
        type: "list_item",
        children: [{ key: "p", type: "paragraph", content: "Personalized" }],
      }),
    ).toBe(false);
  });

  it("is true when a topic item contains a nested bullet list", () => {
    expect(
      listItemHasNestedList({
        key: "a",
        type: "list_item",
        children: [
          { key: "p", type: "paragraph", content: "Strengths" },
          { key: "l", type: "bullet_list", children: [] },
        ],
      }),
    ).toBe(true);
  });
});

describe("numbered list column", () => {
  it("fits the list's largest number, so 9. and 10. share one text edge", () => {
    expect(numberColumnWidth(9, 1)).toBe(22);
    expect(numberColumnWidth(12, 1)).toBe(22);
    expect(numberColumnWidth(100, 1)).toBeGreaterThan(22);
    // Larger text: the column grows with it instead of pushing 10+ right.
    expect(numberColumnWidth(12, 1.5)).toBeGreaterThan(numberColumnWidth(12, 1));
  });

  it("reads the largest number from the list's start and item count", () => {
    const list = { attributes: { start: 8 }, children: [{}, {}, {}] };
    expect(listLargestNumber([list])).toBe(10);
    expect(listLargestNumber([{ children: [{}, {}] }])).toBe(2);
    expect(listLargestNumber([])).toBe(1);
  });
});

describe("bulletDiscMetrics", () => {
  it.each([
    // 16pt body, line box 22.8pt: a 6pt disc drops 8pt to sit on its middle.
    [1, 6, 8],
    [0.85, 6, 8],
    [1.5, 9, 13],
    // The disc stops growing at 1.5x; the drop keeps following the line.
    [2, 9, 18],
  ])("at text scale %p is %ppt and drops %ppt", (scale, size, top) => {
    expect(bulletDiscMetrics(scale)).toEqual({ size, top });
  });
});
