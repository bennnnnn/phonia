import { act, renderHook } from "@testing-library/react-native";

import { useStreamingDraft } from "@/features/chat/context/StreamingDraftContext";
import { publishStreamingDraft } from "@/features/chat/model/streamingDraftStore";

beforeEach(() => {
  jest.useFakeTimers();
  publishStreamingDraft(null);
});
afterEach(() => {
  publishStreamingDraft(null);
  jest.useRealTimers();
});

describe("useStreamingDraft", () => {
  it("reads nothing while not live, and never re-renders for the draft", async () => {
    let renders = 0;
    const hook = await renderHook(() => {
      renders += 1;
      return useStreamingDraft(false);
    });
    await act(async () => {
      jest.advanceTimersByTime(100);
      publishStreamingDraft({ content: "Someone else's reply" });
    });
    expect(hook.result.current).toBeNull();
    expect(renders).toBe(1);
  });

  it("starts from the current draft in the render a row goes live again", async () => {
    const seen: (string | null)[] = [];
    const hook = await renderHook(
      ({ enabled }: { enabled: boolean }) => {
        const draft = useStreamingDraft(enabled);
        seen.push(draft?.content ?? null);
        return draft;
      },
      { initialProps: { enabled: true } },
    );
    await act(async () => {
      jest.advanceTimersByTime(100);
      publishStreamingDraft({ content: "Turn one, partly streamed" });
    });
    expect(hook.result.current?.content).toBe("Turn one, partly streamed");

    // The row's cell is reused for another message; turn one ends, turn two starts.
    await hook.rerender({ enabled: false });
    await act(async () => {
      publishStreamingDraft(null);
      publishStreamingDraft({ content: "Turn two" });
    });
    seen.length = 0;
    await hook.rerender({ enabled: true });
    expect(seen[0]).toBe("Turn two");
    expect(seen).not.toContain("Turn one, partly streamed");
  });
});
