import { placePopover, POPOVER_GAP, POPOVER_MARGIN } from "@/ui/overlay/placement";

const screen = { width: 390, height: 844 };
const insets = { top: 47, bottom: 34, left: 0, right: 0 };

describe("placePopover", () => {
  it("drops below a header ⋮ and opens leftward from the right edge", () => {
    const anchor = { x: 334, y: 50, width: 44, height: 44 };
    const p = placePopover({ anchor, width: 260, height: 300, screen, insets });
    expect(p.side).toBe("below");
    expect(p.top).toBe(50 + 44 + POPOVER_GAP);
    // Right edges line up, as with the ChatGPT ⋮ menu.
    expect(p.left + 260).toBe(334 + 44);
    expect(p.origin.y).toBe(0);
  });

  it("opens rightward from a control on the left half", () => {
    const anchor = { x: 16, y: 120, width: 120, height: 44 };
    const p = placePopover({ anchor, width: 240, height: 200, screen, insets });
    expect(p.left).toBe(16);
  });

  it("flips above when a long-press near the bottom has no room below", () => {
    const anchor = { x: 200, y: 760, width: 0, height: 0 };
    const p = placePopover({ anchor, width: 240, height: 300, screen, insets });
    expect(p.side).toBe("above");
    expect(p.top + 300).toBe(760 - POPOVER_GAP);
    expect(p.origin.y).toBe(300);
  });

  it("never leaves the screen edges", () => {
    const anchor = { x: 380, y: 300, width: 0, height: 0 };
    const p = placePopover({ anchor, width: 260, height: 200, screen, insets });
    expect(p.left + 260).toBeLessThanOrEqual(screen.width - POPOVER_MARGIN);
    const near = placePopover({ anchor: { x: 2, y: 300, width: 0, height: 0 }, width: 260, height: 200, screen, insets });
    expect(near.left).toBe(POPOVER_MARGIN);
  });

  it("uses the roomier side and lets rows scroll when neither side fits", () => {
    const anchor = { x: 100, y: 500, width: 44, height: 44 };
    const p = placePopover({ anchor, width: 240, height: 900, screen, insets });
    expect(p.side).toBe("above");
    expect(p.maxHeight).toBe(500 - POPOVER_GAP - (insets.top + POPOVER_MARGIN));
    expect(p.top).toBe(insets.top + POPOVER_MARGIN);
  });

  it("centers like a dialog when there is no anchor", () => {
    const p = placePopover({ anchor: null, width: 300, height: 200, screen, insets });
    expect(p.side).toBe("center");
    expect(p.left).toBe(45);
    expect(p.origin).toEqual({ x: 150, y: 100 });
  });

  it("narrows a card wider than the screen", () => {
    const small = { width: 280, height: 600 };
    const p = placePopover({ anchor: null, width: 400, height: 100, screen: small, insets });
    expect(p.left).toBe(POPOVER_MARGIN);
  });
});
