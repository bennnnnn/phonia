import { ReactNode } from "react";
import { Text, View, type StyleProp, type TextStyle } from "react-native";

import { MathText } from "@/components/rich/MathText";
import { splitStreamCaret } from "@/components/StreamingCursor";
import {
  type AstNode,
  astText,
  astTextWithBreaks,
  openingStrong,
  unwrapSingle,
} from "@/components/markdown/markdownAstHelpers";
import type { StyleMap } from "@/components/markdown/markdownContentStyles";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { DYNAMIC_TYPE_MAX, Type, Weight } from "@/lib/type";
import { splitInlineMath } from "@/lib/markdown/preprocess";
import type { Theme } from "@/lib/theme";

const LESSON_STEP_RE = /^(\d+)\.\s+(\S[\s\S]*)$/;

/** A generated lesson heading, then each equation of that move on its own line. */
export function lessonStepParts(
  node: AstNode,
): { n: string; label: string; reason: string | null; formulas: string[] } | null {
  // A hard break splits the paragraph into textgroups: [heading — rule, $a$]
  // [break] [$b$]. Read them as one run, or a rule note hides the badge.
  const kids = (unwrapSingle(node).children ?? []).flatMap((kid) =>
    kid.type === "textgroup" ? (kid.children ?? []) : [kid],
  );
  const strong = openingStrong(kids[0]);
  if (!strong) return null;
  // A streaming caret's mark is never part of the step.
  const match = LESSON_STEP_RE.exec(splitStreamCaret(astText(strong)).text.trim());
  if (!match) return null;

  const tail = splitStreamCaret(
    kids
      .slice(1)
      .map((kid) => astTextWithBreaks(kid))
      .join(""),
  ).text;
  if (!tail.trim()) {
    return { n: match[1], label: match[2], reason: null, formulas: [] };
  }

  // The API emits a soft break and one `$...$` per line (the both-sides
  // equation, then the simplified equation). Anything else inline after the
  // bold heading stays ordinary Markdown.
  const parsed = lessonStepTail(tail);
  return parsed
    ? { n: match[1], label: match[2], reason: parsed.reason, formulas: parsed.formulas }
    : null;
}

function lessonStepTail(tail: string): { reason: string | null; formulas: string[] } | null {
  let rest = tail;
  let reason: string | null = null;
  // A reason sits on the heading line. A formula on that same line is ordinary
  // markdown (`**1. Result** $x^2$`); the working puts each equation on the next line.
  const reasonMatch = /^[ \t]*—\s*([^\n]*)/.exec(rest);
  if (reasonMatch) {
    reason = reasonMatch[1].trim() || null;
    rest = rest.slice(reasonMatch[0].length);
  }
  if (!/^\s*\n/.test(rest)) return null;
  const lines = rest
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  if (!lines.length) return null;
  const formulas: string[] = [];
  for (const line of lines) {
    const formula = /^\$([^$\n]+)\$$/.exec(line);
    if (!formula) return null;
    formulas.push(formula[1].trim());
  }
  return { reason, formulas };
}

function lessonLabelNodes(
  label: string,
  keyPrefix: string,
  textStyle: StyleProp<TextStyle>,
  textColor: string,
): ReactNode {
  const operand = stepOperand(label);
  if (operand && !label.includes("$")) {
    return (
      <Text key={keyPrefix} style={textStyle} selectable>
        {operand.prefix}
        <Text style={Weight.bold}>{operand.operand}</Text>
        {operand.suffix}
      </Text>
    );
  }
  return splitInlineMath(label).map((part, i) =>
    part.type === "math" ? (
      <MathText
        scrollOverflow
        key={`${keyPrefix}-m-${i}`}
        latex={part.value}
        textColor={textColor}
      />
    ) : (
      <Text key={`${keyPrefix}-t-${i}`} style={textStyle} selectable>
        {boldOperandText(part.value, operand)}
      </Text>
    ),
  );
}

function boldOperandText(
  value: string,
  operand: { prefix: string; operand: string; suffix: string } | null,
): ReactNode {
  if (!operand || operand.operand.includes("$") || !value.includes(operand.operand)) return value;
  const at = value.indexOf(operand.operand);
  return (
    <>
      {value.slice(0, at)}
      <Text style={Weight.bold}>{operand.operand}</Text>
      {value.slice(at + operand.operand.length)}
    </>
  );
}

/** The amount a both-sides move acts on, so "Subtract 4" can bold the 4. */
function stepOperand(label: string): { prefix: string; operand: string; suffix: string } | null {
  const subtract = /^(Subtract |Add )(.+?)( from both sides[\s\S]*| to both sides[\s\S]*)$/.exec(
    label,
  );
  if (subtract) return { prefix: subtract[1], operand: subtract[2], suffix: subtract[3] };
  const scale = /^(Divide both sides by |Multiply both sides by )(.+)$/.exec(label);
  if (scale) return { prefix: scale[1], operand: scale[2], suffix: "" };
  return null;
}

/** A lesson step: its number in a pill and the move, then the reason and each equation. */
export function renderLessonStep(
  key: string,
  step: { n: string; label: string; reason: string | null; formulas: string[] },
  styles: StyleMap,
  t: Theme,
): React.ReactElement {
  return (
    // A little extra space above each step so its lines read as one block.
    <View key={key} testID="lesson-step" style={[styles.paragraphRun, { marginTop: Space.xs }]}>
      <View
        style={{
          flexDirection: "row",
          alignItems: "center",
          gap: Space.xs,
        }}
      >
        <View
          style={{
            // A pill once large text makes the number wider than 22pt.
            minWidth: 22,
            minHeight: 22,
            paddingHorizontal: Space.xxs,
            borderRadius: Radius.full,
            backgroundColor: t.surfaceAlt,
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <Text
            style={{ ...Type.caption, ...Weight.bold, color: t.text }}
            maxFontSizeMultiplier={DYNAMIC_TYPE_MAX}
          >
            {step.n}
          </Text>
        </View>
        <View
          testID="lesson-step-label"
          style={{
            flex: 1,
            flexDirection: "row",
            flexWrap: "wrap",
            alignItems: "center",
          }}
        >
          {lessonLabelNodes(
            step.label,
            `${key}-label`,
            [styles.body, styles.text, Weight.semibold, { color: t.assistantText }],
            t.assistantText,
          )}
        </View>
      </View>
      {step.reason || step.formulas.length ? (
        <View testID="lesson-step-formula" style={{ paddingLeft: Space.xl, gap: Space.xxs }}>
          {step.reason ? (
            <View
              testID="lesson-step-reason"
              // The rule under the step: smaller and dimmer than the working.
              style={{
                flexDirection: "row",
                flexWrap: "wrap",
                alignItems: "center",
                marginBottom: Space.xxs,
              }}
            >
              {splitInlineMath(step.reason).map((part, i) =>
                part.type === "math" ? (
                  <MathText
                    scrollOverflow
                    key={`${key}-reason-m-${i}`}
                    latex={part.value}
                    textColor={t.textTertiary}
                    fontSize={Type.secondary.fontSize}
                  />
                ) : (
                  <Text
                    key={`${key}-reason-t-${i}`}
                    style={[styles.text, Type.secondary, { color: t.textTertiary }]}
                    maxFontSizeMultiplier={DYNAMIC_TYPE_MAX}
                    selectable
                  >
                    {part.value}
                  </Text>
                ),
              )}
            </View>
          ) : null}
          {step.formulas.map((formula, i) => (
            <MathText
              scrollOverflow
              key={`${key}-formula-${i}`}
              latex={formula}
            />
          ))}
        </View>
      ) : null}
    </View>
  );
}
