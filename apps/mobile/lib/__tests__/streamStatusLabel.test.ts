import type { TFunction } from "i18next";

import {
  clipStreamStatusDetail,
  initialStreamStatusTick,
  isProgressStreamPhase,
  phaseStartedAt,
  pickRotatingStreamLabel,
  progressStreamLabel,
  shouldShowWaitingIndicator,
  streamStatusLabels,
} from "@/lib/streamStatusLabel";

const t = ((key: string, options?: { detail?: string; seconds?: number }) => {
  const map: Record<string, string> = {
    "chat.status.searching": "Searching the web…",
    "chat.status.searching_1": "Checking sources…",
    "chat.status.searching_detail": "Searching — “{{detail}}”",
    "chat.status.preparing": "Getting ready…",
    "chat.status.remembering": "Recalling what I know about you…",
    "chat.status.thinking": "Thinking…",
    "chat.status.thinking_seconds": "Thinking… {{seconds}}s",
    "chat.status.checking": "Checking the answer…",
    "chat.status.composing": "Writing a reply…",
    "chat.status.finding_photo": "Finding a photo…",
    "chat.status.finding_photo_detail": "Finding a photo — “{{detail}}”",
    "chat.status.answer_photo": "Finding a photo…",
    "chat.status.unknown": "missing",
  };
  const raw = map[key];
  if (raw === undefined) return key;
  return raw
    .replace("{{detail}}", options?.detail ?? "{{detail}}")
    .replace("{{seconds}}", String(options?.seconds ?? "{{seconds}}"));
}) as TFunction;

describe("streamStatusLabels", () => {
  it("collects base and numbered variants", () => {
    expect(streamStatusLabels(t, "searching")).toEqual([
      "Searching the web…",
      "Checking sources…",
    ]);
  });

  it("returns empty when phase is unknown", () => {
    expect(streamStatusLabels(t, "not_a_real_phase")).toEqual([]);
  });

  it("hides preparing/remembering/composing — typing dots only", () => {
    expect(streamStatusLabels(t, "preparing")).toEqual([]);
    expect(streamStatusLabels(t, "remembering")).toEqual([]);
    expect(streamStatusLabels(t, "composing")).toEqual([]);
  });

  it("leaves thinking and checking to their timed progress label", () => {
    expect(streamStatusLabels(t, "thinking")).toEqual([]);
    expect(streamStatusLabels(t, "checking")).toEqual([]);
  });

  it("leads with the detail label when detail is provided", () => {
    expect(streamStatusLabels(t, "searching", "weather in berlin")).toEqual([
      "Searching — “weather in berlin”",
      "Searching the web…",
      "Checking sources…",
    ]);
  });

  // S7.9: a reference-photo lookup said "Sketching it out" with an image-gen progress card.
  it("labels a photo lookup as finding a photo, with its query", () => {
    expect(streamStatusLabels(t, "finding_photo", "human ear")).toEqual([
      "Finding a photo — “human ear”",
      "Finding a photo…",
    ]);
  });

  it("ignores detail when the phase has no _detail template", () => {
    expect(streamStatusLabels(t, "not_a_real_phase", "x")).toEqual([]);
  });

  it("rotates through labels", () => {
    const labels = ["A", "B", "C"];
    expect(pickRotatingStreamLabel(labels, 0)).toBe("A");
    expect(pickRotatingStreamLabel(labels, 1)).toBe("B");
    expect(pickRotatingStreamLabel(labels, 3)).toBe("A");
  });
});

describe("shouldShowWaitingIndicator", () => {
  it("shows while streaming with no content", () => {
    expect(shouldShowWaitingIndicator({ isStreaming: true, hasContent: false })).toBe(true);
  });

  it("hides once content has started arriving", () => {
    expect(shouldShowWaitingIndicator({ isStreaming: true, hasContent: true })).toBe(false);
  });

  it("hides when not streaming", () => {
    expect(shouldShowWaitingIndicator({ isStreaming: false, hasContent: false })).toBe(false);
  });
});

describe("clipStreamStatusDetail", () => {
  it("flattens whitespace and passes short details through", () => {
    expect(clipStreamStatusDetail("  weather \n in  berlin ")).toBe(
      "weather in berlin",
    );
  });

  it("truncates long details with an ellipsis", () => {
    const long = "a".repeat(120);
    const clipped = clipStreamStatusDetail(long);
    expect(clipped.length).toBeLessThanOrEqual(45);
    expect(clipped.endsWith("…")).toBe(true);
  });
});

describe("initialStreamStatusTick", () => {
  it("always starts at the detail label when present", () => {
    expect(initialStreamStatusTick(4, true, () => 0.9)).toBe(0);
  });

  it("starts at zero for single-label phases", () => {
    expect(initialStreamStatusTick(1, false, () => 0.9)).toBe(0);
  });

  it("randomizes the opening variant otherwise", () => {
    expect(initialStreamStatusTick(4, false, () => 0)).toBe(0);
    expect(initialStreamStatusTick(4, false, () => 0.5)).toBe(2);
    expect(initialStreamStatusTick(4, false, () => 0.99)).toBe(3);
  });
});

describe("progressStreamLabel", () => {
  it("shows nothing for a progress phase in its first second", () => {
    expect(progressStreamLabel(t, "thinking", 0)).toBeNull();
    expect(progressStreamLabel(t, "thinking", 999)).toBeNull();
    expect(progressStreamLabel(t, "checking", 400)).toBeNull();
  });

  it("counts whole seconds of thinking", () => {
    expect(progressStreamLabel(t, "thinking", 1000)).toBe("Thinking… 1s");
    expect(progressStreamLabel(t, "thinking", 12_999)).toBe("Thinking… 12s");
  });

  it("names the answer check", () => {
    expect(progressStreamLabel(t, "checking", 1500)).toBe("Checking the answer…");
  });

  it("reads any other phase as its own label at once, and theater as nothing", () => {
    expect(progressStreamLabel(t, "finding_photo", 0)).toBe("Finding a photo…");
    expect(progressStreamLabel(t, "answer_photo", 0)).toBe("Finding a photo…");
    expect(progressStreamLabel(t, "composing", 5000)).toBeNull();
  });

  it("shows nothing once the reply's last step has finished", () => {
    expect(streamStatusLabels(t, "finishing")).toEqual([]);
    expect(progressStreamLabel(t, "finishing", 5000)).toBeNull();
  });

  it("knows which phases are progress", () => {
    expect(isProgressStreamPhase("thinking")).toBe(true);
    expect(isProgressStreamPhase("checking")).toBe(true);
    expect(isProgressStreamPhase("searching")).toBe(false);
    expect(isProgressStreamPhase(undefined)).toBe(false);
  });
});

describe("phaseStartedAt", () => {
  const now = 100_000;

  it("starts a new phase now, or back by the server's elapsed time", () => {
    expect(phaseStartedAt(null, "thinking", undefined, now)).toBe(now);
    expect(phaseStartedAt({ status: "composing" }, "thinking", 2300, now)).toBe(now - 2300);
  });

  it("keeps the start of a phase sent again", () => {
    const previous = { status: "thinking", statusStartedAt: now - 9000 };
    expect(phaseStartedAt(previous, "thinking", 100, now)).toBe(now - 9000);
  });

  it("ignores an elapsed time that is not a sane number", () => {
    expect(phaseStartedAt(null, "thinking", "2300", now)).toBe(now);
    expect(phaseStartedAt(null, "thinking", -50, now)).toBe(now);
    expect(phaseStartedAt(null, "thinking", Number.NaN, now)).toBe(now);
    expect(phaseStartedAt(null, "thinking", 10 ** 12, now)).toBe(now - 10 * 60 * 1000);
  });
});
