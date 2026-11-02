import { Fragment, ReactNode } from "react";
import { Text, type StyleProp, type TextStyle } from "react-native";

import { splitStreamCaret, StreamingCursor } from "@/components/StreamingCursor";
import { MathText } from "@/components/rich/MathText";
import {
  inPlainBlockquote,
  inTableCell,
  inTableHeader,
  parentHasType,
} from "@/components/markdown/markdownAstHelpers";
import type {
  MdMathStyles,
  MdTableStyles,
  StyleMap,
} from "@/components/markdown/markdownContentStyles";
import { DisplayRow, InlineFlow } from "@/components/markdown/rules/inlineFlow";
import {
  segmentTextWithMath,
  type MathTextRun,
} from "@/components/markdown/rules/textWithMathSegments";
import { latexHasNestedMathView } from "@/lib/math/text";
import type { Theme } from "@/lib/theme";
import { Italic, Weight } from "@/lib/type";

const CHECK_TICK_RE = /([✓✔✅])/u;

type TakeCaret = (inText?: boolean) => ReactNode;

export function withGreenTicks(
  text: string,
  tickColor: string,
  keyPrefix: string,
): ReactNode {
  if (!text.includes("✓") && !text.includes("✔") && !text.includes("✅")) {
    return text;
  }
  return text.split(CHECK_TICK_RE).map((bit, i) =>
    bit === "✓" || bit === "✔" || bit === "✅" ? (
      <Text
        key={`${keyPrefix}-tick-${i}`}
        style={{ color: tickColor, ...Weight.bold }}
      >
        {bit}
      </Text>
    ) : (
      bit
    ),
  );
}

/**
 * Prose runs between display formulas, each formula a row of its own. In a
 * paragraph's flow the prose shares lines with its bold and linked neighbours.
 */
function displayRuns(
  nodeKey: string,
  runs: MathTextRun[],
  base: StyleProp<TextStyle>,
  mdMath: MdMathStyles,
  tickColor: string,
  takeCaret: TakeCaret,
): ReactNode[] {
  return runs.map((run, index) => {
    if (run.type === "formula") {
      return <DisplayRow key={`${nodeKey}-m-${run.at}`} latex={run.latex} />;
    }
    const key = `${nodeKey}-inline-${index}`;
    const nested = run.parts.some(
      (part) => part.type === "math" && latexHasNestedMathView(part.value),
    );
    const caret = index === runs.length - 1 ? takeCaret(!nested) : null;
    const children = run.parts.map((part, i) => part.type === "math"
      ? <MathText scrollOverflow key={`${key}-${i}`} latex={part.value} />
      : <Text key={`${key}-${i}`} style={base} selectable>{withGreenTicks(part.value, tickColor, key)}</Text>);
    return nested
      ? <InlineFlow key={key} style={mdMath.inlineWrap}>{children}{caret}</InlineFlow>
      : <Text key={key} style={base} selectable>{children}{caret}</Text>;
  });
}

/**
 * Each nested math View outside Text, while prose and simple math share a
 * Text run so native line wrapping can break between words.
 */
function nestedRuns(
  nodeKey: string,
  runs: MathTextRun[],
  base: StyleProp<TextStyle>,
  tickColor: string,
  takeCaret: TakeCaret,
): ReactNode[] {
  return runs.map((run, index) => {
    if (run.type === "formula") {
      return <MathText scrollOverflow key={`${nodeKey}-m-${run.at}`} latex={run.latex} />;
    }
    const key = `${nodeKey}-inline-${index}`;
    return (
      <Text key={key} style={base} selectable>
        {run.parts.map((part, i) => part.type === "math"
          ? <MathText scrollOverflow key={`${key}-${i}`} latex={part.value} />
          : withGreenTicks(part.value, tickColor, `${key}-${i}`))}
        {index === runs.length - 1 ? takeCaret(true) : null}
      </Text>
    );
  });
}

/** A text run's style where it sits: quote ink, table cell or header, bold italic, math line height. */
function textRunStyle(
  parent: unknown,
  styles: StyleMap,
  inheritedStyles: object,
  mdTable: MdTableStyles,
  runHeight: number | undefined,
) {
  return [
    styles.body,
    inheritedStyles,
    styles.text,
    // After the inherited bold/heading ink; a link keeps its own color.
    inPlainBlockquote(parent) && !parentHasType(parent, "link") && styles.quoteText,
    inTableCell(parent) && mdTable.cellInline,
    inTableHeader(parent) && mdTable.headerText,
    // Ancestor styles stack in order, so strong's Bold would hide em's Italic.
    parentHasType(parent, "em") && parentHasType(parent, "strong") && Italic.bold,
    runHeight != null && { lineHeight: runHeight },
  ];
}

function renderTextWithMath(
  node: { key: string; content: string },
  parent: unknown,
  styles: StyleMap,
  inheritedStyles: object,
  mdTable: MdTableStyles,
  mdMath: MdMathStyles,
  tickColor: string,
) {
  const marked = splitStreamCaret(node.content);
  const segments = segmentTextWithMath(marked.text);
  const { content, parts } = segments;
  const base = textRunStyle(parent, styles, inheritedStyles, mdTable, segments.runHeight);
  let caretLeft = marked.caret;
  const takeCaret = (inText = false): ReactNode => {
    if (!caretLeft) return null;
    caretLeft = false;
    return <StreamingCursor key={`${node.key}-caret`} inline={inText} />;
  };

  if (!content && marked.caret) {
    return (
      <Text key={node.key} style={base} selectable>
        {takeCaret(true)}
      </Text>
    );
  }

  if (segments.layout === "prose") {
    return (
      <Text key={node.key} style={base} selectable>
        {withGreenTicks(content, tickColor, node.key)}
        {takeCaret(true)}
      </Text>
    );
  }

  if (segments.layout === "display") {
    const runs = displayRuns(node.key, segments.runs, base, mdMath, tickColor, takeCaret);
    if (caretLeft) runs.push(takeCaret());
    return <Fragment key={node.key}>{runs}</Fragment>;
  }

  if (segments.layout === "nested") {
    const runs = nestedRuns(node.key, segments.runs, base, tickColor, takeCaret);
    if (caretLeft) runs.push(takeCaret());
    return <Fragment key={node.key}>{runs}</Fragment>;
  }

  return (
    <Text key={node.key} style={base} selectable>
      {parts.map((part, i) =>
        part.type === "math" ? (
          <MathText scrollOverflow key={`${node.key}-m-${i}`} latex={part.value} />
        ) : (
          withGreenTicks(part.value, tickColor, `${node.key}-t-${i}`)
        ),
      )}
      {takeCaret(true)}
    </Text>
  );
}

export function textRules(t: Theme, mdTable: MdTableStyles, mdMath: MdMathStyles) {
  return {
    text: (
      node: { key: string; content: string },
      _children: unknown,
      parent: unknown,
      styles: StyleMap,
      inheritedStyles: object = {},
    ) =>
      renderTextWithMath(
        node,
        parent,
        styles,
        inheritedStyles,
        mdTable,
        mdMath,
        t.success,
      ),
  };
}
