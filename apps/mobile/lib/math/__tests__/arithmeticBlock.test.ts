import { parseArithmeticWork, parseFractionWork } from "@/lib/math/arithmeticBlock";

function addition(overrides: Record<string, unknown> = {}) {
  return JSON.stringify({
    type: "arithmetic",
    operation: "addition",
    operator: "+",
    expression: "478 + 356",
    operands: ["478", "356"],
    working_operands: ["478", "356"],
    answer: "834",
    decimal_places: 0,
    addition_columns: [
      {
        position: 0,
        place: "ones",
        addends: [8, 6],
        carry_in: 0,
        result_digit: 4,
        carry_out: 1,
      },
    ],
    subtraction_columns: [],
    regrouped_minuend: [],
    partial_products: [],
    quotient: null,
    remainder: null,
    division_steps: [],
    explanations: ["Ones: 8 + 6 = 14. Write 4; carry 1."],
    ...overrides,
  });
}

describe("parseArithmeticWork", () => {
  it("accepts a complete server-owned trace", () => {
    const parsed = parseArithmeticWork(addition());

    expect(parsed?.answer).toBe("834");
    expect(parsed?.addition_columns[0]?.carry_out).toBe(1);
  });

  it("rejects malformed JSON and traces for the wrong operation", () => {
    expect(parseArithmeticWork("not json")).toBeNull();
    expect(
      parseArithmeticWork(
        addition({ operation: "division", quotient: null, division_steps: [] }),
      ),
    ).toBeNull();
  });

  it("rejects a spec without at least two displayed operands", () => {
    expect(parseArithmeticWork(addition({ operands: ["478"] }))).toBeNull();
  });

  it("accepts a complete multi-addend trace and rejects a dropped addend", () => {
    const parsed = parseArithmeticWork(
      addition({
        expression: "478 + 356 + 99",
        operands: ["478", "356", "99"],
        working_operands: ["478", "356", "99"],
        answer: "933",
        addition_columns: [
          {
            position: 0,
            place: "ones",
            addends: [8, 6, 9],
            carry_in: 0,
            result_digit: 3,
            carry_out: 2,
          },
        ],
      }),
    );
    expect(parsed?.operands).toEqual(["478", "356", "99"]);
    expect(
      parseArithmeticWork(
        addition({
          operands: ["478", "356", "99"],
          working_operands: ["478", "356", "99"],
        }),
      ),
    ).toBeNull();
  });

  it("rejects division rows without server-owned alignment data", () => {
    expect(
      parseArithmeticWork(
        addition({
          operation: "division",
          operator: "÷",
          addition_columns: [],
          quotient: "2",
          division_steps: [{ product: "4", remainder: "0" }],
        }),
      ),
    ).toBeNull();
  });
});

describe("parseFractionWork", () => {
  it("accepts a complete server-owned fraction trace", () => {
    const parsed = parseFractionWork(
      JSON.stringify({
        type: "fraction",
        operation: "add",
        operands: ["1/2", "1/3"],
        answer: "\\frac{5}{6}",
        exact_numerator: 5,
        exact_denominator: 6,
        steps: [
          {
            kind: "common_denominator",
            explanation: "Use denominator 6.",
            expression: "\\frac{3}{6}+\\frac{2}{6}",
            result: "\\frac{5}{6}",
          },
        ],
      }),
    );
    expect(parsed?.exact_numerator).toBe(5);
  });

  it("accepts a unary fraction conversion trace", () => {
    const parsed = parseFractionWork(
      JSON.stringify({
        type: "fraction",
        operation: "improper_to_mixed",
        operands: ["29/4"],
        answer: "7\\frac{1}{4}",
        exact_numerator: 29,
        exact_denominator: 4,
        steps: [
          {
            kind: "convert",
            explanation: "Divide and use the remainder as the numerator.",
            expression: "29\\div 4",
            result: "7 R1",
          },
        ],
      }),
    );

    expect(parsed?.operation).toBe("improper_to_mixed");
    expect(parsed?.operands).toEqual(["29/4"]);
  });

  it("rejects a fraction card without solver-owned steps", () => {
    expect(
      parseFractionWork(
        JSON.stringify({
          type: "fraction",
          operation: "simplify",
          operands: ["8/12"],
          answer: "\\frac{2}{3}",
          steps: [],
        }),
      ),
    ).toBeNull();
  });
});
