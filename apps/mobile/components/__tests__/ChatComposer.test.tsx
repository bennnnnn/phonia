import { Dimensions, StyleSheet } from "react-native";
import { act, fireEvent, render, waitFor, within } from "@testing-library/react-native";

import { ChatComposer } from "@/features/chat/components/ChatComposer";
import { MATH_KEYBOARD_GAP_FADE_HEIGHT } from "@/features/chat/components/chatComposerStyles";
import { KEY_HEIGHT_MIN, mathPadHeight, padKeyHeight } from "@/lib/math/keyboardPad";
import { darkTheme, lightTheme } from "@/lib/theme";
import { ComposerDraftProvider, useComposerDraftApi } from "@/features/chat/context/ComposerDraftContext";

import { DraftHarness } from "./DraftHarness";

/** The math preview is hidden from screen readers (the text field reads the draft); look inside it. */
const HIDDEN_TOO = { includeHiddenElements: true };

jest.mock("expo-linear-gradient", () => {
  const { View } = jest.requireActual("react-native") as typeof import("react-native");
  return { LinearGradient: View };
});

jest.mock("@/contexts/AuthContext", () => ({
  useAuthToken: () => "t",
}));

jest.mock("@/features/speech/components/VoiceComposerWaveform", () => ({
  VoiceComposerWaveform: () => null,
}));

jest.mock("@/features/speech/components/VoiceMicButton", () => {
  const { View } = jest.requireActual("react-native") as typeof import("react-native");
  return {
    VoiceMicButton: () => <View testID="voice-mic-button" />,
  };
});

jest.mock("@/features/speech/components/LiveTalkButton", () => {
  const { Pressable } = jest.requireActual("react-native") as typeof import("react-native");
  return {
    LiveTalkButton: ({ onPress }: { onPress: () => void }) => (
      <Pressable testID="live-talk-button" onPress={onPress} />
    ),
  };
});

jest.mock("@/features/attachments/components/ComposerAttachmentPreview", () => ({
  ComposerAttachmentPreview: () => null,
}));

// The RN jest preset reports a 2x text size. Sizes here are at the default
// unless a test raises it; the preset's other window metrics stay.
const presetDimensionsGet = Dimensions.get.bind(Dimensions);
let windowFontScale = 1;
jest
  .spyOn(Dimensions, "get")
  .mockImplementation((dim) => ({ ...presetDimensionsGet(dim), fontScale: windowFontScale }));
beforeEach(() => {
  windowFontScale = 1;
});

const baseProps = {
  visible: true,
  streaming: false,
  pendingAttachment: null,
  onRemoveAttachment: jest.fn(),
  onCloseAttachSheet: jest.fn(),
  onPickAttachment: jest.fn(),
  onSend: jest.fn(),
  onStop: jest.fn(),
  isOffline: false,
};

describe("ChatComposer math keyboard", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it.each([
    "What is sqrt{81}?",
    "Let x=-5. Evaluate x^2",
    "Use $x^2$ with a $5 example",
  ])("keeps ordinary typing on the messaging keyboard with the native caret: %s", async (text) => {
    const { getByTestId, queryByTestId } = await render(
      <DraftHarness>
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );
    for (let i = 1; i <= text.length; i += 1) {
      const next = text.slice(0, i);
      await fireEvent.changeText(getByTestId("chat-composer-input"), next);
      const native = getByTestId("chat-composer-input");
      expect(native.props.value).toBe(next);
      expect(native.props.autoCorrect).toBe(true);
      expect(native.props.spellCheck).toBe(true);
      expect(native.props.autoCapitalize).toBe("sentences");
      expect(native.props.selection).toBeUndefined();
      expect(native.props.caretHidden).toBe(false);
      expect(native.props.pointerEvents).toBe("auto");
      expect(queryByTestId("math-draft-preview", HIDDEN_TOO)).toBeNull();
    }
  });

  it("uses messaging input until the math pad is open", async () => {
    const { getByTestId } = await render(<ChatComposer {...baseProps} />);
    const expectMessaging = () => {
      const native = getByTestId("chat-composer-input");
      expect(native.props.autoCorrect).toBe(true);
      expect(native.props.spellCheck).toBe(true);
      expect(native.props.autoCapitalize).toBe("sentences");
    };
    const expectMathEditor = () => {
      const native = getByTestId("chat-composer-input");
      expect(native.props.autoCorrect).toBe(false);
      expect(native.props.spellCheck).toBe(false);
      expect(native.props.autoCapitalize).toBe("none");
    };
    expectMessaging();
    await fireEvent.press(getByTestId("math-keyboard-toggle"));
    expectMathEditor();
    await fireEvent.press(getByTestId("math-keyboard-abc"));
    expectMessaging();
  });

  it("does not enable preview just by opening and closing an empty math pad", async () => {
    const { getByTestId, queryByTestId } = await render(
      <DraftHarness>
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );
    await fireEvent.press(getByTestId("math-keyboard-toggle"));
    await fireEvent.press(getByTestId("math-keyboard-abc"));
    const text = "The price is $5.00";
    for (let i = 1; i <= text.length; i += 1) {
      await fireEvent.changeText(getByTestId("chat-composer-input"), text.slice(0, i));
      expect(getByTestId("chat-composer-input").props.selection).toBeUndefined();
      expect(queryByTestId("math-draft-preview", HIDDEN_TOO)).toBeNull();
    }
  });

  it("keeps a saved native draft literal after switching away from a math draft", async () => {
    let api: ReturnType<typeof useComposerDraftApi>;
    function ApiProbe() {
      api = useComposerDraftApi();
      return null;
    }
    const { getByTestId, queryByTestId } = await render(
      <ComposerDraftProvider>
        <ApiProbe />
        <ChatComposer {...baseProps} />
      </ComposerDraftProvider>,
    );
    await act(() => api.switchThread("literal"));
    await fireEvent.changeText(getByTestId("chat-composer-input"), "The price is $5");
    await act(() => api.switchThread("math"));
    await fireEvent.press(getByTestId("math-keyboard-toggle"));
    await fireEvent.press(getByTestId("math-key-frac"));
    expect(getByTestId("math-draft-preview", HIDDEN_TOO)).toBeTruthy();
    await act(() => api.switchThread("literal"));
    expect(getByTestId("chat-composer-input").props.value).toBe("The price is $5");
    expect(getByTestId("chat-composer-input").props.selection).toBeUndefined();
    expect(queryByTestId("math-draft-preview", HIDDEN_TOO)).toBeNull();
    expect(queryByTestId("math-keyboard-pad")).toBeNull();
    await fireEvent.changeText(getByTestId("chat-composer-input"), "The price is $50");
    expect(getByTestId("chat-composer-input").props.value).toBe("The price is $50");
    expect(queryByTestId("math-draft-preview", HIDDEN_TOO)).toBeNull();
  });

  it("shows a guarded busy send control before streaming starts", async () => {
    const onSend = jest.fn();
    const { getByLabelText } = await render(
      <DraftHarness input="">
        <ChatComposer {...baseProps} sendBusy onSend={onSend} />
      </DraftHarness>,
    );

    const send = getByLabelText("chat.sending");
    expect(send.props.accessibilityState).toEqual({ disabled: true, busy: true });
    await fireEvent.press(send);
    expect(onSend).not.toHaveBeenCalled();
  });

  it("holds Send and shows the + busy while a picked photo is being prepared", async () => {
    const onSend = jest.fn();
    const { getByLabelText, getByTestId, rerender } = await render(
      <DraftHarness input="what is this?">
        <ChatComposer {...baseProps} attachPicking onSend={onSend} />
      </DraftHarness>,
    );
    const send = getByLabelText("chat.send_a11y");
    expect(send.props.accessibilityState).toEqual({ disabled: true, busy: false });
    await fireEvent.press(send);
    expect(onSend).not.toHaveBeenCalled();
    expect(getByTestId("composer-attachment-busy")).toBeTruthy();
    expect(getByTestId("composer-attachment-button").props.accessibilityState).toMatchObject({ busy: true });

    await rerender(
      <DraftHarness input="what is this?">
        <ChatComposer {...baseProps} onSend={onSend} />
      </DraftHarness>,
    );
    await fireEvent.press(getByLabelText("chat.send_a11y"));
    expect(onSend).toHaveBeenCalledTimes(1);
  });

  it("shows an immediate locating status without clearing the draft", async () => {
    const { getByTestId } = await render(
      <DraftHarness input="coffee near me">
        <ChatComposer
          {...baseProps}
          sendBusy
          sendStatus="chat.locating"
        />
      </DraftHarness>,
    );

    expect(getByTestId("chat-composer-input").props.value).toBe("coffee near me");
    expect(getByTestId("composer-send-status").props.children).toBe(
      "chat.locating",
    );
  });

  it("keeps reporting its size while the drawer hides it, so the chat under the drawer keeps its layout", async () => {
    const onInputFrameExtraChange = jest.fn();
    const onMathChromeHeightChange = jest.fn();
    const composer = (visible: boolean) => (
      <DraftHarness input={"First line\nSecond line"}>
        <ChatComposer
          {...baseProps}
          visible={visible}
          sendStatus="chat.locating"
          onInputFrameExtraChange={onInputFrameExtraChange}
          onMathChromeHeightChange={onMathChromeHeightChange}
        />
      </DraftHarness>
    );
    const view = await render(composer(true));
    const extra = onInputFrameExtraChange.mock.calls.at(-1)?.[0];
    const chrome = onMathChromeHeightChange.mock.calls.at(-1)?.[0];
    expect(extra).toBeGreaterThan(0);
    expect(chrome).toBeGreaterThan(0);
    onInputFrameExtraChange.mockClear();
    onMathChromeHeightChange.mockClear();

    await view.rerender(composer(false));
    expect(view.queryByTestId("chat-composer")).toBeNull();
    expect(onInputFrameExtraChange).not.toHaveBeenCalled();
    expect(onMathChromeHeightChange).not.toHaveBeenCalled();
  });

  it("returns an expanded multiline input to its default height after send", async () => {
    function SendClearsDraft() {
      const draft = useComposerDraftApi();
      return <ChatComposer {...baseProps} onSend={() => draft.setInput("")} />;
    }

    const { getByTestId, getByLabelText } = await render(
      <DraftHarness input="A long message that wraps across several lines in the composer before it is sent.">
        <SendClearsDraft />
      </DraftHarness>,
    );
    const composerInput = getByTestId("chat-composer-input");

    await fireEvent(composerInput, "contentSizeChange", {
      nativeEvent: { contentSize: { width: 240, height: 112 } },
    });
    expect(getByTestId("chat-composer-input")).toHaveStyle({ height: 112, paddingTop: 0 });

    await fireEvent.press(getByLabelText("chat.send_a11y"));

    await waitFor(() => {
      expect(getByTestId("chat-composer-input").props.value).toBe("");
      expect(getByTestId("chat-composer-input")).toHaveStyle({ height: 24 });
    });
  });

  it("leaves the text field its own screen-reader element", async () => {
    // iOS reads an accessible view as one element and hides what is inside it: a text
    // field under one would be read as a role-less "Message" with no draft and no editing.
    const { getByTestId } = await render(
      <DraftHarness>
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );
    const input = getByTestId("chat-composer-input");
    const wrappers: string[] = [];
    for (let node = input.parent; node; node = node.parent) {
      if (node.props.accessible === true) wrappers.push(node.props.testID ?? String(node.type));
    }
    expect(wrappers).toEqual([]);
  });

  it("grows the field when a leading Return adds a line", async () => {

    const { getByTestId } = await render(
      <DraftHarness>
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );
    const composerInput = getByTestId("chat-composer-input");

    expect(getByTestId("composer-input-row")).toHaveStyle({ alignItems: "center" });
    expect(composerInput.props.placeholder).toBe("chat.placeholder");
    expect(composerInput.props.accessibilityLabel).toBe("chat.placeholder");
    expect(composerInput.props.maxFontSizeMultiplier).toBe(1.5);

    await fireEvent.changeText(composerInput, "\n");
    await fireEvent(composerInput, "contentSizeChange", {
      nativeEvent: { contentSize: { width: 240, height: 50 } },
    });

    expect(getByTestId("chat-composer-input").props.value).toBe("\n");
    expect(getByTestId("chat-composer-input").props.placeholder).toBe("chat.placeholder");
    expect(getByTestId("chat-composer-input")).toHaveStyle({ height: 48, paddingTop: 0 });
    expect(getByTestId("composer-input-row")).toHaveStyle({ alignItems: "flex-end" });
  });

  it("grows to the next line when text reaches the end of the field", async () => {
    const { getByTestId } = await render(
      <DraftHarness input={"a".repeat(40)}>
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );
    expect(getByTestId("chat-composer-input")).toHaveStyle({ height: 24 });

    await fireEvent(getByTestId("chat-composer-input"), "layout", {
      nativeEvent: { layout: { x: 0, y: 0, width: 200, height: 44 } },
    });

    expect(getByTestId("chat-composer-input")).toHaveStyle({
      height: 48,
      paddingTop: 0,
    });
  });

  it("preserves leading indentation while typing a code block", async () => {

    const { getByTestId } = await render(
      <DraftHarness>
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );
    const composerInput = getByTestId("chat-composer-input");

    await fireEvent.changeText(composerInput, " ");
    expect(getByTestId("chat-composer-input").props.value).toBe(" ");
    await fireEvent.changeText(getByTestId("chat-composer-input"), "  const answer = 42;");
    expect(getByTestId("chat-composer-input").props.value).toBe("  const answer = 42;");
  });

  it("bottom-aligns controls only after visible multiline text is entered", async () => {
    const { getByTestId } = await render(
      <DraftHarness input={"First line\nSecond line"}>
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );

    await fireEvent(getByTestId("chat-composer-input"), "contentSizeChange", {
      nativeEvent: { contentSize: { width: 240, height: 50 } },
    });

    expect(getByTestId("composer-input-row")).toHaveStyle({ alignItems: "flex-end" });
  });

  it("puts text beside the + until it wraps, then gives it the full width", async () => {
    const view = await render(
      <DraftHarness input="Hello there">
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );
    const row = () => view.getByTestId("composer-input-row");
    await fireEvent(view.getByTestId("chat-composer-input"), "layout", {
      nativeEvent: { layout: { width: 200, height: 24 } },
    });
    expect(within(row()).getByTestId("composer-attachment-button")).toBeTruthy();
    expect(view.queryByTestId("composer-stacked-controls")).toBeNull();

    await view.rerender(
      <DraftHarness input={"A long message that wraps ".repeat(4)}>
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );
    const controls = view.getByTestId("composer-stacked-controls");
    expect(within(controls).getByTestId("composer-attachment-button")).toBeTruthy();
    expect(within(controls).getByLabelText("chat.send_a11y")).toBeTruthy();
    expect(within(row()).queryByTestId("composer-attachment-button")).toBeNull();

    // The stacked field is wider; wrapping is still judged beside the buttons.
    await fireEvent(view.getByTestId("chat-composer-input"), "layout", {
      nativeEvent: { layout: { width: 320, height: 72 } },
    });
    expect(view.getByTestId("composer-stacked-controls")).toBeTruthy();

    await view.rerender(
      <DraftHarness input="Hello there">
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );
    expect(view.queryByTestId("composer-stacked-controls")).toBeNull();
    expect(within(row()).getByTestId("composer-attachment-button")).toBeTruthy();
  });

  it("offers a full-height editor when the multiline input reaches its limit", async () => {
    const { getByTestId, getByLabelText } = await render(
      <DraftHarness input={"A long draft\n".repeat(20)}>
        <ChatComposer
          {...baseProps}
        />
      </DraftHarness>,
    );
    const composerInput = getByTestId("chat-composer-input");

    await fireEvent(composerInput, "contentSizeChange", {
      nativeEvent: { contentSize: { width: 240, height: 190 } },
    });

    expect(composerInput).toHaveStyle({ height: 144, paddingTop: 0 });
    expect(getByTestId("composer-expand").props.accessibilityState).toEqual({
      expanded: false,
    });

    await fireEvent.press(getByLabelText("rich.expand"));

    expect(getByTestId("composer-expand").props.accessibilityState).toEqual({
      expanded: true,
    });
    expect(getByTestId("chat-composer")).toHaveStyle({ top: 8 });
    expect(getByTestId("chat-composer-input")).toHaveStyle({
      flex: 1,
      minHeight: 0,
    });
    expect(getByLabelText("rich.collapse")).toBeTruthy();
  });

  it("uses Ionicon send and stop glyphs instead of text arrows", async () => {
    const { queryByText, getByLabelText, rerender } = await render(
      <DraftHarness input="hi">
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );
    expect(queryByText("↑")).toBeNull();
    expect(getByLabelText("chat.send_a11y")).toBeTruthy();

    await rerender(
      <DraftHarness input="hi">
        <ChatComposer {...baseProps} streaming />
      </DraftHarness>,
    );
    expect(queryByText("■")).toBeNull();
    expect(getByLabelText("chat.stop_a11y")).toBeTruthy();
  });

  it("shows the math keyboard button on an empty composer, immediately before the mic", async () => {
    const { getByTestId } = await render(
      <DraftHarness input="">
        <ChatComposer
          {...baseProps}
          voiceAvailable
          onVoicePress={jest.fn()}
        />
      </DraftHarness>,
    );
    const row = getByTestId("composer-input-row");
    const ids: string[] = [];
    const walk = (node: { props?: { testID?: string }; children?: unknown[] }) => {
      const id = node.props?.testID;
      if (typeof id === "string") ids.push(id);
      for (const child of node.children ?? []) {
        if (child && typeof child === "object") walk(child as typeof node);
      }
    };
    walk(row);
    const math = ids.indexOf("math-keyboard-toggle");
    const mic = ids.indexOf("voice-mic-button");
    expect(math).toBeGreaterThanOrEqual(0);
    expect(mic).toBe(math + 1);
  });

  it("toggles the symbol bar and inserts a fraction at the caret", async () => {
    const onInput = jest.fn();
    const { getByTestId, queryByTestId } = await render(
      <DraftHarness onInput={onInput}>
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );

    expect(queryByTestId("math-key-frac")).toBeNull();
    await fireEvent.press(getByTestId("math-keyboard-toggle"));
    expect(getByTestId("math-keyboard-pad")).toBeTruthy();
    expect(queryByTestId("math-keyboard-toggle")).toBeNull();
    expect(getByTestId("math-keyboard-abc")).toBeTruthy();
    expect(getByTestId("math-composer-caret")).toBeTruthy();
    expect(getByTestId("math-key-frac")).toBeTruthy();

    await fireEvent.press(getByTestId("math-key-frac"));
    expect(onInput).toHaveBeenCalledWith("$\\frac{}{}$");
    expect(getByTestId("math-keyboard-pad")).toBeTruthy();
  });

  it("switches tabs to reach trig functions", async () => {
    const onInput = jest.fn();
    const { getByTestId, queryByTestId } = await render(
      <DraftHarness onInput={onInput}>
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );
    await fireEvent.press(getByTestId("math-keyboard-toggle"));
    expect(queryByTestId("math-key-sin")).toBeNull();
    await fireEvent.press(getByTestId("math-keyboard-tab-trig"));
    expect(getByTestId("math-key-sin")).toBeTruthy();
    await fireEvent.press(getByTestId("math-key-sin"));
    expect(onInput).toHaveBeenCalledWith("$\\sin()$");
  });

  it("renders a trig function once, not as a doubled name", async () => {
    const { getByTestId, getAllByTestId } = await render(
      <DraftHarness>
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );
    await fireEvent.press(getByTestId("math-keyboard-toggle"));
    await fireEvent.press(getByTestId("math-keyboard-tab-trig"));
    await fireEvent.press(getByTestId("math-key-cos"));
    expect(getAllByTestId("math-group", HIDDEN_TOO)).toHaveLength(1);
  });

  it("sends a convert prompt on Ask, not a computed answer", async () => {
    const onInput = jest.fn();
    const onSend = jest.fn();
    const { getByTestId, queryByTestId } = await render(
      <DraftHarness onInput={onInput}>
        <ChatComposer {...baseProps} onSend={onSend} />
      </DraftHarness>,
    );
    await fireEvent.press(getByTestId("math-keyboard-toggle"));
    await fireEvent.press(getByTestId("math-keyboard-tab-converter"));
    expect(getByTestId("math-converter")).toBeTruthy();
    expect(getByTestId("math-converter-from-value").props.children).toBe("1");
    expect(getByTestId("math-converter-to-value").props.children).toBe("100");
    await fireEvent.press(getByTestId("math-converter-5"));
    expect(getByTestId("math-converter-from-value").props.children).toBe("5");
    expect(getByTestId("math-converter-to-value").props.children).toBe("500");
    await fireEvent.press(getByTestId("math-converter-ask"));
    expect(onSend).toHaveBeenCalledWith("convert 5 m to cm");
    expect(onInput).not.toHaveBeenCalledWith("convert 5 m to cm");
    expect(queryByTestId("math-converter")).toBeNull();
  });

  it("gives every page, the converter included, one key height of at least 44pt", async () => {
    const { getByTestId } = await render(<ChatComposer {...baseProps} />);
    await fireEvent.press(getByTestId("math-keyboard-toggle"));
    const flat = (id: string) => {
      const style = getByTestId(id).props.style;
      return StyleSheet.flatten(typeof style === "function" ? style({ pressed: false }) : style);
    };
    const keyHeight = padKeyHeight(mathPadHeight(0));
    expect(keyHeight).toBeGreaterThanOrEqual(KEY_HEIGHT_MIN);
    expect(getByTestId("math-keyboard-tab-basics")).toHaveStyle({ minHeight: 44 });
    expect(getByTestId("math-keyboard-abc")).toHaveStyle({ minHeight: 44 });
    for (const id of ["math-key-frac", "math-key-digit-7", "math-key-left", "math-key-right"]) {
      expect(flat(id).height).toBe(keyHeight);
    }
    await fireEvent.press(getByTestId("math-keyboard-tab-calc"));
    expect(flat("math-key-partial-x").height).toBe(keyHeight);
    await fireEvent.press(getByTestId("math-keyboard-tab-symbols"));
    expect(flat("math-key-cup").height).toBe(keyHeight);

    await fireEvent.press(getByTestId("math-keyboard-tab-converter"));
    for (const id of ["math-converter-0", "math-converter-dot", "math-converter-ask"]) {
      expect(flat(id).height).toBe(keyHeight);
    }
    expect(flat("math-converter-ask").flex).toBe(2);
    expect(flat("math-converter-from-unit").height).toBe(keyHeight);
    expect(getByTestId("math-converter-swap")).toHaveStyle({ minWidth: 44, minHeight: 44 });

    await fireEvent.press(getByTestId("math-converter-from-unit"));
    expect(getByTestId("math-converter-picker-close")).toHaveStyle({ minWidth: 44, minHeight: 44 });
    expect(getByTestId("math-converter-cat-length")).toHaveStyle({ minHeight: 44 });
  });
  it("draws every key white with the same ink, delete and clear included", async () => {
    const { getByTestId } = await render(<ChatComposer {...baseProps} />);
    await fireEvent.press(getByTestId("math-keyboard-toggle"));
    const flat = (style: unknown) =>
      StyleSheet.flatten(typeof style === "function" ? style({ pressed: false }) : style);
    const ink = [lightTheme.text, darkTheme.text];
    const white = [lightTheme.bg, darkTheme.bg];
    const back = getByTestId("math-key-backspace");
    expect(white).toContain(flat(back.props.style).backgroundColor);
    expect(ink).toContain(within(back).getByTestId("math-key-backspace-icon").props.color);
    await fireEvent.press(getByTestId("math-keyboard-tab-converter"));
    for (const id of ["math-converter-5", "math-converter-ask", "math-converter-AC", "math-converter-±"]) {
      expect(white).toContain(flat(getByTestId(id).props.style).backgroundColor);
    }
    const clear = within(getByTestId("math-converter-AC")).getByText("chat.math_converter_clear");
    expect(ink).toContain(flat(clear.props.style).color);
    const backIcon = within(getByTestId("math-converter-back")).getByTestId("math-converter-back-icon");
    expect(backIcon.props.name).toBe("backspace");
    expect(ink).toContain(backIcon.props.color);
  });
  it("leaves the thread free to scroll while the math keyboard is open", async () => {
    const { getByTestId, queryByTestId } = await render(<ChatComposer {...baseProps} />);
    await fireEvent.press(getByTestId("math-keyboard-toggle"));
    expect(getByTestId("math-keyboard-pad")).toBeTruthy();
    const padHeight = StyleSheet.flatten(getByTestId("math-keyboard-pad").props.style).height;
    const fade = StyleSheet.flatten(getByTestId("composer-scroll-fade").props.style);
    expect(fade.top).toBeUndefined();
    expect(fade.bottom).toBe(padHeight);
    expect(fade.height).toBe(MATH_KEYBOARD_GAP_FADE_HEIGHT);
    expect(StyleSheet.flatten(getByTestId("chat-composer").props.style).top).toBeUndefined();
    expect(queryByTestId("math-keyboard-dismiss")).toBeNull();
    await fireEvent.press(getByTestId("math-keyboard-abc"));
    expect(queryByTestId("math-keyboard-pad")).toBeNull();
    expect(queryByTestId("composer-scroll-fade")).toBeNull();
    await fireEvent(getByTestId("chat-composer-input"), "focus");
    expect(queryByTestId("math-keyboard-pad")).toBeNull();
  });

  it("minimizes the math keyboard while a reply is streaming", async () => {
    const onStop = jest.fn();
    const { getByTestId, getByLabelText, queryByTestId, rerender } = await render(
      <ChatComposer {...baseProps} onStop={onStop} />,
    );
    await fireEvent.press(getByTestId("math-keyboard-toggle"));
    expect(getByTestId("math-keyboard-pad")).toBeTruthy();

    await rerender(<ChatComposer {...baseProps} streaming onStop={onStop} />);
    expect(queryByTestId("math-keyboard-pad")).toBeNull();
    expect(getByLabelText("chat.stop_a11y")).toBeTruthy();

    await fireEvent.press(getByTestId("math-keyboard-toggle"));
    expect(queryByTestId("math-keyboard-pad")).toBeNull();
    await fireEvent.press(getByLabelText("chat.stop_a11y"));
    expect(onStop).toHaveBeenCalled();
  });

  it("reopens the Converter tab after ABC", async () => {
    const { getByTestId, queryByTestId } = await render(<ChatComposer {...baseProps} />);
    await fireEvent.press(getByTestId("math-keyboard-toggle"));
    await fireEvent.press(getByTestId("math-keyboard-tab-converter"));
    expect(getByTestId("math-converter")).toBeTruthy();
    await fireEvent.press(getByTestId("math-keyboard-abc"));
    expect(queryByTestId("math-converter")).toBeNull();
    await fireEvent.press(getByTestId("math-keyboard-toggle"));
    expect(getByTestId("math-converter")).toBeTruthy();
  });

  it("opens the unit list in a sheet, not inside the pad", async () => {
    const { getByTestId, queryByTestId } = await render(<ChatComposer {...baseProps} />);
    await fireEvent.press(getByTestId("math-keyboard-toggle"));
    await fireEvent.press(getByTestId("math-keyboard-tab-converter"));
    expect(queryByTestId("math-converter-picker")).toBeNull();
    await fireEvent.press(getByTestId("math-converter-from-unit"));
    expect(getByTestId("math-converter-picker")).toBeTruthy();
    expect(getByTestId("math-converter-unit-km")).toBeTruthy();
    expect(getByTestId("math-converter-numpad")).toBeTruthy();
    const lengthHeight = StyleSheet.flatten(getByTestId("math-converter-picker").props.style).height;
    await fireEvent.press(getByTestId("math-converter-cat-speed"));
    expect(getByTestId("math-converter-unit-kmh")).toBeTruthy();
    await fireEvent.press(getByTestId("math-converter-cat-temperature"));
    expect(getByTestId("math-converter-unit-c")).toBeTruthy();
    expect(StyleSheet.flatten(getByTestId("math-converter-picker").props.style).height).toBe(
      lengthHeight,
    );
  });

  it("keeps digits and operators on Basics, and every page on the same grid", async () => {
    const { getByTestId, queryByTestId } = await render(<ChatComposer {...baseProps} />);
    await fireEvent.press(getByTestId("math-keyboard-toggle"));
    for (const id of ["digit-7", "digit-0", "plus", "minus", "times", "div", "eq", "var-x", "frac"]) {
      expect(getByTestId(`math-key-${id}`)).toBeTruthy();
    }
    expect(queryByTestId("math-keyboard-123")).toBeNull();
    for (const tab of ["symbols", "trig", "calc", "greek"]) {
      await fireEvent.press(getByTestId(`math-keyboard-tab-${tab}`));
      expect(getByTestId("math-key-left")).toBeTruthy();
      expect(getByTestId("math-key-right")).toBeTruthy();
      expect(getByTestId("math-key-backspace")).toBeTruthy();
      expect(queryByTestId("math-key-digit-7")).toBeNull();
    }
    await fireEvent.press(getByTestId("math-keyboard-tab-trig"));
    for (const id of ["arccot", "sech", "theta", "deg", "pi-over-2", "two-pi"]) {
      expect(getByTestId(`math-key-${id}`)).toBeTruthy();
    }
    await fireEvent.press(getByTestId("math-keyboard-tab-calc"));
    for (const id of ["der", "oint", "binom", "perm", "e-const", "prime"]) {
      expect(getByTestId(`math-key-${id}`)).toBeTruthy();
    }
  });
});
