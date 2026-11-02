import { render } from "@testing-library/react-native";

import { FunctionGraphBlock } from "@/components/rich/FunctionGraphBlock";

jest.mock("@/lib/skiaAvailability", () => ({ isSkiaAvailable: () => false }));

const base = {
  type: "inequality", expr: "y < 2*x", a: -2, b: 1, c: 0, comparator: "<",
  x_min: -10, x_max: 10, y_min: -10, y_max: 10, points: [],
};

describe("InequalityGraphChart", () => {
  it.each(["<", ">"])("renders a shaded region and dashed boundary for %s", async (comparator) => {
    const { getByTestId, getByText, getByLabelText } = await render(
      <FunctionGraphBlock content={JSON.stringify({ ...base, comparator, expr: `y ${comparator} 2*x` })} />,
    );
    expect(getByText(`y ${comparator} 2x`)).toBeOnTheScreen();
    expect(getByTestId("inequality-region").props.fillOpacity).toBe(0.16);
    expect(getByTestId("inequality-boundary").props.strokeDasharray).toEqual([6, 5]);
    expect(getByText("rich.graph_boundary_excluded")).toBeOnTheScreen();
    expect(getByLabelText(`y ${comparator} 2x. rich.graph_solution_region. rich.graph_boundary_excluded.`)).toBeOnTheScreen();
  });

  it.each(["<=", ">="])("renders a solid boundary for %s", async (comparator) => {
    const { getByTestId, getByText } = await render(
      <FunctionGraphBlock content={JSON.stringify({ ...base, comparator, expr: `y ${comparator} 2*x` })} />,
    );
    expect(getByText(comparator === "<=" ? "y ≤ 2x" : "y ≥ 2x")).toBeOnTheScreen();
    expect(getByTestId("inequality-boundary").props.strokeDasharray).toBeUndefined();
    expect(getByText("rich.graph_boundary_included")).toBeOnTheScreen();
  });

  it("renders an explicitly verified vertical half-plane as 2D shading", async () => {
    const { getByTestId } = await render(
      <FunctionGraphBlock content={JSON.stringify({ ...base, expr: "x + 0*y < 2", a: 1, b: 0, c: 2 })} />,
    );
    expect(getByTestId("inequality-region")).toBeOnTheScreen();
    expect(getByTestId("inequality-boundary")).toBeOnTheScreen();
  });

  it("does not invent a visible boundary when the entire viewport satisfies the inequality", async () => {
    const { getByTestId, queryByTestId } = await render(
      <FunctionGraphBlock content={JSON.stringify({ ...base, a: 0, b: 1, c: 20 })} />,
    );
    expect(getByTestId("inequality-region")).toBeOnTheScreen();
    expect(queryByTestId("inequality-boundary")).toBeNull();
  });

  it("retains the mathematical relation in accessibility text even with a custom title", async () => {
    const { getByText, getByLabelText } = await render(
      <FunctionGraphBlock content={JSON.stringify({ ...base, title: "Solutions" })} />,
    );
    expect(getByText("Solutions")).toBeOnTheScreen();
    expect(getByLabelText(/y < 2x/)).toBeOnTheScreen();
  });

  it("marks an included corner when the half-plane only touches the viewport there", async () => {
    const { getByTestId, queryByTestId } = await render(
      <FunctionGraphBlock content={JSON.stringify({ ...base, expr: "y >= -x + 20", a: 1, b: 1, c: 20, comparator: ">=" })} />,
    );
    expect(getByTestId("inequality-boundary-point")).toBeOnTheScreen();
    expect(queryByTestId("inequality-region")).toBeNull();
  });

  it("does not mark an excluded corner for the strict version of the relation", async () => {
    const { queryByTestId } = await render(
      <FunctionGraphBlock content={JSON.stringify({ ...base, expr: "y > -x + 20", a: 1, b: 1, c: 20, comparator: ">" })} />,
    );
    expect(queryByTestId("inequality-boundary-point")).toBeNull();
    expect(queryByTestId("inequality-region")).toBeNull();
  });

  it("rejects a malformed affine graph through the existing error view", async () => {
    const { getByText, queryByTestId } = await render(
      <FunctionGraphBlock content={JSON.stringify({ ...base, a: 0, b: 0 })} />,
    );
    expect(getByText("rich.graph_error")).toBeOnTheScreen();
    expect(queryByTestId("inequality-graph")).toBeNull();
  });

  it.each([
    { x_min: -0.1, x_max: 0.1, labels: ["-0.1", "-0.05", "0.05", "0.1"] },
    { x_min: 2.1, x_max: 2.4, labels: ["2.1", "2.15", "2.2", "2.25", "2.3", "2.35", "2.4"] },
  ])("labels an explicit fractional x viewport accurately: $x_min to $x_max", async ({ labels, ...bounds }) => {
    const { toJSON } = await render(
      <FunctionGraphBlock content={JSON.stringify({ ...base, ...bounds })} />,
    );
    const nativeTree = JSON.stringify(toJSON());
    for (const label of labels) expect(nativeTree).toContain(`"content":"${label}"`);
  });
});
