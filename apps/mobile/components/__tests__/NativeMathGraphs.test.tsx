import { fireEvent, render } from "@testing-library/react-native";

import { FunctionGraphBlock } from "@/components/rich/FunctionGraphBlock";

jest.mock("@/lib/skiaAvailability", () => ({ isSkiaAvailable: () => true }));

describe("native math graphs", () => {
  it("uses Skia for the inline function card", async () => {
    const content = JSON.stringify({
      type: "function",
      expr: "x**2",
      points: [
        [-2, 4],
        [0, 0],
        [2, 4],
      ],
    });
    const { getByTestId } = await render(<FunctionGraphBlock content={content} />);

    expect(getByTestId("skia-graph-card")).toBeOnTheScreen();
  });

  it("lets the expanded Skia canvas receive pinch and pan touches", async () => {
    const content = JSON.stringify({
      type: "function",
      expr: "x**2",
      points: [
        [-2, 4],
        [0, 0],
        [2, 4],
      ],
    });
    const { getByTestId } = await render(<FunctionGraphBlock content={content} />);

    await fireEvent.press(getByTestId("graph-expand"));

    expect(getByTestId("graph-interaction-surface").props.pointerEvents).toBe("box-only");
    expect(getByTestId("skia-graph-canvas")).toBeOnTheScreen();
  });

  it("uses Skia for a number-line solution", async () => {
    const content = JSON.stringify({
      type: "number_line",
      expr: "x > 3",
      title: "x > 3",
      intervals: [{ start: 3, end: null, start_inclusive: false, end_inclusive: false }],
    });
    const { getByTestId } = await render(<FunctionGraphBlock content={content} />);

    expect(getByTestId("skia-number-line-canvas")).toBeOnTheScreen();
  });

  it("uses Skia for a two-dimensional inequality", async () => {
    const content = JSON.stringify({
      type: "inequality",
      expr: "x + y <= 2",
      title: "x + y <= 2",
      comparator: "<=",
      a: 1,
      b: 1,
      c: 2,
      x_min: -5,
      x_max: 5,
      y_min: -5,
      y_max: 5,
      points: [],
    });
    const { getByTestId } = await render(<FunctionGraphBlock content={content} />);

    expect(getByTestId("skia-inequality-canvas")).toBeOnTheScreen();
  });
});
