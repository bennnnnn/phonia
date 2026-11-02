import { stripMemoryAsOf } from "@/features/memory/model/memoryFacts";

describe("memoryFacts", () => {
  it("drops the server's freshness stamp from a fact", () => {
    expect(stripMemoryAsOf("As of 2026-09-20: Likes short answers")).toBe("Likes short answers");
    expect(stripMemoryAsOf("  Likes tea ")).toBe("Likes tea");
  });
});
