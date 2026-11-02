import { render } from "@testing-library/react-native";

import { AnswerBlock } from "@/components/rich/AnswerBlock";

jest.mock("@/components/rich/MathText", () => {
  const { Text: RNText } = jest.requireActual("react-native");
  return {
    MathText: ({ latex }: { latex: string }) => <RNText testID="math-text">{latex}</RNText>,
  };
});

jest.mock("@/components/rich/MathSvgView", () => {
  const { Text: RNText } = jest.requireActual("react-native");
  return {
    MathSvgView: () => <RNText testID="math-svg">svg</RNText>,
  };
});

jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: { text?: string }) =>
      key === "rich.answer_a11y" && opts?.text != null ? `Answer: ${opts.text}` : key,
  }),
}));

describe("AnswerBlock chemistry notation", () => {
  it("renders the formula as text and does not typeset it", async () => {
    const formula = "M(H2O) = 18.015 g/mol";
    const { getByTestId, getByText, queryByTestId } = await render(
      <AnswerBlock content={`verified: true\nnotation: chemistry\n${formula}`} />,
    );
    expect(getByTestId("answer-literal").props.children).toBe(formula);
    expect(getByText(formula)).toBeTruthy();
    expect(queryByTestId("math-text")).toBeNull();
    expect(queryByTestId("math-svg")).toBeNull();
    expect(getByTestId("answer-success-check")).toBeTruthy();
  });

  it("draws no check on a chemistry body without the server's marker", async () => {
    const { queryByTestId } = await render(
      <AnswerBlock content={"notation: chemistry\nM(H2O) = 18.015 g/mol"} />,
    );
    expect(queryByTestId("answer-success-check")).toBeNull();
  });
});
