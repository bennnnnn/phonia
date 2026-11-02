/**
 * Glyph runs inside native math: operator words stay upright, letter runs are
 * italic variables, and the glyphs the math face lacks or spaces differently
 * (negated relations, blackboard letters, primes, norms) get their own Text.
 */
import { type ReactNode } from "react";
import { Text } from "react-native";

import { splitOperatorPads } from "@/lib/math/layout";
import {
  AMS_ONLY_CHARS,
  BLACKBOARD_LATIN,
  MATH_NOT_GLYPH,
  NEGATED_RELATION,
  NOT_ADVANCE_EM,
  NORM_ADVANCE_EM,
  primeRun,
} from "@/lib/math/glyphs";

/** The size a run draws at: layout pixels per em, and the device font scale. */
type RunMetrics = { em: number; fontScale: number };

/** Operator spacing for a run; `space: false` keeps a script's operators tight. */
export type RunPad = RunMetrics & { leadingAtom: boolean; space?: boolean };

/** A run drawn without padding measures its glyphs at the stylesheet's 16px. */
const UNPADDED_METRICS: RunMetrics = { em: 16, fontScale: 1 };

/** Named operators are words, not products of variables, so they stay
 * upright in the same way KaTeX renders `sin`, `log`, and `mod`. */
const UPRIGHT_MATH_WORDS = new Set([
  "arccos", "arcsin", "arctan", "cos", "cosh", "cot", "csc", "det",
  "exp", "gcd", "if", "lim", "ln", "log", "max", "min", "mod",
  "otherwise", "rank", "sec", "sin", "sinh", "tan", "tanh", "where",
]);

// Latin and Greek letters make separate runs: `\sin\theta` reads "sinθ", and as one run
// the function name was drawn italic with its angle, a product of four variables.
const MATH_LETTER_RUN = /[A-Za-z]+|[Ͱ-Ͽ]+/g;

function isUprightWord(value: string): boolean {
  return UPRIGHT_MATH_WORDS.has(value.toLowerCase());
}

export function renderNonVariableRun(
  value: string,
  key: string,
  glyphStyle: object,
  metrics: RunMetrics,
): ReactNode[] {
  return Array.from(value).map((ch, i) => renderMathGlyph(ch, `${key}-g${i}`, glyphStyle, metrics));
}

function renderMathGlyph(
  ch: string,
  key: string,
  glyphStyle: object,
  metrics: RunMetrics,
): ReactNode {
  const negated = NEGATED_RELATION[ch];
  if (negated) {
    const shift = NOT_ADVANCE_EM * metrics.em * metrics.fontScale;
    return (
      <Text key={key} testID="math-negated" accessibilityLabel={ch}>
        <Text style={{ letterSpacing: -shift }}>{MATH_NOT_GLYPH}</Text>
        {negated.base}
      </Text>
    );
  }
  const blackboard = BLACKBOARD_LATIN[ch];
  if (blackboard) {
    return (
      <Text key={key} testID="math-blackboard" style={glyphStyle}>
        {blackboard}
      </Text>
    );
  }
  if (AMS_ONLY_CHARS.has(ch)) {
    return (
      <Text key={key} style={glyphStyle}>
        {ch}
      </Text>
    );
  }
  const primes = primeRun(ch);
  if (primes) return primes;
  // A formula is one word in the line: "(T = mg)" drew "(T" on one line and "= mg)"
  // on the next. A no-break space measures as a space (layout.ts) but never wraps.
  if (ch === " ") return "\u00a0";
  if (ch === "-") return "−";
  if (ch === "·") return "⋅";
  if (ch === "‖") {
    const pull = (0.8 - NORM_ADVANCE_EM) * metrics.em * metrics.fontScale;
    return (
      <Text key={key} testID="math-norm" style={{ letterSpacing: -pull / 2 }}>
        ||
      </Text>
    );
  }
  return ch;
}

export function renderMathRun(
  value: string,
  key: string,
  textStyle: object,
  glyphStyle: object,
  variableStyle: object,
  testID?: string,
  pad?: RunPad,
): ReactNode {
  const pieces = pad && pad.space !== false
    ? splitOperatorPads(value, pad.leadingAtom)
    : [{ text: value, leftEm: 0, rightEm: 0 }];
  const metrics = pad ?? UNPADDED_METRICS;
  const runs = pieces.map((piece, pieceIndex) => {
    const pieceKey = pieces.length === 1 ? key : `${key}-p${pieceIndex}`;
    const children: ReactNode[] = [];
    let cursor = 0;
    let variableIndex = 0;
    for (const match of piece.text.matchAll(MATH_LETTER_RUN)) {
      const start = match.index ?? 0;
      if (start > cursor) {
        children.push(
          ...renderNonVariableRun(
            piece.text.slice(cursor, start),
            `${pieceKey}-t${cursor}`,
            glyphStyle,
            metrics,
          ),
        );
      }
      const word = match[0];
      children.push(
        isUprightWord(word) ? word : (
          <Text
            key={`${pieceKey}-v${variableIndex}`}
            testID="math-variable"
            style={[textStyle, variableStyle]}
          >
            {word}
          </Text>
        ),
      );
      variableIndex += 1;
      cursor = start + word.length;
    }
    if (cursor < piece.text.length) {
      children.push(
        ...renderNonVariableRun(
          piece.text.slice(cursor),
          `${pieceKey}-t${cursor}`,
          glyphStyle,
          metrics,
        ),
      );
    }
    // Padding, not margin: nested Text on iOS ignores margin, so the
    // measured operator space would never appear.
    const margin = pad
      ? {
          paddingLeft: piece.leftEm * pad.em * pad.fontScale,
          paddingRight: piece.rightEm * pad.em * pad.fontScale,
        }
      : null;
    return (
      <Text key={pieceKey} style={[textStyle, margin]} testID={pieces.length === 1 ? testID : undefined}>
        {children}
      </Text>
    );
  });
  if (runs.length === 1) return runs[0];
  return runs;
}
