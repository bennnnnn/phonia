import { render } from "@testing-library/react-native";

import { ArrayBlock } from "@/components/rich/ArrayBlock";

jest.mock("@/lib/i18n", () => ({
  __esModule: true,
  default: {
    t: (key: string, args?: { index?: number }) =>
      args ? `${key}:${args.index}` : key,
  },
}));

describe("ArrayBlock", () => {
  it("draws each value over its index, with the caption and note under them", async () => {
    const view = await render(
      <ArrayBlock
        content={JSON.stringify({
          name: "nums",
          values: [2, 7, 11, 15],
          highlight: [0, 1],
          caption: "2 + 7 = 9",
          note: "We return indexes, not the numbers.",
        })}
      />,
    );
    expect(view.getByText("11")).toBeTruthy();
    expect(view.getByText("rich.array_index:3")).toBeTruthy();
    expect(view.getByText("2 + 7 = 9")).toBeTruthy();
    expect(view.getByText("We return indexes, not the numbers.")).toBeTruthy();
    expect(view.getByLabelText("nums = [2, 7, 11, 15]")).toBeTruthy();
  });

  it("puts the title above the boxes and reads markdown in the note", async () => {
    const view = await render(
      <ArrayBlock
        content={JSON.stringify({
          title: "Think of a Python list as a row of numbered boxes.",
          values: [18, 25, 32, 40],
          note: "Python starts counting indexes at **0**, not 1.",
        })}
      />,
    );
    expect(
      view.getByText("Think of a Python list as a row of numbered boxes."),
    ).toBeTruthy();
    expect(view.getByText("0")).toBeTruthy();
    expect(view.getByText("Python starts counting indexes at 0, not 1.")).toBeTruthy();
  });

  it("scrolls a long list sideways", async () => {
    const values = Array.from({ length: 10 }, (_, i) => i);
    const view = await render(
      <ArrayBlock content={JSON.stringify({ values })} />,
    );
    expect(view.getByText("rich.array_index:9")).toBeTruthy();
  });

  it("draws nothing while the list is still streaming in", async () => {
    const view = await render(<ArrayBlock content='{"values": [1, 2' />);
    expect(view.toJSON()).toBeNull();
  });

  it("draws nothing for a list with no values", async () => {
    const view = await render(<ArrayBlock content='{"values": []}' />);
    expect(view.toJSON()).toBeNull();
  });

  it("shows a list with broken JSON as text", async () => {
    const view = await render(
      <ArrayBlock
        content={'{"title": "Boxes", "values": [2, 7, "x",], "caption": "2 + 7 = 9"}'}
      />,
    );
    expect(view.getByTestId("array-block-text")).toBeTruthy();
    expect(view.getByText("Boxes")).toBeTruthy();
    expect(view.getByText("[2, 7, x]")).toBeTruthy();
    expect(view.getByText("2 + 7 = 9")).toBeTruthy();
  });
});
