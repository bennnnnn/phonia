import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import {
  Keyboard,
  Platform,
  type NativeSyntheticEvent,
  type TextInputSelectionChangeEventData,
} from "react-native";

import { clipboardIsImageOnly } from "@/lib/clipboard";
import {
  autoAdvanceNextEmptySlot,
  caretStepLeft,
  caretStepRight,
  MATH_KEYBOARD_SYMBOLS,
  type MathKeyboardGroup,
  spliceMathInsert,
  tapAdvancesToNextSlot,
  type MathKeyboardSymbol,
  type TextSelection,
} from "@/lib/math/keyboardSymbols";
import { applyPinnedTextChange, caretAfterMathBarClose, nativeEditRange } from "@/lib/math/composerChange";
import {
  extractInsertedDelta,
  isMostlyProsePaste,
  shouldProbeClipboardForImagePaste,
  normalizePastedMath,
} from "@/lib/math/pasteNormalize";
import { spliceMathBackspace } from "@/lib/math/draftSlots";
import {
  droppedOnlySlash,
  hasBareCommand,
  healDroppedCommandSlash,
} from "@/lib/math/healMathSource";
import { mathPadHeight } from "@/lib/math/keyboardPad";
import { useLatestRef } from "@/lib/latestRef";

function hasEditableMath(text: string): boolean {
  return text.includes("$") && !isMostlyProsePaste(text);
}

/**
 * The last height the phone's own keyboard reported. Module scope, so a pad
 * opened with the keyboard already down still matches it, and the pad is the
 * same height every time it opens.
 */
let lastSystemKeyboardHeight = 0;

function rememberSystemKeyboard(height: number | undefined) {
  if (height && height > 0) lastSystemKeyboardHeight = height;
}

export function useMathKeyboardInsert(options: {
  input: string;
  draftRevision?: number;
  setInput: (text: string) => void;
  onImageOnlyPaste?: () => void;
}) {
  const { input, setInput, onImageOnlyPaste, draftRevision = 0 } = options;
  const [mathBarOpen, setMathBarOpen] = useState(false);
  const [mathGroup, setMathGroup] = useState<MathKeyboardGroup>("basics");
  const [padHeight, setPadHeight] = useState(() => mathPadHeight(0));
  const [selection, setSelection] = useState<TextSelection>({ start: 0, end: 0 });
  const [forcedSelection, setForcedSelection] = useState<TextSelection | undefined>();
  // Mirrors of the two selections, so an event that repeats one (each typed
  // character reports the caret it already moved to) does not render the
  // composer again: React renders even for an unchanged value set right after an update.
  const selectionRef = useRef(selection);
  const forcedSelectionRef = useRef(forcedSelection);
  const [previewEnabled, setPreviewEnabled] = useState(false);
  const previewEnabledRef = useRef(false);
  const draftRevisionRef = useRef(draftRevision);
  // The draft whose math state this render shows; another draft shows no preview until reset.
  const [seenRevision, setSeenRevision] = useState(draftRevision);
  const pinRef = useRef<TextSelection | null>(null);
  const mathBarOpenRef = useRef(false);
  /** Outside tap hides the pad, but the next composer focus brings it back. ABC clears this. */
  const resumeMathRef = useRef(false);
  const [resumeMathOnFocus, setResumeMathOnFocus] = useState(false);
  const textRef = useLatestRef(input);

  useEffect(() => {
    const event = Platform.OS === "ios" ? "keyboardWillShow" : "keyboardDidShow";
    const sub = Keyboard.addListener(event, (e) => rememberSystemKeyboard(e.endCoordinates.height));
    return () => sub.remove();
  }, []);

  const enablePreview = useCallback(() => {
    previewEnabledRef.current = true;
    setPreviewEnabled(true);
  }, []);

  /** The caret the composer shows, and the one forced onto the native field (undefined: native owns it). */
  const commitSelection = useCallback((next: TextSelection, forced: TextSelection | undefined) => {
    const current = selectionRef.current;
    if (current.start !== next.start || current.end !== next.end) {
      selectionRef.current = next;
      setSelection(next);
    }
    if (forced === undefined && forcedSelectionRef.current === undefined) return;
    forcedSelectionRef.current = forced;
    setForcedSelection(forced);
  }, []);

  useEffect(() => {
    if (input) return;
    previewEnabledRef.current = false;
    setPreviewEnabled(false);
  }, [input]);

  useLayoutEffect(() => {
    if (draftRevisionRef.current === draftRevision) return;
    draftRevisionRef.current = draftRevision;
    setSeenRevision(draftRevision);
    previewEnabledRef.current = false;
    setPreviewEnabled(false);
    mathBarOpenRef.current = false;
    setMathBarOpen(false);
    resumeMathRef.current = false;
    setResumeMathOnFocus(false);
    pinRef.current = null;
    commitSelection({ start: input.length, end: input.length }, undefined);
  }, [commitSelection, draftRevision, input]);

  const pinSelection = useCallback((sel: TextSelection) => {
    pinRef.current = sel;
    commitSelection(sel, sel);
  }, [commitSelection]);

  useLayoutEffect(() => {
    if (!previewEnabledRef.current || !hasEditableMath(input)) return;
    const pin = pinRef.current ?? selection;
    const healed = healDroppedCommandSlash(input, pin.start, pin.end);
    if (healed.text === input) return;
    textRef.current = healed.text;
    setInput(healed.text);
    pinSelection({ start: healed.start, end: healed.end });
  }, [input, pinSelection, selection, setInput, textRef]);

  const onSelectionChange = useCallback(
    (event: NativeSyntheticEvent<TextInputSelectionChangeEventData>) => {
      const next = event.nativeEvent.selection;
      const pinned = pinRef.current;
      // Only explicit math edits use the preview caret. Ordinary typing,
      // including dollar signs and formulas, keeps the native caret.
      // The parked TextInput keeps the OS caret in the last LaTeX slot.
      if (pinned && previewEnabledRef.current && hasEditableMath(textRef.current)) {
        if (next.start !== pinned.start || next.end !== pinned.end) {
          // A new object even when equal: it puts the native caret back on the pin.
          forcedSelectionRef.current = { ...pinned };
          setForcedSelection(forcedSelectionRef.current);
        }
        return;
      }
      pinRef.current = next;
      commitSelection(next, undefined);
    },
    [commitSelection, textRef],
  );

  const onChangeText = useCallback(
    (next: string) => {
      const previous = textRef.current;
      const pin = pinRef.current ?? selection;
      const parked = previewEnabledRef.current && hasEditableMath(previous);
      // A native edit that only knocks the `\` off `\frac` is not a delete.
      // Keep the formula, or remove one math atom, and never show `frac{…}`.
      if (parked && hasBareCommand(next) && !hasBareCommand(previous)) {
        if (droppedOnlySlash(previous, next)) {
          const removed = spliceMathBackspace(previous, pin);
          const healed = healDroppedCommandSlash(
            removed.text,
            removed.selection.start,
            removed.selection.end,
          );
          textRef.current = healed.text;
          setInput(healed.text);
          pinSelection({ start: healed.start, end: healed.end });
          return;
        }
        textRef.current = previous;
        setInput(previous);
        pinSelection(pin);
        return;
      }
      // onChangeText does not identify a paste. Rewriting its delta can
      // corrupt ordinary/coalesced typing and race the native selection.
      const range = nativeEditRange(previous, next);
      const changed = parked
        ? applyPinnedTextChange(previous, next, pin)
        : { text: next, caret: range ? range.at + range.added.length : pin.start };
      const healed = parked
        ? healDroppedCommandSlash(changed.text, changed.caret, changed.caret)
        : { text: changed.text, start: changed.caret, end: changed.caret };
      textRef.current = healed.text;
      setInput(healed.text);
      const nextSelection = { start: healed.start, end: healed.end };
      if (parked) {
        pinSelection(nextSelection);
      } else {
        pinRef.current = nextSelection;
        commitSelection(nextSelection, undefined);
      }
      if (!changed.text) {
        previewEnabledRef.current = false;
        setPreviewEnabled(false);
      }
      const delta = extractInsertedDelta(previous, next);
      if (delta && onImageOnlyPaste && shouldProbeClipboardForImagePaste(delta)) {
        void clipboardIsImageOnly().then((imageOnly) => {
          if (imageOnly) onImageOnlyPaste();
        });
      }
    },
    [commitSelection, onImageOnlyPaste, pinSelection, selection, setInput, textRef],
  );

  const openMathBar = useCallback(() => {
    if (mathBarOpenRef.current) return;
    rememberSystemKeyboard(Keyboard.metrics()?.height);
    if (hasEditableMath(textRef.current)) enablePreview();
    setPadHeight(mathPadHeight(lastSystemKeyboardHeight));
    Keyboard.dismiss();
    resumeMathRef.current = true;
    setResumeMathOnFocus(true);
    mathBarOpenRef.current = true;
    setMathBarOpen(true);
  }, [enablePreview, textRef]);

  const dismissMathBar = useCallback(() => {
    if (!mathBarOpenRef.current) return;
    mathBarOpenRef.current = false;
    setMathBarOpen(false);
  }, []);

  const onComposerFocus = useCallback(() => {
    if (!resumeMathRef.current || mathBarOpenRef.current) return;
    openMathBar();
  }, [openMathBar]);

  const insertSymbol = useCallback(
    (spec: MathKeyboardSymbol) => {
      enablePreview();
      const sel = pinRef.current ?? selection;
      const text = textRef.current;
      const jump = tapAdvancesToNextSlot(text, sel.start, spec.id);
      if (jump != null) {
        pinSelection({ start: jump, end: jump });
        return;
      }
      // A key types into the box the caret is in, operators included: `(x+1)`
      // stays together. → leaves the box.
      const result = spliceMathInsert(text, sel, spec);
      const advanced = autoAdvanceNextEmptySlot(
        text,
        sel.start,
        result.text,
        result.selection.start,
        spec,
      );
      textRef.current = result.text;
      setInput(result.text);
      pinSelection(
        advanced != null ? { start: advanced, end: advanced } : result.selection,
      );
    },
    [enablePreview, pinSelection, selection, setInput, textRef],
  );

  const backspace = useCallback(() => {
    const sel = pinRef.current ?? selection;
    const result = spliceMathBackspace(textRef.current, sel);
    const healed = healDroppedCommandSlash(result.text, result.selection.start, result.selection.end);
    textRef.current = healed.text;
    setInput(healed.text);
    pinSelection({ start: healed.start, end: healed.end });
  }, [pinSelection, selection, setInput, textRef]);

  const pasteText = useCallback(
    async (text: string) => {
      if (!text) return;
      enablePreview();
      const sel = pinRef.current ?? selection;
      const before = textRef.current.slice(0, sel.start);
      const after = textRef.current.slice(sel.end);
      const convertedChunk = normalizePastedMath(text);
      const spliced = before + convertedChunk + after;
      const caret = before.length + convertedChunk.length;
      textRef.current = spliced;
      setInput(spliced);
      pinSelection({ start: caret, end: caret });
    },
    [enablePreview, pinSelection, selection, setInput, textRef],
  );

  const stepCaret = useCallback(
    (direction: "left" | "right") => {
      const sel = pinRef.current ?? selection;
      const text = textRef.current;
      let next: number;
      if (sel.start !== sel.end) {
        next = direction === "right" ? sel.end : sel.start;
      } else {
        next = direction === "right" ? caretStepRight(text, sel.start) : caretStepLeft(text, sel.start);
      }
      pinSelection({ start: next, end: next });
    },
    [pinSelection, selection, textRef],
  );

  const moveCaret = useCallback(
    (pos: number) => {
      const next = Math.max(0, Math.min(pos, textRef.current.length));
      pinSelection({ start: next, end: next });
    },
    [pinSelection, textRef],
  );

  const toggleMathBar = useCallback(() => {
    if (mathBarOpenRef.current) {
      resumeMathRef.current = false;
      setResumeMathOnFocus(false);
      mathBarOpenRef.current = false;
      const text = textRef.current;
      const caret = caretAfterMathBarClose(text);
      pinSelection({ start: caret, end: caret });
      setMathBarOpen(false);
      return;
    }
    openMathBar();
  }, [openMathBar, pinSelection, textRef]);

  return {
    mathBarOpen,
    showMathPreview: seenRevision === draftRevision && previewEnabled && hasEditableMath(input),
    padHeight,
    resumeMathOnFocus,
    toggleMathBar,
    openMathBar,
    dismissMathBar,
    onComposerFocus,
    mathGroup,
    setMathGroup,
    selection,
    forcedSelection,
    onSelectionChange,
    onChangeText,
    insertSymbol,
    backspace,
    pasteText,
    moveCaret,
    stepCaret,
    symbols: MATH_KEYBOARD_SYMBOLS,
  };
}
