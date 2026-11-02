import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type {
  LayoutChangeEvent,
  NativeSyntheticEvent,
  TextInputContentSizeChangeEventData,
} from "react-native";

import type { ComposerTextSize } from "@/features/chat/components/ComposerTextMeasure";
import { useLatestRef } from "@/lib/latestRef";
import {
  COMPOSER_CONTROL_SIZE,
  composerInputFrameForLines,
  composerInputFrameHeight,
  composerInputMetrics,
  composerInputTextBoxHeight,
  composerSoftWrapLineCount,
  retainedComposerContentHeight,
} from "@/features/chat/model/composerLogic";

type Options = {
  input: string;
  /** Bumps on a thread switch: the next draft does not inherit this one's wrap height. */
  draftRevision: number | undefined;
  /** Native text scales the field's line box with the system text size. */
  fontScale: number;
  /** Recording or transcribing: the waveform takes the row, so nothing stacks. */
  voiceActive: boolean;
  /** Extra field height past one line, so the thread moves up with the pill. */
  onInputFrameExtraChange?: (extra: number) => void;
};

/**
 * What the off-screen copy of the draft says about layout, kept coarse. Its
 * one-line width grows with every letter; the layout changes only when the
 * text stops fitting beside the buttons or takes another line, so a keystroke
 * that does neither does not render the composer again.
 */
type MeasuredText = {
  /** Wider than the field beside the buttons; null until the copy has been laid out. */
  wrapsInline: boolean | null;
  /** The copy's height at the field width. */
  height: number;
};

const UNMEASURED: MeasuredText = { wrapsInline: null, height: 0 };

/**
 * How tall the composer field is, whether its text wraps above the buttons,
 * and the full-height editor toggle. The field reports its width and content
 * size; everything else is derived from the draft and the text size.
 */
export function useComposerFieldLayout({
  input,
  draftRevision,
  fontScale,
  voiceActive,
  onInputFrameExtraChange,
}: Options) {
  const [inputHeight, setInputHeight] = useState<number>(COMPOSER_CONTROL_SIZE);
  const [inputContentWidth, setInputContentWidth] = useState(0);
  const [composerExpanded, setComposerExpanded] = useState(false);
  // Field width beside the buttons. Wrapping is judged at this width, so the
  // wider stacked field cannot flip the layout back.
  const [inlineWidth, setInlineWidth] = useState(0);
  const [measured, setMeasured] = useState<MeasuredText>(UNMEASURED);
  // Copies of state for the setters below, which skip a value React already
  // has (setting even an unchanged value right after a render renders again),
  // and for layout events that land before the render holding the last one.
  const inputHeightRef = useRef(inputHeight);
  const inlineWidthRef = useRef(inlineWidth);
  const measuredRef = useRef(measured);
  const textSize = useRef<ComposerTextSize>({ naturalWidth: 0, height: 0 });
  const [measuredContent, setMeasuredContent] = useState<{ revision: number; height: number } | null>(null);
  // The effect below runs on the draft, not on each measurement: it reads the latest one.
  const measuredContentRef = useLatestRef(measuredContent);
  // The glyph estimate walks every character: once per draft and width, shared below.
  const estimatedLines = useMemo(
    () => composerSoftWrapLineCount(input, inputContentWidth, fontScale),
    [input, inputContentWidth, fontScale],
  );

  const commitInputHeight = useCallback((height: number) => {
    if (inputHeightRef.current === height) return;
    inputHeightRef.current = height;
    setInputHeight(height);
  }, []);

  // Expanded chrome belongs to the active draft, not the mounted screen.
  useEffect(() => {
    setComposerExpanded(false);
  }, [draftRevision]);

  useEffect(() => {
    // iOS can retain the last multiline content size after a controlled
    // TextInput is cleared. Pin the empty draft back to the single-line
    // height so a sent long message cannot leave a tall blank composer.
    // Within one draft, keep the last wrap height: a keystroke changes the
    // string without a new content-size event. A thread switch (revision)
    // drops that sample so the next draft does not inherit it.
    const revision = draftRevision ?? 0;
    if (!input) {
      setMeasuredContent(null);
      commitInputHeight(COMPOSER_CONTROL_SIZE);
      setComposerExpanded(false);
      return;
    }
    const retained = retainedComposerContentHeight(measuredContentRef.current, revision, input);
    const frame = composerInputFrameHeight(
      input,
      retained,
      inputContentWidth,
      fontScale,
      estimatedLines,
    );
    commitInputHeight(frame.height);
  }, [commitInputHeight, draftRevision, estimatedLines, fontScale, input, inputContentWidth, measuredContentRef]);

  const commitMeasured = (size: ComposerTextSize, fitWidth: number) => {
    const wrapsInline = size.naturalWidth > 0 ? fitWidth > 0 && size.naturalWidth > fitWidth : null;
    const current = measuredRef.current;
    if (current.wrapsInline === wrapsInline && current.height === size.height) return;
    measuredRef.current = { wrapsInline, height: size.height };
    setMeasured(measuredRef.current);
  };

  const onTextMeasure = (size: ComposerTextSize) => {
    textSize.current = size;
    commitMeasured(size, inlineWidthRef.current);
  };

  // Only hard returns move the thread. A soft wrap grows the field in place;
  // pushing list padding here is what yanks the chat up on every line.
  // Measured from the 44 pt field COMPOSER_HEIGHT assumes, so a taller line
  // at a large text size moves the thread too.
  const returnFrame = composerInputFrameHeight(input, 0, 0, fontScale);
  // Text wraps beside the buttons: it takes the full width over a row of them.
  // Judged on the rendered text; the glyph estimate is only for the first frame.
  const estimateWrapsInline = () =>
    (inlineWidth === inputContentWidth
      ? estimatedLines
      : composerSoftWrapLineCount(input, inlineWidth, fontScale)) > 1;
  const stacked =
    Boolean(input) &&
    (input.includes("\n") || (measured.wrapsInline ?? estimateWrapsInline()));
  // Stacking adds the button row once, so the last reply stays clear of the pill.
  const inputFrameExtra = composerExpanded
    ? 0
    : Math.max(0, returnFrame.height - COMPOSER_CONTROL_SIZE) +
      (stacked ? COMPOSER_CONTROL_SIZE : 0);
  // Reported while the drawer hides the composer too: it keeps its size there,
  // so opening the drawer does not lay out the chat under it again.
  useEffect(() => {
    onInputFrameExtraChange?.(inputFrameExtra);
  }, [inputFrameExtra, onInputFrameExtraChange]);

  const measuredNow = input
    ? retainedComposerContentHeight(measuredContent, draftRevision ?? 0, input)
    : 0;
  const field = composerInputMetrics(fontScale);
  const frameNow =
    measured.height > 0
      ? composerInputFrameForLines(Math.round(measured.height / field.line), fontScale)
      : composerInputFrameHeight(
          input,
          Math.max(measuredNow, inputHeight),
          inputContentWidth,
          fontScale,
          estimatedLines,
        );
  // Same render as the keystroke. Waiting for the effect leaves one frame
  // clipped at the end of the line.
  const fieldHeight = input ? frameNow.height : field.min;
  const fieldOverflows = Boolean(input) && frameNow.overflows;
  const stackedLayout = (stacked || composerExpanded) && !voiceActive;

  const onInputLayout = (event: LayoutChangeEvent) => {
    const next = Math.round(event.nativeEvent.layout.width);
    if (next <= 0) return;
    setInputContentWidth((current) => (current === next ? current : next));
    if (!stackedLayout) {
      inlineWidthRef.current = next;
      setInlineWidth(next);
      commitMeasured(textSize.current, next);
    }
  };

  const onInputContentSizeChange = (
    event: NativeSyntheticEvent<TextInputContentSizeChangeEventData>,
  ) => {
    const measuredHeight = Math.ceil(event.nativeEvent.contentSize.height);
    const revision = draftRevision ?? 0;
    // An unchanged height keeps the same object: no render for a keystroke on the same line.
    setMeasuredContent((current) =>
      current?.revision === revision && current.height === measuredHeight ? current : { revision, height: measuredHeight },
    );
    const frame = composerInputFrameHeight(
      input,
      measuredHeight,
      inputContentWidth,
      fontScale,
      estimatedLines,
    );
    if (!composerExpanded) commitInputHeight(frame.height);
  };

  return {
    composerExpanded,
    toggleExpanded: () => setComposerExpanded((expanded) => !expanded),
    inputContentWidth,
    onTextMeasure,
    field,
    fieldHeight,
    // Text box matches the lines. Centering slack stays on the wrapper so the
    // caret remains on the last line, beside the buttons.
    textBoxHeight: composerInputTextBoxHeight(fieldHeight, fontScale),
    fieldOverflows,
    singleLineComposer: !composerExpanded && fieldHeight <= field.min,
    showExpandControl: fieldOverflows || composerExpanded,
    stackedLayout,
    onInputLayout,
    onInputContentSizeChange,
  };
}
