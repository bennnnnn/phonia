import { act, cleanup, fireEvent, render } from "@testing-library/react-native";

import { RelatedPromptLines } from "@/features/suggestions/components/RelatedPromptLines";

const PHYSICS =
  "Why is the force the product of mass and acceleration for this object?";
const MATH =
  "Why does the equation X^2 = 9 have two solutions, +3 and -3, instead of just one?";

describe("RelatedPromptLines", () => {
  afterEach(() => {
    cleanup();
  });

  it("sends the full question when the line is pressed", async () => {
    const onSelect = jest.fn();
    const { getByLabelText, getAllByRole, getAllByTestId, queryByTestId, queryByText } =
      await render(<RelatedPromptLines prompts={[MATH, PHYSICS]} onSelect={onSelect} />);

    expect(queryByText("X^2 = 9")).toBeNull();
    expect(getAllByRole("button")).toHaveLength(2);
    // A dotted underline under each question's words; no rules between rows.
    expect(getAllByTestId("related-prompt-underline")).toHaveLength(2);
    expect(queryByTestId("related-prompt-divider")).toBeNull();

    await act(async () => {
      fireEvent.press(getByLabelText(MATH));
    });
    expect(onSelect).toHaveBeenCalledWith(MATH);
    await act(async () => {
      fireEvent.press(getByLabelText(PHYSICS));
    });
    expect(onSelect).toHaveBeenLastCalledWith(PHYSICS);
  });

  it("does not offer a fragment or a glued equation", async () => {
    const onSelect = jest.fn();
    const { queryByLabelText, getByLabelText } = await render(
      <RelatedPromptLines
        prompts={["How", "Education level", String.raw`Why does $^5\sqrt{x}=0^5$ equal zero?`, MATH]}
        onSelect={onSelect}
      />,
    );

    expect(queryByLabelText("How")).toBeNull();
    expect(queryByLabelText("Education level")).toBeNull();
    fireEvent.press(getByLabelText(MATH));
    expect(onSelect).toHaveBeenCalledWith(MATH);
  });
});

describe("RelatedPromptLines in other scripts", () => {
  it("offers follow-ups written in Russian, Amharic and French", async () => {
    const prompts = [
      "Какой рис лучше всего подходит для плова?",
      "ዶሮ ወጥ ምን ያህል ጊዜ ይበስላል?",
      "Combien de temps faut-il pétrir la pâte ?",
    ];
    const onSelect = jest.fn();
    const { getAllByRole, getByLabelText } = await render(
      <RelatedPromptLines prompts={prompts} onSelect={onSelect} />,
    );

    expect(getAllByRole("button")).toHaveLength(3);
    fireEvent.press(getByLabelText(prompts[1]!));
    expect(onSelect).toHaveBeenCalledWith(prompts[1]);
  });
});

describe("RelatedPromptLines underline", () => {
  it("draws dots across the words' width once it is measured", async () => {
    const { getByTestId } = await render(
      <RelatedPromptLines prompts={[PHYSICS]} onSelect={jest.fn()} />,
    );
    const underline = getByTestId("related-prompt-underline");
    await act(async () => {
      fireEvent(underline, "layout", { nativeEvent: { layout: { width: 50, height: 2 } } });
    });
    // 2pt dots, 3pt apart: 10 across 50pt.
    expect(underline.children).toHaveLength(10);
  });
});
