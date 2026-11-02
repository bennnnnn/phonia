import { act, renderHook } from "@testing-library/react-native";

import { useChatLayoutMetrics } from "@/features/chat/hooks/useChatLayoutMetrics";

const options = {
  insetsTop: 44,
  insetsBottom: 20,
  windowHeight: 800,
  fontScale: 1,
  keyboardHeight: 0,
  composerHeight: 88,
  attachmentExtra: 0,
  messagesLength: 1,
  streaming: false,
  lastMessageId: "message-1",
};

describe("useChatLayoutMetrics", () => {
  it("uses the minimum initially, then adopts a measured taller header without duplicate updates", async () => {
    const { result } = await renderHook(() => useChatLayoutMetrics(options));
    const initial = result.current;

    expect(initial.headerMinimumHeight).toBe(96);
    expect(initial.headerInset).toBe(96);

    await act(() => initial.onHeaderHeightChange(96));
    expect(result.current).toBe(initial);

    await act(() => initial.onHeaderHeightChange(123.2));
    expect(result.current.headerInset).toBe(124);
    const grown = result.current;

    await act(() => grown.onHeaderHeightChange(124));
    expect(result.current).toBe(grown);
  });
});
