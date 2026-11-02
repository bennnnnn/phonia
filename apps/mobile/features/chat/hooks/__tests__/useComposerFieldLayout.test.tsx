import type { LayoutChangeEvent } from "react-native";
import { act, renderHook } from "@testing-library/react-native";

import { useComposerFieldLayout } from "@/features/chat/hooks/useComposerFieldLayout";

const fieldLayout = (width: number) =>
  ({ nativeEvent: { layout: { x: 0, y: 0, width, height: 24 } } }) as LayoutChangeEvent;

const DRAFT = "Plan a weekend in Lisbon";

describe("useComposerFieldLayout", () => {
  it("judges stacking on the rendered text, again when the field beside the buttons changes", async () => {
    const { result } = await renderHook(() =>
      useComposerFieldLayout({ input: DRAFT, draftRevision: 0, fontScale: 1, voiceActive: false }),
    );
    await act(() => result.current.onInputLayout(fieldLayout(280)));
    await act(() => result.current.onTextMeasure({ naturalWidth: 250, height: 24 }));
    expect(result.current.stackedLayout).toBe(false);

    // The buttons beside the text took more room: the same draft no longer fits.
    await act(() => result.current.onInputLayout(fieldLayout(240)));
    expect(result.current.stackedLayout).toBe(true);
  });

  it("does not render for a measure that changes neither the fit nor the line count", async () => {
    let renders = 0;
    const { result } = await renderHook(() => {
      renders += 1;
      return useComposerFieldLayout({ input: DRAFT, draftRevision: 0, fontScale: 1, voiceActive: false });
    });
    await act(() => result.current.onInputLayout(fieldLayout(280)));
    await act(() => result.current.onTextMeasure({ naturalWidth: 200, height: 24 }));
    const measured = renders;

    // The next letter widens the one-line copy; it still fits on one line.
    await act(() => result.current.onTextMeasure({ naturalWidth: 208, height: 24 }));
    expect(renders).toBe(measured);

    // Another line does change the field.
    await act(() => result.current.onTextMeasure({ naturalWidth: 208, height: 48 }));
    expect(renders).toBe(measured + 1);
    expect(result.current.fieldHeight).toBe(60);
  });

  it("reports the extra height a Return line and the stacked buttons add, for the thread to clear", async () => {
    const onInputFrameExtraChange = jest.fn();
    await renderHook(() =>
      useComposerFieldLayout({
        input: "First line\nSecond line",
        draftRevision: 0,
        fontScale: 1,
        voiceActive: false,
        onInputFrameExtraChange,
      }),
    );
    // One Return adds a line and the text stacks over the buttons.
    expect(onInputFrameExtraChange).toHaveBeenLastCalledWith(24 + 36);
  });
});
