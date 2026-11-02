import { fireEvent, render } from "@testing-library/react-native";

import { CalculatorBlock } from "@/components/rich/CalculatorBlock";
import { clearCalculatorPositions } from "@/lib/money/calculatorPositions";
import { cardFence, loanFence } from "@/lib/money/__tests__/loanFence";

// The real English strings, so a key missing from en.json shows up as a raw key.
jest.mock("react-i18next", () => {
  const english = jest.requireActual("@/lib/i18n/en.json") as Record<string, string>;
  const fill = (text: string, options?: Record<string, unknown>) =>
    text.replace(/\{\{(\w+)\}\}/g, (_, name: string) => String(options?.[name]));
  const t = (key: string, options?: Record<string, unknown>) => {
    if (typeof options?.count === "number") {
      const plural = english[`${key}_${options.count === 1 ? "one" : "other"}`];
      if (plural) return fill(plural, options);
    }
    return fill(String(english[key] ?? key), options);
  };
  return {
    useTranslation: () => ({ t, i18n: { language: "en" } }),
    initReactI18next: { type: "3rdParty", init: () => undefined },
  };
});

jest.mock("@/lib/theme", () => {
  const actual = jest.requireActual("@/lib/theme");
  return { ...actual, useTheme: () => actual.lightTheme };
});

jest.mock("@/ui/icons/Icon", () => ({ Icon: () => null }));

const fence = (body: unknown) => <CalculatorBlock content={JSON.stringify(body)} />;
const step = (track: unknown, actionName: "increment" | "decrement") =>
  fireEvent(track as never, "accessibilityAction", { nativeEvent: { actionName } });

beforeEach(() => clearCalculatorPositions());

describe("CalculatorBlock", () => {
  it("draws the mortgage at the asked values, with today's average on the rate", async () => {
    const view = await render(fence(loanFence()));
    expect(view.getByText("Mortgage")).toBeTruthy();
    expect(view.getByText("Monthly payment")).toBeTruthy();
    expect(view.getByTestId("calculator-readout-payment")).toHaveTextContent("$964.92");
    expect(view.getByTestId("calculator-readout-total")).toHaveTextContent("$347,371");
    expect(view.getByTestId("calculator-readout-interest")).toHaveTextContent("$47,371");
    expect(view.getByTestId("calculator-slider-amount-value")).toHaveTextContent("$300,000");
    expect(view.getByTestId("calculator-slider-rate-value")).toHaveTextContent("1%");
    expect(view.getByTestId("calculator-slider-years-value")).toHaveTextContent("30 years");
    expect(view.getByText("Avg 6.27% · Oct 16")).toBeTruthy();
    expect(view.getByTestId("calculator-source")).toHaveTextContent(
      "Average from Freddie Mac via FRED, Oct 16, 2026",
    );
    expect(view.queryByTestId("calculator-reset")).toBeNull();
  });

  it("recomputes as a slider moves, and resets to the asked values", async () => {
    const view = await render(fence(loanFence()));
    await fireEvent.press(view.getByRole("button", { name: "Today's average, 6.27%, as of Oct 16. Tap to use it." }));
    expect(view.getByTestId("calculator-slider-rate-value")).toHaveTextContent("6.27%");
    expect(view.getByTestId("calculator-readout-payment")).toHaveTextContent("$1,851.06");

    await step(view.getByTestId("calculator-slider-years-track"), "decrement");
    expect(view.getByTestId("calculator-slider-years-value")).toHaveTextContent("29 years");

    await fireEvent.press(view.getByTestId("calculator-reset"));
    expect(view.getByTestId("calculator-readout-payment")).toHaveTextContent("$964.92");
    expect(view.getByTestId("calculator-slider-years-value")).toHaveTextContent("30 years");
    expect(view.queryByTestId("calculator-reset")).toBeNull();
  });

  it("keeps the sliders where they were when the list draws the card again", async () => {
    const body = loanFence();
    const first = await render(fence(body));
    await step(first.getByTestId("calculator-slider-years-track"), "decrement");
    await first.unmount();
    const again = await render(fence(body));
    expect(again.getByTestId("calculator-slider-years-value")).toHaveTextContent("29 years");
  });

  it("says a card payment never pays it off, and counts the months once it does", async () => {
    const view = await render(fence(cardFence(100)));
    expect(view.getByText("Credit card payoff")).toBeTruthy();
    expect(view.getByTestId("calculator-readout-months")).toHaveTextContent("Never at this payment");
    const paying = await render(fence(cardFence(200)));
    expect(paying.getByTestId("calculator-readout-months")).toHaveTextContent(/^\d+ months$/);
  });

  it("draws nothing for a body it does not understand", async () => {
    const broken = await render(<CalculatorBlock content='{"v": 2, "controls": []}' />);
    expect(broken.toJSON()).toBeNull();
    const streaming = await render(<CalculatorBlock content='{"v": 1, "controls": [' />);
    expect(streaming.toJSON()).toBeNull();
  });

  it("falls back to a known title when the server names one this app has no text for", async () => {
    const view = await render(fence(loanFence({ title_key: "money.title.boat" })));
    expect(view.getByText("Loan")).toBeTruthy();
  });
});
