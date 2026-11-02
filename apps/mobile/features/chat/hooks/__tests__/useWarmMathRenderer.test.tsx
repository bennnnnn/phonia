import { act, renderHook } from "@testing-library/react-native";

import {
  DISPLAY_MATHS_MARKERS,
  useWarmMathRenderer,
  WARM_MATH_AFTER_MS,
} from "@/features/chat/hooks/useWarmMathRenderer";
import type { Message } from "@/lib/api";
import { warmSvgMath } from "@/lib/math/svgMath";
import { publishStreamingDraft } from "@/features/chat/model/streamingDraftStore";

jest.mock("@/lib/math/svgMath", () => ({ warmSvgMath: jest.fn() }));

const message = (content: string): Message =>
  ({ id: content, role: "assistant", content, model: null, created_at: "2026-10-01T10:00:00Z" }) as Message;
const PLAIN = [message("Here is a plan for your week."), message("Inline $x^2$ only.")];
const DISPLAY = [message("The roots are\n\n$$x = \\frac{-b \\pm \\sqrt{\\Delta}}{2a}$$")];

beforeEach(() => {
  jest.useFakeTimers();
  jest.mocked(warmSvgMath).mockClear();
  publishStreamingDraft(null);
});
afterEach(() => {
  publishStreamingDraft(null);
  jest.useRealTimers();
});

async function idle(ms = WARM_MATH_AFTER_MS + 100) {
  await act(async () => {
    jest.advanceTimersByTime(ms);
  });
}

describe("useWarmMathRenderer", () => {
  it("never loads the maths renderer for a chat without display maths", async () => {
    await renderHook(() => useWarmMathRenderer(PLAIN));
    await idle(60_000);
    expect(warmSvgMath).not.toHaveBeenCalled();
  });

  it("loads it once a thread with display maths has settled and gone idle", async () => {
    await renderHook(() => useWarmMathRenderer(DISPLAY));
    await idle(WARM_MATH_AFTER_MS - 1);
    expect(warmSvgMath).not.toHaveBeenCalled();
    await idle(100);
    expect(warmSvgMath).toHaveBeenCalledTimes(1);
  });

  it("loads it when the reply streaming in starts display maths, a marker split across flushes too", async () => {
    await renderHook(() => useWarmMathRenderer(PLAIN));
    await act(async () => {
      publishStreamingDraft({ content: "We integrate: \\in" });
    });
    await idle();
    expect(warmSvgMath).not.toHaveBeenCalled();
    await act(async () => {
      publishStreamingDraft({ content: "We integrate: \\int_0^1 x\\,dx" });
    });
    await idle();
    expect(warmSvgMath).toHaveBeenCalledTimes(1);
  });

  it("does nothing for a chat that closes first", async () => {
    const { unmount } = await renderHook(() => useWarmMathRenderer(DISPLAY));
    await unmount();
    await idle(60_000);
    expect(warmSvgMath).not.toHaveBeenCalled();
  });
});

describe("DISPLAY_MATHS_MARKERS", () => {
  it.each([
    "$$x^2$$",
    "\\[x\\]",
    "\\begin{cases}",
    "```math\nx\n```",
    "```answer\n12\n```",
    "\\sum_{k=1}^n k",
    "\\lim_{x \\to 0}",
    "\\binom{5}{2}",
  ])("finds %s", (text) => {
    expect(DISPLAY_MATHS_MARKERS.test(text)).toBe(true);
  });

  it.each(["Inline $x^2$ and $y$.", "A price of $5 and $6.", "\\integer is not maths", "Plain prose."])(
    "leaves %s",
    (text) => {
      expect(DISPLAY_MATHS_MARKERS.test(text)).toBe(false);
    },
  );
});
