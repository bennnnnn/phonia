import {
  getDisplayName,
  getInitials,
  sanitizeDisplayName,
} from "@/lib/profile";

describe("profile helpers", () => {
  it("sanitizeDisplayName collapses whitespace and enforces length", () => {
    expect(sanitizeDisplayName("  Ada   Lovelace  ")).toBe("Ada Lovelace");
    expect(sanitizeDisplayName("   ")).toBeNull();
    expect(sanitizeDisplayName("x".repeat(81))).toBeNull();
  });

  it("getDisplayName falls back when empty", () => {
    expect(getDisplayName("Ada", "You")).toBe("Ada");
    expect(getDisplayName("  ", "You")).toBe("You");
  });

  it("getInitials uses up to two words", () => {
    expect(getInitials("Ada Lovelace")).toBe("AL");
    expect(getInitials("Cher")).toBe("C");
    expect(getInitials(null)).toBe("?");
  });
});
