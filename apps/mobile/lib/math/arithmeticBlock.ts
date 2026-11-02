import { isJsonRecord, parseJsonRecord } from "@/lib/jsonFence";

type ArithmeticOperation =
  | "addition"
  | "subtraction"
  | "multiplication"
  | "division";

type AdditionColumn = {
  position: number;
  place: string;
  addends: number[];
  carry_in: number;
  result_digit: number;
  carry_out: number;
};

type SubtractionColumn = {
  position: number;
  place: string;
  top_digit: number;
  bottom_digit: number;
  working_top: number;
  result_digit: number;
  regrouped_from: string[];
};

type PartialProduct = {
  position: number;
  place: string;
  multiplier_digit: number;
  unshifted_product: string;
  shifted_product: string;
  columns: MultiplicationColumn[];
};

type MultiplicationColumn = {
  position: number;
  place: string;
  multiplicand_digit: number;
  carry_in: number;
  result_digit: number;
  carry_out: number;
};

type DivisionStep = {
  index: number;
  column_end: number;
  partial_dividend: string;
  quotient_digit: number;
  product: string;
  remainder: string;
  bring_down?: number | null;
  next_partial?: string | null;
};

export type ArithmeticWorkSpec = {
  type: "arithmetic";
  operation: ArithmeticOperation;
  operator: "+" | "−" | "×" | "÷";
  expression: string;
  operands: string[];
  working_operands: string[];
  answer: string;
  decimal_places: number;
  addition_columns: AdditionColumn[];
  subtraction_columns: SubtractionColumn[];
  regrouped_minuend: string[];
  partial_products: PartialProduct[];
  quotient?: string | null;
  remainder?: string | null;
  answer_mode?:
    | "exact"
    | "remainder"
    | "fraction"
    | "decimal"
    | "round_up"
    | "discard";
  division_steps: DivisionStep[];
  explanations: string[];
};

type FractionStep = {
  kind: string;
  explanation: string;
  expression: string;
  result: string;
};

export type FractionWorkSpec = {
  type: "fraction";
  operation:
    | "simplify"
    | "equivalent"
    | "add"
    | "subtract"
    | "multiply"
    | "divide"
    | "mixed_to_improper"
    | "improper_to_mixed"
    | "of_quantity"
    | "compare";
  operands: string[];
  answer: string;
  exact_numerator?: number | null;
  exact_denominator?: number | null;
  steps: FractionStep[];
};

function stringOperands(value: unknown): value is string[] {
  return (
    Array.isArray(value) &&
    value.length >= 2 &&
    value.length <= 6 &&
    value.every((item) => typeof item === "string")
  );
}

function fractionOperands(value: unknown): value is string[] {
  return (
    Array.isArray(value) &&
    value.length >= 1 &&
    value.length <= 6 &&
    value.every((item) => typeof item === "string")
  );
}

/** Parse server-owned procedure data. The client never derives the arithmetic. */
export function parseArithmeticWork(raw: string): ArithmeticWorkSpec | null {
  const data = parseJsonRecord(raw);
  if (!data || data.type !== "arithmetic") return null;
  if (
    !["addition", "subtraction", "multiplication", "division"].includes(
      String(data.operation),
    ) ||
    !["+", "−", "×", "÷"].includes(String(data.operator)) ||
    typeof data.expression !== "string" ||
    !stringOperands(data.operands) ||
    !stringOperands(data.working_operands) ||
    typeof data.answer !== "string" ||
    typeof data.decimal_places !== "number" ||
    !Array.isArray(data.explanations) ||
    !data.explanations.every((item) => typeof item === "string")
  ) {
    return null;
  }
  if (
    data.operands.length !== data.working_operands.length ||
    (data.operation !== "addition" && data.operands.length !== 2)
  ) {
    return null;
  }
  const operandCount = data.operands.length;
  const additionColumns = data.addition_columns;
  const subtractionColumns = data.subtraction_columns;
  const regroupedMinuend = data.regrouped_minuend;
  const partialProducts = data.partial_products;
  const divisionSteps = data.division_steps;
  if (
    !Array.isArray(additionColumns) ||
    !Array.isArray(subtractionColumns) ||
    !Array.isArray(regroupedMinuend) ||
    !Array.isArray(partialProducts) ||
    !Array.isArray(divisionSteps)
  ) {
    return null;
  }
  const trace = {
    addition:
      additionColumns.length > 0 &&
      additionColumns.every(
        (column) =>
          isJsonRecord(column) &&
          typeof column.position === "number" &&
          Array.isArray(column.addends) &&
          column.addends.length === operandCount &&
          typeof column.carry_out === "number",
      ),
    subtraction:
      subtractionColumns.length > 0 &&
      subtractionColumns.every(
        (column) =>
          isJsonRecord(column) &&
          typeof column.position === "number" &&
          Array.isArray(column.regrouped_from),
      ),
    multiplication:
      partialProducts.length > 0 &&
      partialProducts.every(
        (product) =>
          isJsonRecord(product) &&
          typeof product.shifted_product === "string" &&
          Array.isArray(product.columns),
      ),
    division:
      divisionSteps.length > 0 &&
      typeof data.quotient === "string" &&
      divisionSteps.every(
        (step) =>
          isJsonRecord(step) &&
          typeof step.column_end === "number" &&
          typeof step.product === "string" &&
          typeof step.remainder === "string",
      ),
  } as const;
  if (!trace[data.operation as ArithmeticOperation]) return null;
  return data as ArithmeticWorkSpec;
}

export function parseFractionWork(raw: string): FractionWorkSpec | null {
  const data = parseJsonRecord(raw);
  if (!data || data.type !== "fraction") return null;
  if (
    ![
      "simplify",
      "equivalent",
      "add",
      "subtract",
      "multiply",
      "divide",
      "mixed_to_improper",
      "improper_to_mixed",
      "of_quantity",
      "compare",
    ].includes(String(data.operation)) ||
    !fractionOperands(data.operands) ||
    typeof data.answer !== "string" ||
    !Array.isArray(data.steps) ||
    data.steps.length === 0 ||
    !data.steps.every(
      (step) =>
        isJsonRecord(step) &&
        typeof step.kind === "string" &&
        typeof step.explanation === "string" &&
        typeof step.expression === "string" &&
        typeof step.result === "string",
    )
  ) {
    return null;
  }
  return data as FractionWorkSpec;
}
