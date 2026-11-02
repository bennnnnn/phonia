export {
  MATH_KEYBOARD_GROUPS,
  MATH_KEYBOARD_SYMBOLS,
  spliceMathInsert,
  symbolA11yLabel,
  type MathKeyboardGroup,
  type MathKeyboardSymbol,
  type TextSelection,
} from "@/lib/math/keyboardCatalog";
export {
  autoAdvanceNextEmptySlot,
  caretInGroup,
  innermostSlot,
  readBraceGroup,
  readDelimGroup,
  readSetBrace,
  tapAdvancesToNextSlot,
  type LatexGroup,
} from "@/lib/math/keyboardSlots";
export {
  padRows,
  type PadCell,
  type SymbolPage,
} from "@/lib/math/keyboardPages";
export { caretStepLeft, caretStepRight } from "@/lib/math/caretStops";
