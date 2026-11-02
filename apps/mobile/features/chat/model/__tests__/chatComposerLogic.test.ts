import {
  CHAT_ACTION_ROW_HEIGHT,
  COMPOSER_CONTROL_SIZE,
  COMPOSER_INPUT_LINE_HEIGHT,
  COMPOSER_INPUT_MAX_HEIGHT,
  composerInputFrameHeight,
  composerInputMetrics,
  composerInputTextBoxHeight,
  composerSoftWrapLineCount,
  retainedComposerContentHeight,
  composerNativeInputTraits,
  composerShowsMic,
  composerShowsSend,
  composerShowsStop,
  computeChatLayoutMetrics,
  isComposerMenuOverlayOpen,
  shouldReserveComposerActionGap,
} from "@/features/chat/model/composerLogic";
import { IMAGE_GEN_PENDING_ASSISTANT_ID } from "@/features/images/model/imageGenMessages";
import { keyboardLiftAbove } from "@/lib/keyboardInset";

describe("composerInputFrameHeight", () => {
  it("grows one line per Return and caps at the field max", () => {
    expect(composerInputFrameHeight("", 80)).toEqual({
      height: COMPOSER_CONTROL_SIZE,
      overflows: false,
    });
    expect(composerInputFrameHeight("\n\n", 0).height).toBeGreaterThan(
      COMPOSER_CONTROL_SIZE,
    );
    expect(composerInputFrameHeight("K\nk", 20).height).toBeGreaterThan(
      COMPOSER_CONTROL_SIZE,
    );
    expect(composerInputFrameHeight("line\n".repeat(12), 400)).toEqual({
      height: COMPOSER_INPUT_MAX_HEIGHT,
      overflows: true,
    });
  });

  it("grows when a line is wider than the field, without a Return", () => {
    expect(composerSoftWrapLineCount("hello", 200)).toBe(1);
    expect(composerSoftWrapLineCount("a".repeat(40), 200)).toBe(2);
    expect(composerSoftWrapLineCount("ab\ncd", 200)).toBe(2);
    expect(composerSoftWrapLineCount("hello", 0)).toBe(1);
    const wrapped = composerInputFrameHeight("a".repeat(40), 0, 200);
    expect(wrapped.height).toBe(COMPOSER_CONTROL_SIZE + COMPOSER_INPUT_LINE_HEIGHT);
    expect(wrapped.overflows).toBe(false);
    expect(composerInputFrameHeight("a".repeat(40), 0).height).toBe(COMPOSER_CONTROL_SIZE);
    // A native content size larger than the text must not keep growing the field.
    expect(composerInputFrameHeight("hello", 400, 220).height).toBe(COMPOSER_CONTROL_SIZE);
    expect(composerInputFrameHeight("a".repeat(40), 400, 200).height).toBe(
      COMPOSER_CONTROL_SIZE + COMPOSER_INPUT_LINE_HEIGHT,
    );
  });

  it("keeps centering slack out of the text box so the caret stays on the last line", () => {
    expect(composerInputTextBoxHeight(COMPOSER_CONTROL_SIZE)).toBe(
      COMPOSER_INPUT_LINE_HEIGHT,
    );
    expect(
      composerInputTextBoxHeight(COMPOSER_CONTROL_SIZE + COMPOSER_INPUT_LINE_HEIGHT),
    ).toBe(COMPOSER_INPUT_LINE_HEIGHT * 2);
    expect(composerInputTextBoxHeight(COMPOSER_INPUT_MAX_HEIGHT)).toBe(
      COMPOSER_INPUT_LINE_HEIGHT * 6,
    );
    expect(composerInputTextBoxHeight(112)).toBe(112);
  });

  it("scales the field with the system text size", () => {
    // The default size keeps the fixed field.
    expect(composerInputMetrics(1)).toEqual({
      line: COMPOSER_INPUT_LINE_HEIGHT,
      min: COMPOSER_CONTROL_SIZE,
      max: COMPOSER_INPUT_MAX_HEIGHT,
      slack: COMPOSER_CONTROL_SIZE - COMPOSER_INPUT_LINE_HEIGHT,
    });
    // 1.5x: the line fills the row, so there is no centering slack.
    expect(composerInputMetrics(1.5)).toEqual({ line: 36, min: 36, max: 216, slack: 0 });
    expect(composerInputFrameHeight("", 0, 0, 1.5).height).toBe(36);
    expect(composerInputTextBoxHeight(36, 1.5)).toBe(36);
    expect(composerInputFrameHeight("\n", 0, 0, 1.5).height).toBe(72);
    expect(composerInputTextBoxHeight(72, 1.5)).toBe(72);
    // 2x: one line is taller than the buttons.
    expect(composerInputFrameHeight("", 0, 0, 2).height).toBe(48);
    expect(composerInputTextBoxHeight(48, 2)).toBe(48);
    expect(composerInputTextBoxHeight(96, 2)).toBe(96);
    // Fractional lines (iOS XXXL) still land on the line grid.
    const xxxl = composerInputMetrics(1.353);
    expect(composerInputTextBoxHeight(xxxl.min + xxxl.line * 2, 1.353)).toBeCloseTo(
      xxxl.line * 3,
    );
    // Accessibility sizes stop growing sooner, so the field stays on screen.
    expect(composerInputMetrics(3.5).max).toBeLessThanOrEqual(240);
    expect(composerInputFrameHeight("line\n".repeat(12), 0, 0, 3.5)).toEqual({
      height: composerInputMetrics(3.5).max,
      overflows: true,
    });
  });

  it("wraps sooner at a larger text size", () => {
    expect(composerSoftWrapLineCount("a".repeat(20), 200)).toBe(1);
    expect(composerSoftWrapLineCount("a".repeat(20), 200, 1.5)).toBe(2);
    expect(composerInputFrameHeight("a".repeat(20), 0, 200, 1.5).height).toBe(72);
  });

  it("keeps a wrap height while the same draft changes and drops it on reset", () => {
    const stored = { revision: 2, height: 88 };
    expect(retainedComposerContentHeight(stored, 2, "hello world")).toBe(88);
    expect(retainedComposerContentHeight(stored, 2, "hello worlds")).toBe(88);
    expect(retainedComposerContentHeight(stored, 2, "")).toBe(0);
    expect(retainedComposerContentHeight(stored, 3, "hello world")).toBe(0);
    expect(retainedComposerContentHeight(null, 2, "hello world")).toBe(0);
  });
});

describe("chatComposerLogic", () => {
  it("isComposerMenuOverlayOpen reflects attach sheet", () => {
    expect(isComposerMenuOverlayOpen(false)).toBe(false);
    expect(isComposerMenuOverlayOpen(true)).toBe(true);
  });

  it("composer input is a messaging field until the math editor owns it", () => {
    expect(composerNativeInputTraits(false)).toEqual({
      autoCorrect: true,
      spellCheck: true,
      autoCapitalize: "sentences",
    });
    expect(composerNativeInputTraits(true)).toEqual({
      autoCorrect: false,
      spellCheck: false,
      autoCapitalize: "none",
    });
  });

  it.each([
    [{ streaming: true, sendBusy: false, replySaving: false }, true],
    // Typing dots went up with the bubble, but the turn has not gone out yet.
    [{ streaming: true, sendBusy: true, replySaving: false }, false],
    // The reply's text is all in (stream_end); only its save is left.
    [{ streaming: true, sendBusy: false, replySaving: true }, false],
    [{ streaming: false, sendBusy: true, replySaving: false }, false],
    [{ streaming: false, sendBusy: false, replySaving: false }, false],
  ])("composerShowsStop(%o) is %p", (state, shows) => {
    expect(composerShowsStop(state)).toBe(shows);
  });

  it("composerShowsMic and composerShowsSend are mutually exclusive for typed text", () => {
    expect(
      composerShowsMic({
        voiceAvailable: true,
        voiceRecording: false,
        voiceTranscribing: false,
        hasSendableContent: false,
      }),
    ).toBe(true);
    expect(
      composerShowsSend({
        voiceRecording: false,
        voiceTranscribing: false,
        hasSendableContent: false,
      }),
    ).toBe(false);

    expect(
      composerShowsMic({
        voiceAvailable: true,
        voiceRecording: false,
        voiceTranscribing: false,
        hasSendableContent: true,
      }),
    ).toBe(false);
    expect(
      composerShowsSend({
        voiceRecording: false,
        voiceTranscribing: false,
        hasSendableContent: true,
      }),
    ).toBe(true);

    // Mid-dictation: mic only (plus cancel), never send.
    expect(
      composerShowsMic({
        voiceAvailable: true,
        voiceRecording: true,
        voiceTranscribing: false,
        hasSendableContent: true,
      }),
    ).toBe(true);
    expect(
      composerShowsSend({
        voiceRecording: true,
        voiceTranscribing: false,
        hasSendableContent: true,
      }),
    ).toBe(false);
  });

  it("computeChatLayoutMetrics holds composer-gap air only for the in-flight placeholder", () => {
    const idle = computeChatLayoutMetrics({
      insetsTop: 44,
      insetsBottom: 20,
      windowHeight: 800,
      keyboardHeight: 0,
      composerHeight: 100,
      attachmentExtra: 0,
      messagesLength: 2,
      streaming: false,
      lastMessageId: "msg-1",
    });
    expect(idle.headerMinimumHeight).toBe(96);
    expect(idle.headerInset).toBe(96);
    expect(idle.composerLift).toBe(0);
    expect(idle.composerBottomPad).toBe(20);
    expect(idle.listBottomPad).toBe(idle.composerClearance);

    const streaming = computeChatLayoutMetrics({
      insetsTop: 44,
      insetsBottom: 20,
      windowHeight: 800,
      keyboardHeight: 0,
      composerHeight: 100,
      attachmentExtra: 0,
      messagesLength: 2,
      streaming: true,
      lastMessageId: "streaming",
    });
    expect(streaming.listBottomPad).toBe(idle.composerClearance + CHAT_ACTION_ROW_HEIGHT);

    // Finalize still has streaming=true on the old signal, but icons already
    // live on the persisted row — do not keep the extra pad.
    const finalizing = computeChatLayoutMetrics({
      insetsTop: 44,
      insetsBottom: 20,
      windowHeight: 800,
      keyboardHeight: 0,
      composerHeight: 100,
      attachmentExtra: 0,
      messagesLength: 2,
      streaming: true,
      lastMessageId: "msg-1",
    });
    expect(finalizing.listBottomPad).toBe(idle.composerClearance);

    const keyboard = computeChatLayoutMetrics({
      insetsTop: 44,
      insetsBottom: 20,
      windowHeight: 800,
      keyboardHeight: 300,
      composerHeight: 100,
      attachmentExtra: 44,
      messagesLength: 0,
      streaming: true,
    });
    expect(keyboard.composerLift).toBe(300);
    expect(keyboard.composerBottomPad).toBe(0);
    expect(keyboard.composerBlockHeight).toBe(144);

    const withMathBar = computeChatLayoutMetrics({
      insetsTop: 44,
      insetsBottom: 20,
      windowHeight: 800,
      keyboardHeight: 0,
      composerHeight: 100,
      attachmentExtra: 0,
      mathBarExtra: 44,
      messagesLength: 0,
      streaming: false,
    });
    expect(withMathBar.composerBlockHeight).toBe(144);

    const grownHeader = computeChatLayoutMetrics({
      insetsTop: 44,
      insetsBottom: 20,
      windowHeight: 800,
      keyboardHeight: 0,
      composerHeight: 100,
      attachmentExtra: 0,
      messagesLength: 2,
      streaming: false,
      measuredHeaderHeight: 124,
    });
    expect(grownHeader.headerMinimumHeight).toBe(96);
    expect(grownHeader.headerInset).toBe(124);
    expect(grownHeader.emptyHeight).toBe(idle.emptyHeight - 28);

    const scaledHeader = computeChatLayoutMetrics({
      insetsTop: 44,
      insetsBottom: 20,
      windowHeight: 800,
      fontScale: 3,
      keyboardHeight: 0,
      composerHeight: 100,
      attachmentExtra: 0,
      messagesLength: 2,
      streaming: false,
    });
    expect(scaledHeader.headerMinimumHeight).toBeGreaterThan(96);
    expect(scaledHeader.headerInset).toBe(scaledHeader.headerMinimumHeight);
  });

  it.each([
    ["the keyboard down", 0, "msg-1"],
    ["the keyboard up", 336, "msg-1"],
    ["the keyboard up and a reply in flight", 336, "streaming"],
  ])("resting clearance plus the keyboard lift lands where the settled layout puts it, with %s", (_case, keyboardHeight, lastMessageId) => {
    const options = {
      insetsTop: 44,
      insetsBottom: 34,
      windowHeight: 800,
      composerHeight: 56,
      attachmentExtra: 0,
      mathBarExtra: 24,
      messagesLength: 2,
      streaming: false,
      lastMessageId,
    };
    const settled = computeChatLayoutMetrics({ ...options, keyboardHeight });
    const keyboardDown = computeChatLayoutMetrics({ ...options, keyboardHeight: 0 });
    const lift = keyboardLiftAbove(keyboardHeight, keyboardDown.composerBottomPad);

    // The resting values never move with the keyboard; the UI thread adds the lift.
    expect(settled.restingComposerClearance).toBe(keyboardDown.restingComposerClearance);
    expect(settled.restingListBottomPad).toBe(keyboardDown.restingListBottomPad);
    expect(settled.restingComposerClearance + lift).toBe(settled.composerClearance);
    expect(settled.restingListBottomPad + lift).toBe(settled.listBottomPad);
  });

  it("shouldReserveComposerActionGap only for in-flight placeholders", () => {
    expect(shouldReserveComposerActionGap("streaming")).toBe(true);
    expect(shouldReserveComposerActionGap(IMAGE_GEN_PENDING_ASSISTANT_ID)).toBe(true);
    expect(shouldReserveComposerActionGap("msg-1")).toBe(false);
    expect(shouldReserveComposerActionGap(undefined)).toBe(false);
  });
});
