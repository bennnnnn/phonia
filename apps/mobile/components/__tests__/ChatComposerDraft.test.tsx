import { Dimensions } from "react-native";
import * as Clipboard from "expo-clipboard";
import { configure, fireEvent, render, within, waitFor } from "@testing-library/react-native";

import { ChatComposer } from "@/features/chat/components/ChatComposer";
import { DraftHarness } from "./DraftHarness";

// These tests drive the math preview, which is hidden from screen readers (the text
// field reads the draft), so queries look inside hidden views.
configure({ defaultIncludeHiddenElements: true });

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

jest.mock("@/features/speech/components/VoiceMicButton", () => ({
  VoiceMicButton: () => null,
}));

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

  it("renders the draft as math, not raw LaTeX", async () => {
    const { getByTestId } = await render(
      <DraftHarness input={"$\\frac{1}{2}$"}>
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );
    await fireEvent.press(getByTestId("math-keyboard-toggle"));
    expect(getByTestId("math-draft-preview")).toBeTruthy();
    expect(getByTestId("math-frac")).toBeTruthy();
    expect(getByTestId("math-vinculum")).toBeTruthy();
  });

  it("does not render a pasted physics word problem as stacked math", async () => {
    const pasted =
      "A car starts from rest and accelerates at a constant rate of 1.2 m/s². How long does it take the car to travel a distance of 500 meters?";
    const { queryByTestId } = await render(
      <DraftHarness input={pasted}>
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );
    expect(queryByTestId("math-draft-preview")).toBeNull();
  });

  it("puts the caret in the numerator, then → continues the expression after the fraction", async () => {
    let latest = "";
    const { getByTestId } = await render(
      <DraftHarness onInput={(text) => { latest = text; }}>
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );
    await fireEvent.press(getByTestId("math-keyboard-toggle"));
    await fireEvent.press(getByTestId("math-key-frac"));
    expect(getByTestId("math-slot-num-caret")).toBeTruthy();
    expect(getByTestId("math-slot-den-placeholder")).toBeTruthy();
    await fireEvent.press(getByTestId("math-key-digit-1"));
    await fireEvent.press(getByTestId("math-slot-den"));
    await fireEvent.press(getByTestId("math-key-digit-2"));
    expect(getByTestId("math-slot-num")).toBeTruthy();
    expect(getByTestId("math-slot-den")).toBeTruthy();
    await fireEvent.press(getByTestId("math-key-right"));
    await fireEvent.press(getByTestId("math-key-times"));
    await fireEvent.press(getByTestId("math-key-digit-2"));
    expect(latest).toBe("$\\frac{1}{2}\\times 2$");
    expect(getByTestId("math-slot-after")).toBeTruthy();
  });

  it("tabs to the denominator and back to the numerator", async () => {
    const { getByTestId, queryByTestId } = await render(
      <DraftHarness>
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );
    await fireEvent.press(getByTestId("math-keyboard-toggle"));
    await fireEvent.press(getByTestId("math-key-frac"));
    expect(getByTestId("math-slot-num-caret")).toBeTruthy();
    await fireEvent.press(getByTestId("math-slot-den"));
    expect(getByTestId("math-slot-den-caret")).toBeTruthy();
    expect(queryByTestId("math-slot-num-caret")).toBeNull();
    await fireEvent.press(getByTestId("math-slot-num"));
    expect(getByTestId("math-slot-num-caret")).toBeTruthy();
  });

  it("does not show raw latex after deleting an empty cos", async () => {
    let latest = "";
    const { getByTestId, queryByText } = await render(
      <DraftHarness onInput={(text) => { latest = text; }}>
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );
    await fireEvent.press(getByTestId("math-keyboard-toggle"));
    await fireEvent.press(getByTestId("math-keyboard-tab-trig"));
    await fireEvent.press(getByTestId("math-key-cos"));
    await fireEvent.press(getByTestId("math-key-backspace"));
    expect(latest).not.toMatch(/\\cos/);
    expect(queryByText("\\cos")).toBeNull();
  });

  it("shows a tappable box for square root, not only for fractions", async () => {
    const { getByTestId } = await render(
      <DraftHarness>
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );
    await fireEvent.press(getByTestId("math-keyboard-toggle"));
    await fireEvent.press(getByTestId("math-key-sqrt"));
    expect(getByTestId("math-slot-sqrt-caret")).toBeTruthy();
  });

  it("keeps the radical bar after a digit is typed into the root", async () => {
    const { getByTestId, queryByText } = await render(
      <DraftHarness>
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );
    await fireEvent.press(getByTestId("math-keyboard-toggle"));
    await fireEvent.press(getByTestId("math-key-sqrt"));
    await fireEvent.press(getByTestId("math-key-digit-8"));
    expect(getByTestId("math-sqrt")).toBeTruthy();
    expect(getByTestId("math-radical-glyph")).toBeTruthy();
    expect(getByTestId("math-sqrt-radicand")).toBeTruthy();
    // The draft draws the radical; the √ text belongs only to the keys.
    expect(within(getByTestId("math-draft-preview")).queryByText("√")).toBeNull();
    expect(getByTestId("math-slot-sqrt")).toBeTruthy();
    expect(queryByText(/\\sqrt/)).toBeNull();
  });

  it("ⁿ√ opens an nth-root index box", async () => {
    const { getByTestId } = await render(
      <DraftHarness>
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );
    await fireEvent.press(getByTestId("math-keyboard-toggle"));
    await fireEvent.press(getByTestId("math-key-nroot"));
    expect(getByTestId("math-slot-nroot-index")).toBeTruthy();
  });

  it("moves into the radicand after filling the nth-root index with π", async () => {
    const { getByTestId, queryByTestId } = await render(
      <DraftHarness>
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );
    await fireEvent.press(getByTestId("math-keyboard-toggle"));
    await fireEvent.press(getByTestId("math-key-nroot"));
    expect(getByTestId("math-slot-nroot-index-caret")).toBeTruthy();
    await fireEvent.press(getByTestId("math-key-pi"));
    expect(queryByTestId("math-slot-nroot-index-caret")).toBeNull();
    expect(getByTestId("math-slot-sqrt-caret")).toBeTruthy();
  });

  it("second ⁿ√ tap moves from a filled index into the radicand", async () => {
    const { getByTestId } = await render(
      <DraftHarness>
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );
    await fireEvent.press(getByTestId("math-keyboard-toggle"));
    await fireEvent.press(getByTestId("math-key-nroot"));
    await fireEvent.press(getByTestId("math-key-digit-3"));
    expect(getByTestId("math-slot-nroot-index-caret-end")).toBeTruthy();
    await fireEvent.press(getByTestId("math-key-nroot"));
    expect(getByTestId("math-slot-sqrt-caret")).toBeTruthy();
  });

  it("° on an empty composer inserts a base box", async () => {
    let latest = "";
    const { getByTestId } = await render(
      <DraftHarness onInput={(text) => { latest = text; }}>
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );
    await fireEvent.press(getByTestId("math-keyboard-toggle"));
    await fireEvent.press(getByTestId("math-keyboard-tab-trig"));
    await fireEvent.press(getByTestId("math-key-deg"));
    expect(latest).toBe("$^{\\circ}$");
    await fireEvent.press(getByTestId("math-keyboard-tab-basics"));
    await fireEvent.press(getByTestId("math-key-digit-3"));
    expect(latest).toBe("$3^{\\circ}$");
  });

  it("logₙ auto-advances from the base into the argument after π", async () => {
    let latest = "";
    const { getByTestId } = await render(
      <DraftHarness onInput={(text) => { latest = text; }}>
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );
    await fireEvent.press(getByTestId("math-keyboard-toggle"));
    await fireEvent.press(getByTestId("math-keyboard-tab-calc"));
    await fireEvent.press(getByTestId("math-key-logn"));
    await fireEvent.press(getByTestId("math-keyboard-tab-basics"));
    await fireEvent.press(getByTestId("math-key-pi"));
    expect(latest).toBe("$\\log_{\\pi }()$");
    expect(getByTestId("math-slot-group-caret")).toBeTruthy();
  });

  it("types a comma and y from the number pad", async () => {
    const { getByTestId } = await render(
      <DraftHarness>
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );
    await fireEvent.press(getByTestId("math-keyboard-toggle"));
    await fireEvent.press(getByTestId("math-key-var-y"));
    await fireEvent.press(getByTestId("math-key-comma"));
    expect(getByTestId("chat-composer-input").props.value).toBe("$y,$");
  });

  it("shows a gray box for the empty exponent until it is focused", async () => {
    const { getByTestId, queryByTestId } = await render(
      <DraftHarness>
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );
    await fireEvent.press(getByTestId("math-keyboard-toggle"));
    await fireEvent.press(getByTestId("math-key-sup"));
    expect(getByTestId("math-slot-sup-caret")).toBeTruthy();
    expect(queryByTestId("math-slot-sup-placeholder")).toBeNull();
  });

  it("xⁿ on an empty composer shows a base x and an exponent box", async () => {
    let latest = "";
    const { getByTestId } = await render(
      <DraftHarness onInput={(text) => { latest = text; }}>
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );
    await fireEvent.press(getByTestId("math-keyboard-toggle"));
    await fireEvent.press(getByTestId("math-key-sup"));
    expect(latest).toBe("$x^{}$");
    expect(getByTestId("math-draft-preview")).toBeTruthy();
    expect(getByTestId("math-sup")).toBeTruthy();
    expect(getByTestId("math-slot-sup-caret")).toBeTruthy();
  });

  it("shows a caret in the subscript box", async () => {
    const { getByTestId } = await render(
      <DraftHarness>
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );
    await fireEvent.press(getByTestId("math-keyboard-toggle"));
    await fireEvent.press(getByTestId("math-key-sub"));
    expect(getByTestId("math-slot-sub-caret")).toBeTruthy();
  });

  it("moves the blue caret to the denominator when that box is tapped", async () => {
    const { getByTestId, queryByTestId } = await render(
      <DraftHarness>
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );
    await fireEvent.press(getByTestId("math-keyboard-toggle"));
    await fireEvent.press(getByTestId("math-key-frac"));
    expect(getByTestId("math-slot-num-caret")).toBeTruthy();
    expect(getByTestId("math-slot-den-placeholder")).toBeTruthy();
    await fireEvent.press(getByTestId("math-slot-den"));
    expect(queryByTestId("math-slot-num-caret")).toBeNull();
    expect(getByTestId("math-slot-num-placeholder")).toBeTruthy();
    expect(getByTestId("math-slot-den-caret")).toBeTruthy();
  });

  it("backspaces a fraction without showing raw LaTeX", async () => {
    let latest = "";
    const { getByTestId, queryByTestId } = await render(
      <DraftHarness onInput={(text) => { latest = text; }}>
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );
    await fireEvent.press(getByTestId("math-keyboard-toggle"));
    await fireEvent.press(getByTestId("math-key-frac"));
    await fireEvent.press(getByTestId("math-key-digit-8"));
    await fireEvent.press(getByTestId("math-slot-den"));
    await fireEvent.press(getByTestId("math-key-digit-8"));
    await fireEvent.press(getByTestId("math-key-backspace"));
    expect(latest).toBe("$\\frac{8}{}$");
    expect(getByTestId("math-frac")).toBeTruthy();
    await fireEvent.press(getByTestId("math-key-backspace"));
    expect(latest).toBe("$\\frac{}{}$");
    await fireEvent.press(getByTestId("math-key-backspace"));
    expect(latest).toBe("");
    expect(queryByTestId("math-draft-preview")).toBeNull();
  });

  it("lets you tap the front of the draft and delete the first digit", async () => {
    let latest = "";
    const { getByTestId } = await render(
      <DraftHarness onInput={(text) => { latest = text; }}>
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );
    await fireEvent.press(getByTestId("math-keyboard-toggle"));
    await fireEvent.press(getByTestId("math-key-frac"));
    await fireEvent.press(getByTestId("math-key-digit-8"));
    await fireEvent.press(getByTestId("math-slot-den"));
    await fireEvent.press(getByTestId("math-key-digit-8"));
    await fireEvent.press(getByTestId("math-slot-before"));
    expect(getByTestId("math-slot-before-caret")).toBeTruthy();
    await fireEvent.press(getByTestId("math-key-backspace"));
    expect(latest).toBe("$\\frac{}{8}$");
  });

  it("inserts at the tapped end of the draft, not the start", async () => {
    let latest = "$|5|99$";
    const { getByTestId, queryByTestId } = await render(
      <DraftHarness input="$|5|99$" onInput={(text) => { latest = text; }}>
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );
    await fireEvent.press(getByTestId("math-keyboard-toggle"));
    expect(getByTestId("math-slot-before-caret")).toBeTruthy();
    expect(queryByTestId("math-slot-after-caret")).toBeNull();
    await fireEvent.press(getByTestId("math-slot-after"));
    expect(queryByTestId("math-slot-before-caret")).toBeNull();
    expect(getByTestId("math-slot-after-caret")).toBeTruthy();
    await fireEvent.press(getByTestId("math-key-digit-7"));
    expect(latest).toBe("$|5|997$");
  });

  it("ABC keeps the visual fraction and parks the caret after it", async () => {
    let latest = "";
    const { getByTestId, queryByTestId } = await render(
      <DraftHarness onInput={(text) => { latest = text; }}>
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );
    await fireEvent.press(getByTestId("math-keyboard-toggle"));
    await fireEvent.press(getByTestId("math-key-frac"));
    await fireEvent.press(getByTestId("math-key-digit-9"));
    expect(getByTestId("math-slot-num-caret-end")).toBeTruthy();
    await fireEvent.press(getByTestId("math-keyboard-abc"));
    expect(getByTestId("math-draft-preview")).toBeTruthy();
    expect(getByTestId("math-frac")).toBeTruthy();
    expect(queryByTestId("math-key-frac")).toBeNull();
    expect(queryByTestId("math-slot-num-caret-end")).toBeNull();
    expect(getByTestId("math-slot-after-caret")).toBeTruthy();
    await fireEvent.press(getByTestId("math-slot-before"));
    expect(getByTestId("math-slot-before-caret")).toBeTruthy();
    const before = latest;
    const denTyped = before.replace("}{}", "}{g}");
    await fireEvent.changeText(getByTestId("chat-composer-input"), denTyped);
    expect(latest.startsWith("g")).toBe(true);
    expect(latest).toContain("\\frac{9}{}");
    expect(latest).not.toContain("\\frac{9}{g}");
  });

  it("hides the bar when toggled off", async () => {
    const { getByTestId, queryByTestId } = await render(<ChatComposer {...baseProps} />);
    await fireEvent.press(getByTestId("math-keyboard-toggle"));
    expect(getByTestId("math-key-frac")).toBeTruthy();
    await fireEvent.press(getByTestId("math-keyboard-abc"));
    expect(queryByTestId("math-key-frac")).toBeNull();
  });

  it("rewrites × through the math-bar Paste control", async () => {
    (Clipboard.getStringAsync as jest.Mock).mockResolvedValue("2 × 3");
    const onInput = jest.fn();
    const { getByTestId } = await render(
      <DraftHarness onInput={onInput}>
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );
    await fireEvent.press(getByTestId("math-keyboard-toggle"));
    await fireEvent.press(getByTestId("math-keyboard-paste"));
    await waitFor(() => {
      expect(onInput).toHaveBeenCalledWith("$2 \\times 3$");
    });
  });

  it("does not offer the math scanner just because the composer focused", async () => {
    (Clipboard.getStringAsync as jest.Mock).mockResolvedValue("");
    (Clipboard.hasImageAsync as jest.Mock).mockResolvedValue(true);
    const { getByTestId, queryByText } = await render(
      <ChatComposer {...baseProps} onOpenMathScanner={jest.fn()} />,
    );
    fireEvent(getByTestId("chat-composer-input"), "focus");
    await waitFor(() => {
      expect(queryByText("chat.math_paste_scan_hint")).toBeNull();
    });
  });

  it("does not show a token count under a long draft", async () => {
    const { queryByText } = await render(
      <DraftHarness input={"a".repeat(400)}>
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );
    expect(queryByText(/tokens/i)).toBeNull();
  });

  it("shows live talk when a handler is provided", async () => {
    const onLiveTalkPress = jest.fn();
    const { getByTestId } = await render(
      <ChatComposer {...baseProps} onLiveTalkPress={onLiveTalkPress} />,
    );
    fireEvent.press(getByTestId("live-talk-button"));
    expect(onLiveTalkPress).toHaveBeenCalled();
  });

  it("hides live talk when the send button is showing", async () => {
    const { queryByTestId } = await render(
      <DraftHarness input="hello">
        <ChatComposer {...baseProps} onLiveTalkPress={jest.fn()} />
      </DraftHarness>,
    );
    expect(queryByTestId("live-talk-button")).toBeNull();
  });

  it("keeps type and attach and puts mute next to close in live talk", async () => {
    const onYield = jest.fn();
    const { getByTestId, getByLabelText, queryByTestId } = await render(
      <ChatComposer
        {...baseProps}
        onLiveTalkPress={jest.fn()}
        liveTalkChrome={{
          muted: false,
          onClose: jest.fn(),
          onMutePress: jest.fn(),
          onYield,
        }}
      />,
    );
    expect(queryByTestId("live-talk-button")).toBeNull();
    expect(getByTestId("live-talk-mute")).toBeTruthy();
    expect(getByTestId("live-talk-close")).toBeTruthy();
    expect(getByTestId("chat-composer-input")).toBeTruthy();
    expect(getByLabelText("chat.attach_a11y")).toBeTruthy();
    expect(getByTestId("composer-attachment-add-icon").props.name).toBe("plus");
  });

  it.each([true, false])("replaces attach with cancel while voice is active (recording: %s)", async (recording) => {
    const onCancelVoice = jest.fn();
    const onPickAttachment = jest.fn();
    const { getByLabelText, getByTestId, queryByTestId } = await render(
      <ChatComposer
        {...baseProps}
        voiceRecording={recording}
        voiceTranscribing={!recording}
        onCancelVoice={onCancelVoice}
        onPickAttachment={onPickAttachment}
      />,
    );

    expect(queryByTestId("composer-attachment-add-icon")).toBeNull();
    expect(getByTestId("composer-voice-cancel-icon").props.name).toBe("close");
    fireEvent.press(getByLabelText("chat.voice_cancel_a11y"));
    expect(onCancelVoice).toHaveBeenCalledTimes(1);
    expect(onPickAttachment).not.toHaveBeenCalled();
  });

  it("hides mute and close while the user is typing in live talk", async () => {
    const chrome = {
      muted: false,
      onClose: jest.fn(),
      onMutePress: jest.fn(),
      onYield: jest.fn(),
    };
    const { queryByTestId, rerender } = await render(
      <DraftHarness input="hello">
        <ChatComposer
          {...baseProps}
          onLiveTalkPress={jest.fn()}
          liveTalkChrome={chrome}
        />
      </DraftHarness>,
    );
    expect(queryByTestId("live-talk-mute")).toBeNull();
    expect(queryByTestId("live-talk-close")).toBeNull();
    expect(queryByTestId("chat-composer-input")).toBeTruthy();

    await rerender(
      <DraftHarness input="">
        <ChatComposer
          {...baseProps}
          onLiveTalkPress={jest.fn()}
          liveTalkChrome={chrome}
          pendingAttachment={{
            kind: "image",
            localUri: "file://photo.jpg",
            contentType: "image/jpeg",
            fileName: "photo.jpg",
          }}
        />
      </DraftHarness>,
    );
    expect(queryByTestId("live-talk-mute")).toBeTruthy();
    expect(queryByTestId("live-talk-close")).toBeTruthy();
  });
});

describe("ChatComposer at a larger text size", () => {
  it.each([
    [1.5, 36, 0],
    [2, 48, 0],
  ])("keeps one line level with the buttons at %sx", async (scale, line, spaceBelow) => {
    windowFontScale = scale;
    const { getByTestId } = await render(<ChatComposer {...baseProps} />);

    expect(getByTestId("chat-composer-input")).toHaveStyle({ height: line });
    expect(getByTestId("chat-composer-field")).toHaveStyle({ paddingBottom: spaceBelow });
    expect(getByTestId("composer-input-row")).toHaveStyle({ alignItems: "center" });
  });

  it("grows by a scaled line per Return", async () => {
    windowFontScale = 1.5;
    const { getByTestId } = await render(
      <DraftHarness input={"First line\nSecond line"}>
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );

    expect(getByTestId("chat-composer-input")).toHaveStyle({ height: 72 });
    expect(getByTestId("composer-input-row")).toHaveStyle({ alignItems: "flex-end" });
  });

  it("wraps sooner than at the default size", async () => {
    windowFontScale = 1.5;
    const { getByTestId } = await render(
      <DraftHarness input={"a".repeat(20)}>
        <ChatComposer {...baseProps} />
      </DraftHarness>,
    );
    expect(getByTestId("chat-composer-input")).toHaveStyle({ height: 36 });

    await fireEvent(getByTestId("chat-composer-input"), "layout", {
      nativeEvent: { layout: { x: 0, y: 0, width: 200, height: 44 } },
    });

    // Twenty glyphs fit 200 pt at the default size; at 1.5x they take two lines.
    expect(getByTestId("chat-composer-input")).toHaveStyle({ height: 72 });
  });

  it("moves the thread up when one line is taller than the buttons", async () => {
    windowFontScale = 2;
    const onInputFrameExtraChange = jest.fn();
    await render(
      <ChatComposer {...baseProps} onInputFrameExtraChange={onInputFrameExtraChange} />,
    );

    expect(onInputFrameExtraChange).toHaveBeenLastCalledWith(12);
  });
});
