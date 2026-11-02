import { IMAGE_GEN_PENDING_ASSISTANT_ID } from "@/features/images/model/imageGenMessages";
import { Space } from "@/lib/space";
import { Type } from "@/lib/type";

const CHAT_HEADER_BAR_HEIGHT = 52;
const CHAT_HEADER_TITLE_LINE_HEIGHT_RATIO = 1.3;
const CHAT_HEADER_TITLE_VERTICAL_AIR = 8;
/** Matches the in-bubble action row (34px icons + 4px margin). */
export const CHAT_ACTION_ROW_HEIGHT = 44;
const CHAT_KEYBOARD_LIFT_EXTRA = 0;
export const CHAT_COMPOSER_MIN_BOTTOM_PAD = 10;
/**
 * One-line composer row. Shorter than the 44 pt touch minimum; the buttons
 * add hitSlop so the placeholder, +, mic, and live talk stay on one line.
 * Also the input's minimum height, so the placeholder shares the controls' midline.
 */
export const COMPOSER_CONTROL_SIZE = 36;
/** Extra Returns grow by one text line, not another full control. */
export const COMPOSER_INPUT_LINE_HEIGHT = Space.lg;
export const COMPOSER_INPUT_MAX_HEIGHT =
  COMPOSER_CONTROL_SIZE + COMPOSER_INPUT_LINE_HEIGHT * 5;
/** Cap on the field at large text sizes: fewer than six lines when six would pass it. */
const COMPOSER_INPUT_MAX_FRAME = 240;

type ComposerInputMetrics = {
  /** One text line. */
  line: number;
  /** One-line frame: the + / send height, or the line when that is taller. */
  min: number;
  /** Frame at which the field stops growing and scrolls. */
  max: number;
  /** Frame height outside the text box. Half of it sits under the last line. */
  slack: number;
};

/**
 * Field sizes at the system text size. Native text scales the 24 pt line box
 * by the font scale, so a frame sized for 24 pt lines clips a larger text
 * size. At a font scale of 1 these are the constants above.
 */
export function composerInputMetrics(fontScale = 1): ComposerInputMetrics {
  const line = COMPOSER_INPUT_LINE_HEIGHT * (fontScale > 0 ? fontScale : 1);
  const min = Math.max(COMPOSER_CONTROL_SIZE, line);
  const extraLines = Math.max(
    1,
    Math.min(5, Math.floor((COMPOSER_INPUT_MAX_FRAME - min) / line)),
  );
  return { line, min, max: min + line * extraLines, slack: min - line };
}

/**
 * Last native content height stays valid while the same draft is edited.
 * Soft wraps do not add a newline, and iOS often skips `onContentSizeChange`
 * when the box does not grow, so an exact-string match would snap the field
 * back to one line. A cleared draft or a thread switch drops the sample.
 */
export function retainedComposerContentHeight(
  stored: { revision: number; height: number } | null,
  revision: number,
  text: string,
): number {
  if (!text || !stored || stored.revision !== revision) return 0;
  return stored.height;
}

/** Latin glyph at Type.body. Wide enough that the field grows before the last glyph clips. */
const SOFT_WRAP_GLYPH = 9;
const SOFT_WRAP_WIDE_GLYPH = 16;
/** Ignore a tiny first layout pass so the field does not jump to the max height. */
const SOFT_WRAP_MIN_WIDTH = 40;

function glyphWidth(ch: string): number {
  const code = ch.codePointAt(0) ?? 0;
  const wide =
    (code >= 0x1100 && code <= 0x115f) ||
    (code >= 0x2e80 && code <= 0x9fff) ||
    (code >= 0xac00 && code <= 0xd7a3) ||
    (code >= 0xf900 && code <= 0xfaff) ||
    (code >= 0xfe10 && code <= 0xfe6f) ||
    (code >= 0xff01 && code <= 0xff60) ||
    (code >= 0xffe0 && code <= 0xffe6) ||
    (code >= 0x1f300 && code <= 0x1faff);
  return wide ? SOFT_WRAP_WIDE_GLYPH : SOFT_WRAP_GLYPH;
}

function wrapOneLine(line: string, contentWidth: number): number {
  if (!line) return 1;
  let used = 0;
  let lines = 1;
  for (const ch of line) {
    const width = glyphWidth(ch);
    if (used > 0 && used + width > contentWidth) {
      lines += 1;
      used = width;
    } else {
      used += width;
    }
  }
  return lines;
}

/**
 * Visual lines for a draft. iOS often will not wrap or report a taller
 * content size while the field height is locked to one line, so the frame
 * has to grow from the text width before the native event arrives.
 * `contentWidth` of 0 counts hard returns only.
 */
export function composerSoftWrapLineCount(
  text: string,
  contentWidth: number,
  fontScale = 1,
): number {
  if (!text) return 1;
  const parts = text.split("\n");
  if (contentWidth < SOFT_WRAP_MIN_WIDTH) return parts.length;
  // Glyphs widen with the text size, so fewer fit on a line.
  const width = contentWidth / (fontScale > 0 ? fontScale : 1);
  let lines = 0;
  for (const part of parts) lines += wrapOneLine(part, width);
  return Math.max(1, lines);
}

/**
 * Frame height for the composer field. Returns and soft wraps count as lines
 * even when iOS reports a stale content size, so the field grows instead of
 * clipping the next line under the pill.
 *
 * Once the field width is known, ignore the native content size. iOS reports
 * the height we just set, and trusting that number ratchets the pill (and the
 * thread) upward on every keystroke.
 *
 * `lineCount` is `composerSoftWrapLineCount` for the same text, width and
 * scale, for a caller that already has it: the estimate walks every character.
 */
export function composerInputFrameHeight(
  text: string,
  measuredContentHeight: number,
  contentWidth = 0,
  fontScale = 1,
  lineCount = composerSoftWrapLineCount(text, contentWidth, fontScale),
): { height: number; overflows: boolean } {
  const { line, min, max } = composerInputMetrics(fontScale);
  if (!text) return { height: min, overflows: false };
  const fromLines = min + (lineCount - 1) * line;
  const measured =
    contentWidth >= SOFT_WRAP_MIN_WIDTH
      ? 0
      : measuredContentHeight > 0
        ? measuredContentHeight
        : 0;
  const desired = Math.max(min, fromLines, measured);
  return {
    height: Math.min(max, desired),
    overflows: desired > max,
  };
}

/** Frame for a line count read from the rendered text, not estimated from glyphs. */
export function composerInputFrameForLines(
  lines: number,
  fontScale = 1,
): { height: number; overflows: boolean } {
  const { line, min, max } = composerInputMetrics(fontScale);
  const desired = min + (Math.max(1, lines) - 1) * line;
  return { height: Math.min(max, desired), overflows: desired > max };
}

/**
 * Height of the text itself. The frame includes centering slack so one line
 * lines up with the buttons; that slack must stay on the wrapper. Padding
 * inside the field makes iOS draw the caret a line too high.
 */
export function composerInputTextBoxHeight(frameHeight: number, fontScale = 1): number {
  const { line, min, slack } = composerInputMetrics(fontScale);
  if (frameHeight <= min) return line;
  // Scaled lines are fractional, so the grid check allows float error.
  const lines = (frameHeight - min) / line;
  const onLineGrid = Math.abs(lines - Math.round(lines)) < 1e-6;
  if (!onLineGrid) return frameHeight;
  return frameHeight - slack;
}

/** How far the bottom scrim tucks under the pill. */
export const COMPOSER_GAP_FADE_OVERLAP = 16;

const CHAT_EMPTY_MIN_HEIGHT = 160;

export function isComposerMenuOverlayOpen(attachSheetOpen: boolean): boolean {
  return attachSheetOpen;
}

type ComposerNativeInputTraits = {
  autoCorrect: boolean;
  spellCheck: boolean;
  autoCapitalize: "none" | "sentences";
};

/**
 * Ordinary chat is a messaging field. The math pad is a controlled editor, so
 * it turns correction off only while that editor owns the input — not for the
 * whole session, and not because the draft happens to contain an equation.
 */
export function composerNativeInputTraits(mathEditorOpen: boolean): ComposerNativeInputTraits {
  if (mathEditorOpen) {
    return { autoCorrect: false, spellCheck: false, autoCapitalize: "none" };
  }
  return { autoCorrect: true, spellCheck: true, autoCapitalize: "sentences" };
}

/** Mic when empty; send when there is text/attachment. Never both (except stop while streaming). */
export function composerShowsMic(options: {
  voiceAvailable: boolean;
  voiceRecording: boolean;
  voiceTranscribing: boolean;
  hasSendableContent: boolean;
}): boolean {
  if (!options.voiceAvailable || options.voiceTranscribing) return false;
  if (options.voiceRecording) return true;
  return !options.hasSendableContent;
}

export function composerShowsSend(options: {
  voiceRecording: boolean;
  voiceTranscribing: boolean;
  hasSendableContent: boolean;
}): boolean {
  if (options.voiceRecording || options.voiceTranscribing) return false;
  return options.hasSendableContent;
}

/**
 * Stop is for a reply or a picture under way. A send still on its way (its
 * picture check, location, file or new chat not done) shows a busy Send instead:
 * nothing has gone out yet for Stop to stop. Neither does a reply whose text is
 * all in (`stream_end`) and only saving: Send works again from then.
 */
export function composerShowsStop(options: {
  streaming: boolean;
  sendBusy: boolean;
  replySaving: boolean;
}): boolean {
  return options.streaming && !options.sendBusy && !options.replySaving;
}

/** True while the last row is the in-flight placeholder (no action icons yet). */
export function shouldReserveComposerActionGap(lastMessageId?: string): boolean {
  return lastMessageId === "streaming" || lastMessageId === IMAGE_GEN_PENDING_ASSISTANT_ID;
}

type ChatLayoutMetrics = {
  headerMinimumHeight: number;
  headerInset: number;
  composerLift: number;
  composerBottomPad: number;
  composerBlockHeight: number;
  composerClearance: number;
  listBottomPad: number;
  emptyHeight: number;
  /**
   * `composerClearance` with the keyboard down. Chrome above the composer adds
   * the keyboard's lift on the UI thread, so it moves with every frame of it.
   */
  restingComposerClearance: number;
  /** `listBottomPad` with the keyboard down; a spacer under the list adds the keyboard frame by frame. */
  restingListBottomPad: number;
};

export function computeChatHeaderMinimumHeight(insetsTop: number, fontScale = 1): number {
  const scaledTitleHeight = Math.ceil(
    Type.navTitle.fontSize *
      Math.max(1, fontScale) *
      CHAT_HEADER_TITLE_LINE_HEIGHT_RATIO,
  );
  const headerBarMinimumHeight = Math.max(
    CHAT_HEADER_BAR_HEIGHT,
    scaledTitleHeight + CHAT_HEADER_TITLE_VERTICAL_AIR,
  );
  return insetsTop + headerBarMinimumHeight;
}

export function computeChatLayoutMetrics(options: {
  insetsTop: number;
  insetsBottom: number;
  windowHeight: number;
  keyboardHeight: number;
  composerHeight: number;
  attachmentExtra: number;
  mathBarExtra?: number;
  messagesLength: number;
  streaming: boolean;
  lastMessageId?: string;
  measuredHeaderHeight?: number;
  fontScale?: number;
}): ChatLayoutMetrics {
  const headerMinimumHeight = computeChatHeaderMinimumHeight(
    options.insetsTop,
    options.fontScale,
  );
  const headerInset = Math.max(headerMinimumHeight, options.measuredHeaderHeight ?? 0);
  const composerLift =
    options.keyboardHeight > 0
      ? options.keyboardHeight + CHAT_KEYBOARD_LIFT_EXTRA
      : 0;
  const restingBottomPad = Math.max(options.insetsBottom, CHAT_COMPOSER_MIN_BOTTOM_PAD);
  const composerBottomPad = options.keyboardHeight > 0 ? 0 : restingBottomPad;
  const composerBlockHeight =
    options.composerHeight + options.attachmentExtra + (options.mathBarExtra ?? 0);
  const composerClearance = composerBlockHeight + composerBottomPad + composerLift;
  const restingComposerClearance = composerBlockHeight + restingBottomPad;
  // ChatGPT-style: while the in-flight placeholder is on screen, hold empty
  // air above the composer. When that row becomes a real message the icons
  // mount in the bubble and this pad drops in the same render — net zero, so
  // the prose does not move. Never reserve both regions at once (`streaming`
  // is not the signal: it stays true through finalize after icons already
  // landed, which was the down-spring).
  const actionGap = shouldReserveComposerActionGap(options.lastMessageId)
    ? CHAT_ACTION_ROW_HEIGHT
    : 0;
  const listBottomPad = composerClearance + actionGap;
  const emptyHeight = Math.max(
    CHAT_EMPTY_MIN_HEIGHT,
    options.windowHeight - headerInset - composerClearance,
  );

  return {
    headerMinimumHeight,
    headerInset,
    composerLift,
    composerBottomPad,
    composerBlockHeight,
    composerClearance,
    listBottomPad,
    emptyHeight,
    restingComposerClearance,
    restingListBottomPad: restingComposerClearance + actionGap,
  };
}

