import { useMemo } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { MathText } from "@/components/rich/MathText";
import { StepList } from "@/components/rich/StepList";
import { TeachingCard } from "@/components/rich/TeachingCard";
import { useFenceRefused } from "@/components/rich/useFenceRefused";
import { MATH_FONT, mathFace } from "@/lib/fonts";
import { parseArithmeticWork, parseFractionWork } from "@/lib/math/arithmeticBlock";
import { parseTeaching } from "@/lib/math/teachingBlock";
import type { ArithmeticWorkSpec, FractionWorkSpec } from "@/lib/math/arithmeticBlock";
import { Space } from "@/lib/space";
import { Theme, useTheme } from "@/lib/theme";
import { Type } from "@/lib/type";

const CELL_WIDTH = 25;
const DOT_WIDTH = 12;

function cells(value: string, width: number): string[] {
  return value.padStart(width, " ").split("");
}

function DigitRow({
  value,
  width,
  operator,
  muted = false,
  testID,
}: {
  value: string;
  width: number;
  operator?: string;
  muted?: boolean;
  testID?: string;
}) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  return (
    <View style={s.digitRow} testID={testID} accessibilityLabel={value.trim()}>
      <Text style={[s.operator, muted && s.muted]}>{operator ?? " "}</Text>
      <DigitCells value={value} width={width} muted={muted} />
    </View>
  );
}

function DigitCells({
  value,
  width,
  muted = false,
  testID,
}: {
  value: string;
  width: number;
  muted?: boolean;
  testID?: string;
}) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  return (
    <View style={s.digitRow} testID={testID} accessibilityLabel={value.trim()}>
      {cells(value, width).map((char, index) => (
        <Text
          key={`${index}-${char}`}
          style={[s.digit, char === "." && s.dot, muted && s.muted]}
        >
          {char}
        </Text>
      ))}
    </View>
  );
}

function annotationRow(
  template: string,
  width: number,
  annotations: Map<number, string>,
): { label: string; dot: boolean }[] {
  const padded = cells(template, width);
  let position = 0;
  const row = Array.from({ length: padded.length }, () => ({ label: " ", dot: false }));
  for (let index = padded.length - 1; index >= 0; index -= 1) {
    const char = padded[index];
    if (char === ".") {
      row[index] = { label: ".", dot: true };
      continue;
    }
    if (char === "-") continue;
    row[index] = { label: annotations.get(position) ?? " ", dot: false };
    position += 1;
  }
  return row;
}

function annotationLabel(row: { label: string }[]): string {
  return row.map(({ label }) => label).join("").trim();
}

function AnnotationRow({
  spec,
  width,
}: {
  spec: ArithmeticWorkSpec;
  width: number;
}) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const annotations = new Map<number, string>();
  if (spec.operation === "addition") {
    spec.addition_columns.forEach((column) => {
      if (column.carry_out) annotations.set(column.position + 1, String(column.carry_out));
    });
  } else {
    const didRegroup = spec.subtraction_columns.some(
      (column) => column.regrouped_from.length > 0,
    );
    if (!didRegroup) return null;
    [...spec.regrouped_minuend].reverse().forEach((value, position) => {
      annotations.set(position, value);
    });
  }
  const row = annotationRow(spec.working_operands[0], width, annotations);
  return (
    <View
      style={s.digitRow}
      testID="arithmetic-annotation-row"
      accessibilityLabel={annotationLabel(row)}
    >
      <Text style={s.operator}> </Text>
      {row.map(({ label, dot }, index) => (
        <Text key={index} style={[s.annotation, dot && s.dot]}>
          {label}
        </Text>
      ))}
    </View>
  );
}

function ColumnWork({ spec }: { spec: ArithmeticWorkSpec }) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const width = Math.max(
    spec.answer.length,
    ...spec.working_operands.map((value) => value.length),
  );
  return (
    <View style={s.work}>
      <AnnotationRow spec={spec} width={width} />
      {spec.working_operands.map((operand, index) => {
        const last = index === spec.working_operands.length - 1;
        const testID =
          index === 0
            ? "arithmetic-top-row"
            : last
              ? "arithmetic-bottom-row"
              : `arithmetic-operand-row-${index}`;
        return (
          <DigitRow
            key={`${index}-${operand}`}
            value={operand}
            width={width}
            operator={last ? spec.operator : undefined}
            testID={testID}
          />
        );
      })}
      <View style={[s.rule, { width: width * CELL_WIDTH + CELL_WIDTH }]} />
      <DigitRow value={spec.answer} width={width} testID="arithmetic-result-row" />
    </View>
  );
}

function MultiplicationWork({ spec }: { spec: ArithmeticWorkSpec }) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const rows = spec.partial_products.map((product) => product.shifted_product);
  const width = Math.max(
    spec.answer.length,
    ...spec.working_operands.map((value) => value.length),
    ...rows.map((value) => value.length),
  );
  return (
    <View style={s.work}>
      <DigitRow value={spec.working_operands[0]} width={width} />
      <DigitRow value={spec.working_operands[1]} width={width} operator="×" />
      <View style={[s.rule, { width: width * CELL_WIDTH + CELL_WIDTH }]} />
      {spec.partial_products.map((product, index) => {
        const annotations = new Map<number, string>();
        product.columns.forEach((column) => {
          if (column.carry_out) {
            annotations.set(
              column.position + product.position + 1,
              String(column.carry_out),
            );
          }
        });
        const carryRow = annotationRow(product.shifted_product, width, annotations);
        return (
          <View key={`${index}-${product.shifted_product}`}>
            {annotations.size ? (
              <View
                style={s.digitRow}
                testID={`arithmetic-multiplication-carries-${index}`}
                accessibilityLabel={annotationLabel(carryRow)}
              >
                <Text style={s.operator}> </Text>
                {carryRow.map(({ label, dot }, carryIndex) => (
                  <Text key={carryIndex} style={[s.annotation, dot && s.dot]}>
                    {label}
                  </Text>
                ))}
              </View>
            ) : null}
            <DigitRow
              value={product.shifted_product}
              width={width}
              muted={rows.length > 1}
              testID={`arithmetic-partial-product-${index}`}
            />
          </View>
        );
      })}
      {rows.length > 1 ? (
        <View style={[s.rule, { width: width * CELL_WIDTH + CELL_WIDTH }]} />
      ) : null}
      <DigitRow value={spec.answer} width={width} testID="arithmetic-result-row" />
    </View>
  );
}

function displayColumnEnd(dividend: string, digitColumnEnd: number): number {
  const decimalIndex = dividend.indexOf(".");
  if (decimalIndex >= 0 && digitColumnEnd >= decimalIndex) return digitColumnEnd + 1;
  return digitColumnEnd;
}

function positionedValue(value: string, end: number, width: number): string {
  const row = Array.from({ length: width }, () => " ");
  const start = Math.max(0, end - value.length + 1);
  value.split("").forEach((char, index) => {
    if (start + index < row.length) row[start + index] = char;
  });
  return row.join("");
}

function DivisionWork({ spec }: { spec: ArithmeticWorkSpec }) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const dividend = spec.working_operands[0] ?? "";
  const divisor = spec.working_operands[1] ?? "";
  const width = dividend.length;
  return (
    <View style={s.divisionWork} testID="arithmetic-division-layout">
      <View style={s.quotientRow}>
        <Text style={s.divisorSpacer}>{divisor}</Text>
        <DigitCells
          value={spec.quotient ?? ""}
          width={width}
          testID="arithmetic-quotient"
        />
      </View>
      <View style={s.dividendRow}>
        <Text style={s.divisor}>{divisor}</Text>
        <View style={s.dividendBracket}>
          <DigitCells value={dividend} width={width} testID="arithmetic-dividend" />
        </View>
      </View>
      <View style={s.divisionSteps}>
        <Text style={s.divisorSpacer}>{divisor}</Text>
        <View style={s.divisionStepDigits}>
          {spec.division_steps.map((step) => {
            const productEnd = displayColumnEnd(dividend, step.column_end);
            const nextEnd = displayColumnEnd(
              dividend,
              step.column_end + (step.bring_down == null ? 0 : 1),
            );
            const nextValue = step.next_partial ?? step.remainder;
            const ruleDigits = Math.max(
              step.partial_dividend.length,
              step.product.length,
            );
            const trailing = Math.max(0, width - productEnd - 1);
            return (
              <View key={step.index} testID={`arithmetic-division-step-${step.index}`}>
                <DigitRow
                  value={positionedValue(step.product, productEnd, width)}
                  width={width}
                  operator="−"
                  muted
                  testID={`arithmetic-division-product-${step.index}`}
                />
                <View
                  style={[
                    s.divisionRule,
                    {
                      width: ruleDigits * CELL_WIDTH,
                      marginRight: trailing * CELL_WIDTH,
                    },
                  ]}
                />
                <DigitRow
                  value={positionedValue(nextValue, nextEnd, width)}
                  width={width}
                />
              </View>
            );
          })}
        </View>
      </View>
    </View>
  );
}

/** The server writes this fence as JSON. */
const ARITHMETIC_BODY = { json: true };

export function ArithmeticWorkBlock({ content }: { content: string }) {
  const teaching = parseTeaching(content);
  const spec = teaching ? null : parseArithmeticWork(content);
  const fraction = teaching || spec ? null : parseFractionWork(content);
  useFenceRefused("arithmetic", content, !teaching && !spec && !fraction, ARITHMETIC_BODY);
  // Bonds, dot arrays, and ten frames repeat the fact the answer line states.
  if (
    teaching?.type === "number_bond" ||
    teaching?.type === "array" ||
    teaching?.type === "ten_frame"
  ) {
    return null;
  }
  if (teaching) return <TeachingCard spec={teaching} />;
  if (!spec) return fraction ? <FractionWork spec={fraction} /> : null;
  const layout =
    spec.operation === "addition" || spec.operation === "subtraction" ? (
      <ColumnWork spec={spec} />
    ) : spec.operation === "multiplication" ? (
      <MultiplicationWork spec={spec} />
    ) : (
      <DivisionWork spec={spec} />
    );
  return (
    <View style={styles.arithmeticWork} testID="arithmetic-work-inline">
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.workScroll}
        contentContainerStyle={styles.workScrollContent}
        testID="arithmetic-work-scroll"
      >
        {layout}
      </ScrollView>
      <View style={styles.steps}>
        <StepList steps={spec.explanations} />
      </View>
    </View>
  );
}

function FractionWork({ spec }: { spec: FractionWorkSpec }) {
  const theme = useTheme();
  return (
    <View style={styles.fractionWork} testID="fraction-work-inline">
      {spec.steps.map((step, index) => (
        <View key={`${index}-${step.kind}`} style={styles.fractionStep}>
          <Text style={[styles.fractionExplanation, { color: theme.textSecondary }]}>
            {`${index + 1}. ${step.explanation}`}
          </Text>
          <View testID={`fraction-step-${index}`}>
            <MathText latex={`${step.expression} = ${step.result}`} textColor={theme.text} />
          </View>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  arithmeticWork: { alignSelf: "stretch", marginVertical: Space.xs },
  workScroll: { alignSelf: "stretch" },
  workScrollContent: {
    minWidth: "100%",
    alignItems: "center",
    paddingHorizontal: Space.xs,
  },
  steps: { marginTop: Space.sm },
  fractionWork: { alignSelf: "stretch", gap: Space.md, marginVertical: Space.xs },
  fractionStep: { gap: Space.xs },
  fractionExplanation: Type.secondary,
});

function makeStyles(t: Theme) {
  return StyleSheet.create({
    work: { alignSelf: "center", alignItems: "flex-end", paddingVertical: Space.xs },
    digitRow: { flexDirection: "row", alignItems: "flex-end" },
    operator: {
      ...Type.h1,
      width: CELL_WIDTH,
      ...mathFace(MATH_FONT),
      color: t.text,
      textAlign: "center",
    },
    digit: {
      ...Type.h1,
      width: CELL_WIDTH,
      ...mathFace(MATH_FONT),
      lineHeight: 30,
      color: t.text,
      textAlign: "center",
      fontVariant: ["tabular-nums"],
    },
    dot: { width: DOT_WIDTH },
    annotation: {
      ...Type.secondary,
      width: CELL_WIDTH,
      ...mathFace(MATH_FONT),
      lineHeight: 19,
      color: t.primary,
      textAlign: "center",
    },
    muted: { color: t.textSecondary },
    rule: {
      height: StyleSheet.hairlineWidth,
      backgroundColor: t.text,
      marginVertical: Space.xxs,
    },
    divisionWork: { alignSelf: "center", paddingVertical: Space.sm },
    quotientRow: { flexDirection: "row", alignItems: "flex-end" },
    divisorSpacer: {
      ...Type.h1,
      minWidth: 52,
      opacity: 0,
      ...mathFace(MATH_FONT),
      paddingHorizontal: Space.xs,
    },
    dividendRow: { flexDirection: "row", alignItems: "flex-start" },
    divisor: {
      ...Type.h1,
      minWidth: 52,
      ...mathFace(MATH_FONT),
      lineHeight: 34,
      color: t.text,
      textAlign: "right",
      paddingRight: Space.xs,
    },
    dividendBracket: {
      borderLeftWidth: 1.5,
      borderTopWidth: 1.5,
      borderColor: t.text,
      paddingHorizontal: Space.xs,
      paddingTop: 2,
      minWidth: 80,
    },
    divisionSteps: { flexDirection: "row", alignItems: "flex-start" },
    divisionStepDigits: { alignItems: "flex-end", paddingHorizontal: Space.xs },
    divisionRule: { height: StyleSheet.hairlineWidth, backgroundColor: t.text },
  });
}
