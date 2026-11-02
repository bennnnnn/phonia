import { render } from "@testing-library/react-native";
import { Dimensions } from "react-native";

import { GeometryBlock } from "@/components/rich/GeometryBlock";

// react-native-svg's <Text>/<TSpan> render as RNSVGText/RNSVGTSpan native
// components, not RN's built-in Text — RTL's getByText only matches the
// latter, so diagram labels are asserted via the serialized render tree.
describe("GeometryBlock", () => {
  it("labels angles-only side lengths as relative and omits an invented area", async () => {
    const content = JSON.stringify({
      type: "triangle_sides",
      a: 1,
      b: 1.7321,
      c: 2,
      relative_lengths: true,
      unit: "units",
      area: 0.866,
      labels: { a: "1 cm", b: "1.7321 cm", c: "2 cm", area: "0.87 cm²" },
    });
    const { toJSON, queryByTestId, getByTestId } = await render(
      <GeometryBlock content={content} />,
    );
    const tree = JSON.stringify(toJSON());
    expect(getByTestId("sss-relative-label")).toBeOnTheScreen();
    expect(queryByTestId("sss-area-label")).toBeNull();
    expect(tree).toContain("Relative side lengths");
    expect(tree).not.toContain("cm");
    expect(tree).not.toContain("units²");
  });

  it("renders a rectangle diagram with computed width/height labels", async () => {
    const content = JSON.stringify({
      type: "rectangle",
      width: 6,
      height: 4,
      unit: "cm",
    });
    const { toJSON } = await render(<GeometryBlock content={content} />);
    const tree = JSON.stringify(toJSON());

    expect(tree).toContain("6 cm");
    expect(tree).toContain("4 cm");
  });

  it("renders a circle diagram with a radius label", async () => {
    const content = JSON.stringify({ type: "circle", radius: 5, unit: "cm" });
    const { toJSON } = await render(<GeometryBlock content={content} />);

    expect(JSON.stringify(toJSON())).toContain("5 cm");
  });

  it("renders the fallback message for unparseable content", async () => {
    const { getByText } = await render(<GeometryBlock content="not json" />);
    expect(getByText("Could not render geometry diagram.")).toBeOnTheScreen();
  });

  it("renders a triangle-by-sides (SSS) diagram with side labels", async () => {
    const content = JSON.stringify({
      type: "triangle_sides",
      a: 3,
      b: 4,
      c: 5,
      unit: "cm",
    });
    const { toJSON } = await render(<GeometryBlock content={content} />);
    const tree = JSON.stringify(toJSON());

    expect(tree).toContain("3 cm");
    expect(tree).toContain("4 cm");
    expect(tree).toContain("5 cm");
    expect(tree).not.toContain("90°");
    expect(tree).not.toContain("36.9°");
    expect(tree).not.toContain("53.1°");
  });

  it.each([false, true])(
    "keeps an obtuse 3,5,3 triangle inside the chart with angle labels=%s",
    async (showAngle) => {
      const content = JSON.stringify({
        type: "triangle_sides",
        a: 3,
        b: 5,
        c: 3,
        unit: "cm",
        show_angle: showAngle,
        show_altitude: false,
        show_median: false,
      });
      const { toJSON, getByTestId } = await render(
        <GeometryBlock content={content} />,
      );
      const svg = getByTestId("sss-svg");
      const width = Number(svg.props.width);
      const height = Number(svg.props.height);
      const path = JSON.stringify(toJSON()).match(/"d":"M([^\"]+)z"/);
      expect(path).not.toBeNull();
      const coordinates = path![1].trim().split(/[ ,]+/).map(Number);
      for (let i = 0; i < coordinates.length; i += 2) {
        expect(coordinates[i]).toBeGreaterThanOrEqual(0);
        expect(coordinates[i]).toBeLessThanOrEqual(width);
        expect(coordinates[i + 1]).toBeGreaterThanOrEqual(0);
        expect(coordinates[i + 1]).toBeLessThanOrEqual(height);
      }
      expect(width).toBeLessThanOrEqual(Dimensions.get("window").width - 28);
    },
  );

  it("falls back for an impossible triangle (sides that can't close)", async () => {
    const content = JSON.stringify({
      type: "triangle_sides",
      a: 1,
      b: 1,
      c: 10,
      unit: "cm",
    });
    const { getByText } = await render(<GeometryBlock content={content} />);
    expect(getByText("Could not render geometry diagram.")).toBeOnTheScreen();
  });

  it("renders a trapezoid diagram with top/bottom/height labels", async () => {
    const content = JSON.stringify({
      type: "trapezoid",
      top: 4,
      bottom: 8,
      height: 5,
      unit: "cm",
    });
    const { toJSON } = await render(<GeometryBlock content={content} />);
    const tree = JSON.stringify(toJSON());

    expect(tree).toContain("4 cm");
    expect(tree).toContain("8 cm");
    expect(tree).toContain("5 cm");
  });

  it("renders a parallelogram diagram with base/height/side labels", async () => {
    const content = JSON.stringify({
      type: "parallelogram",
      base: 8,
      height: 4,
      side: 5,
      unit: "cm",
    });
    const { toJSON } = await render(<GeometryBlock content={content} />);
    const tree = JSON.stringify(toJSON());

    expect(tree).toContain("8 cm");
    expect(tree).toContain("4 cm");
    expect(tree).toContain("5 cm");
  });

  it("falls back when the parallelogram's side is shorter than its height", async () => {
    const content = JSON.stringify({
      type: "parallelogram",
      base: 8,
      height: 10,
      side: 3,
      unit: "cm",
    });
    const { getByText } = await render(<GeometryBlock content={content} />);
    expect(getByText("Could not render geometry diagram.")).toBeOnTheScreen();
  });

  it("renders a circle sector diagram with an angle label", async () => {
    const content = JSON.stringify({
      type: "sector",
      radius: 5,
      angle_deg: 90,
      unit: "cm",
    });
    const { toJSON } = await render(<GeometryBlock content={content} />);

    expect(JSON.stringify(toJSON())).toContain("90");
  });

  it("shows only known measurements for a base-and-height triangle", async () => {
    const content = JSON.stringify({
      type: "triangle",
      base: 3,
      height: 4,
      unit: "cm",
      show_ticks: true,
      show_angle: true,
      show_altitude: true,
    });
    const { toJSON } = await render(<GeometryBlock content={content} />);
    const tree = JSON.stringify(toJSON());
    expect(tree).toContain("3 cm");
    expect(tree).toContain("4 cm");
    expect(tree).not.toContain("cm²");
    expect(tree).not.toContain("°");
    // Polygon renders as a native Path; no extra interior-angle arcs.
    expect((tree.match(/"RNSVGPath"/g) ?? []).length).toBe(1);
    // The single known perpendicular height remains; no congruence ticks.
    expect((tree.match(/"RNSVGLine"/g) ?? []).length).toBe(1);
  });

  it("draws a right-angle mark and 90° label on a right triangle", async () => {
    const content = JSON.stringify({
      type: "right_triangle",
      base: 3,
      height: 4,
      unit: "cm",
      show_angle: true,
    });
    const { toJSON } = await render(<GeometryBlock content={content} />);
    const tree = JSON.stringify(toJSON());
    expect(tree).toContain("90°");
    expect(tree).not.toContain("36.9°");
    expect(tree).not.toContain("53.1°");
    expect(tree).toContain("3 cm");
    expect(tree).toContain("4 cm");
    expect(tree).toContain("RNSVGRect");
    expect(tree).not.toContain("right-angle-mark");
  });

  it("prints acute angles only from server labels", async () => {
    const content = JSON.stringify({
      type: "right_triangle",
      base: 3,
      height: 4,
      unit: "cm",
      show_angle: true,
      labels: { angle_at_base: "53.1°", angle_at_height: "36.9°" },
    });
    const tree = JSON.stringify((await render(<GeometryBlock content={content} />)).toJSON());
    expect(tree).toContain("90°");
    expect(tree).toContain("53.1°");
    expect(tree).toContain("36.9°");
  });

  it("draws leader lines when a skinny right triangle cannot fit 10° inside", async () => {
    const content = JSON.stringify({
      type: "right_triangle",
      base: 2,
      height: 34,
      unit: "cm",
      show_angle: true,
    });
    const { toJSON } = await render(<GeometryBlock content={content} />);
    const tree = JSON.stringify(toJSON());
    expect(tree).toContain("90°");
    expect(tree).toContain("RNSVGLine");
    expect(tree).not.toContain("interior-angle-leader");
  });

  it("draws a diagonal-angle arc when rectangle show_angle + show_diagonal", async () => {
    const content = JSON.stringify({
      type: "rectangle",
      width: 8,
      height: 5,
      unit: "cm",
      show_diagonal: true,
      show_angle: true,
      diagonal: 9.43,
      angle_deg: 32.01,
    });
    const { toJSON } = await render(<GeometryBlock content={content} />);
    const tree = JSON.stringify(toJSON());
    expect(tree).toContain("∠");
    expect(tree).toContain("RNSVGPath");
    expect(tree).not.toContain("90°");
  });

  it("draws side tick marks on a square by default", async () => {
    const content = JSON.stringify({ type: "square", side: 5, unit: "cm" });
    const { toJSON } = await render(<GeometryBlock content={content} />);
    expect(JSON.stringify(toJSON())).toContain("RNSVGLine");
  });

  it("labels every square side and marks all four right angles uniformly", async () => {
    const content = JSON.stringify({ type: "square", side: 5, unit: "cm" });
    const { toJSON, getByTestId } = await render(
      <GeometryBlock content={content} />,
    );
    const tree = JSON.stringify(toJSON());
    expect((tree.match(/5 cm/g) ?? []).length).toBeGreaterThanOrEqual(4);
    for (const corner of [
      "top-left",
      "top-right",
      "bottom-right",
      "bottom-left",
    ]) {
      expect(getByTestId(`rectangle-right-angle-${corner}`)).toBeOnTheScreen();
    }
  });

  it("labels both pairs of known rectangle sides", async () => {
    const content = JSON.stringify({
      type: "rectangle",
      width: 4,
      height: 5,
      unit: "cm",
    });
    const { toJSON, getByLabelText } = await render(<GeometryBlock content={content} />);
    const tree = JSON.stringify(toJSON());
    const drawn = tree.replace(/"accessibilityLabel":"[^"]*"/, "");
    expect((drawn.match(/4 cm/g) ?? []).length).toBe(2);
    expect((drawn.match(/5 cm/g) ?? []).length).toBe(2);
    expect(getByLabelText("4 cm, 5 cm")).toBeOnTheScreen();
  });

  it("draws a requested diameter across the full circle", async () => {
    const content = JSON.stringify({
      type: "circle",
      radius: 3,
      unit: "cm",
      show_diameter: true,
      diameter: 6,
    });
    const { toJSON } = await render(<GeometryBlock content={content} />);
    const tree = JSON.stringify(toJSON());
    expect(tree).toContain("6 cm");
    expect(tree).not.toContain("3 cm");
  });

  it("does not draw altitude on an SSS triangle unless asked", async () => {
    const content = JSON.stringify({
      type: "triangle_sides",
      a: 5,
      b: 9.4,
      c: 12.66,
      unit: "cm",
      show_angle: true,
    });
    const { toJSON } = await render(<GeometryBlock content={content} />);
    expect(JSON.stringify(toJSON())).not.toContain(
      '"strokeDasharray":["5","4"]',
    );
  });

  it("draws altitude and equal-side ticks on an isosceles SSS triangle", async () => {
    const content = JSON.stringify({
      type: "triangle_sides",
      a: 6,
      b: 5,
      c: 5,
      unit: "cm",
      show_altitude: true,
      show_ticks: true,
      show_median: true,
    });
    const { toJSON } = await render(<GeometryBlock content={content} />);
    const tree = JSON.stringify(toJSON());
    expect(tree).toContain('"strokeDasharray":["5","4"]');
    expect(tree).toContain("RNSVGLine");
  });

  it("draws a separate median when scalene and show_median is set", async () => {
    const content = JSON.stringify({
      type: "triangle_sides",
      a: 3,
      b: 4,
      c: 5,
      unit: "cm",
      show_altitude: true,
      show_median: true,
      show_ticks: false,
    });
    const { toJSON } = await render(<GeometryBlock content={content} />);
    const tree = JSON.stringify(toJSON());
    expect(tree).toContain('"strokeDasharray":["5","4"]');
    expect(tree).toContain('"strokeDasharray":["2","3"]');
  });

  it("hides labels when show_labels is false", async () => {
    const content = JSON.stringify({
      type: "triangle",
      base: 8,
      height: 5,
      unit: "cm",
      show_labels: false,
    });
    const { toJSON } = await render(<GeometryBlock content={content} />);
    const tree = JSON.stringify(toJSON());
    expect(tree).not.toContain("8 cm");
    expect(tree).not.toContain("5 cm");
  });

  it("BUG FIX regression: SSS area label sits inside the SVG height", async () => {
    const content = JSON.stringify({
      type: "triangle_sides",
      a: 3,
      b: 4,
      c: 5,
      unit: "cm",
      area: 6,
    });
    const { getByTestId } = await render(<GeometryBlock content={content} />);
    const svg = getByTestId("sss-svg");
    const label = getByTestId("sss-area-label");
    expect(Number(label.props.y)).toBeLessThan(Number(svg.props.height));
  });

  it("reads server measurements as the diagram accessibility label", async () => {
    const solved = JSON.stringify({
      type: "circle",
      radius: 5,
      unit: "cm",
      area: 78.54,
    });
    const { getByLabelText } = await render(<GeometryBlock content={solved} />);
    expect(getByLabelText("5 cm, 78.54 cm²")).toBeOnTheScreen();

    const given = JSON.stringify({ type: "rectangle", width: 6, height: 4, unit: "cm" });
    const bare = await render(<GeometryBlock content={given} />);
    expect(bare.getByLabelText("6 cm, 4 cm")).toBeOnTheScreen();
    expect(bare.queryByLabelText(/cm²/)).toBeNull();
  });
});
