import { typingPulseKindForPhase } from "@/lib/typingPulse";

describe("typingPulseKindForPhase", () => {
  it("maps prep / memory / files to calm", () => {
    expect(typingPulseKindForPhase("preparing")).toBe("calm");
    expect(typingPulseKindForPhase("remembering")).toBe("calm");
    expect(typingPulseKindForPhase("reading_files")).toBe("calm");
    expect(typingPulseKindForPhase(undefined)).toBe("calm");
  });

  it("maps thinking / composing to active", () => {
    expect(typingPulseKindForPhase("thinking")).toBe("active");
    expect(typingPulseKindForPhase("composing")).toBe("active");
  });

  it("maps search / math / physics to busy", () => {
    expect(typingPulseKindForPhase("searching")).toBe("busy");
    expect(typingPulseKindForPhase("calculating")).toBe("busy");
    expect(typingPulseKindForPhase("physics")).toBe("busy");
    expect(typingPulseKindForPhase("finding_photo")).toBe("busy");
  });
});
