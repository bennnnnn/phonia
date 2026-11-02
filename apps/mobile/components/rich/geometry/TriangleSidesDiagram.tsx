import Svg, { Line, Polygon, Text as SvgText } from "react-native-svg";

import {
  InteriorAngleMarks,
  TickMarks,
  diagramColors,
} from "@/components/rich/geometry/GeometryMarks";
import {
  computeTriangleSidesLabels,
  equalSideTickCounts,
  footOfPerpendicular,
  geometryLabelInset,
  isIsoscelesSides,
  midpoint,
  padDiagramForAngleLabels,
  shouldShowTicks,
  sideTickMarks,
  triangleSidesVertices,
  type TriangleSidesSpec,
} from "@/lib/math/geometryBlock";
import i18n from "@/lib/i18n";
import { type Theme } from "@/lib/theme";
import { UI_FONT } from "@/lib/uiFont";

export function TriangleSidesDiagram({
  spec,
  screenWidth,
  theme,
}: {
  spec: TriangleSidesSpec;
  screenWidth: number;
  theme: Theme;
}) {
  const colors = diagramColors(theme);
  const labels = computeTriangleSidesLabels(spec);
  const raw = triangleSidesVertices(spec.a, spec.b, spec.c);
  const minX = Math.min(raw.x0, raw.x1, raw.x2);
  const maxX = Math.max(raw.x0, raw.x1, raw.x2);
  const spanX = maxX - minX;
  const maxY = Math.max(raw.y0, raw.y1, raw.y2, 1);
  const offsetX = spec.show_labels !== false ? geometryLabelInset(labels.c) : 40;
  const rightPad = spec.show_labels !== false ? geometryLabelInset(labels.b) : 40;
  const inner = Math.max(screenWidth - 48 - offsetX - rightPad, 1);
  const scale = inner / Math.max(spanX, maxY, 1);
  const offsetY = 28;
  // SVG y grows downward \u2014 flip so the apex draws above the base.
  const toSvg = (x: number, y: number) => ({
    x: offsetX + (x - minX) * scale,
    y: offsetY + (maxY - y) * scale,
  });
  const p0raw = toSvg(raw.x0, raw.y0);
  const p1raw = toSvg(raw.x1, raw.y1);
  const p2raw = toSvg(raw.x2, raw.y2);
  const showLabels = spec.show_labels !== false;
  const svgW0 = spanX * scale + offsetX + rightPad;
  const labelBelow = showLabels ? 52 : 16;
  const svgH0 = maxY * scale + offsetY + labelBelow;
  const tickCounts = equalSideTickCounts(spec.a, spec.b, spec.c);
  const hasEqualSides = tickCounts.a > 0 || tickCounts.b > 0 || tickCounts.c > 0;
  const showTicks = shouldShowTicks(spec.show_ticks, hasEqualSides);
  const showAltitude = spec.show_altitude === true;
  const showAngle = spec.show_angle !== false;
  let verts = [p0raw, p1raw, p2raw];
  let svgW = svgW0;
  let svgH = svgH0;
  if (showAngle) {
    const padded = padDiagramForAngleLabels(verts, svgW, svgH);
    verts = padded.vertices;
    svgW = padded.svgW;
    svgH = padded.svgH;
  }
  const [p0, p1, p2] = verts;
  const showMedian =
    spec.show_median === true || (spec.show_median !== false && isIsoscelesSides(spec.a, spec.b, spec.c));
  const foot = footOfPerpendicular(p0.x, p0.y, p1.x, p1.y, p2.x, p2.y);
  const mid = midpoint(p0.x, p0.y, p1.x, p1.y);
  // When altitude and median coincide (isosceles with base a), draw one line.
  const altitudeIsMedian =
    Math.hypot(foot.x - mid.x, foot.y - mid.y) < 1.5;
  const tickSegments = showTicks
    ? [
        ...sideTickMarks(p0.x, p0.y, p1.x, p1.y, tickCounts.a),
        ...sideTickMarks(p1.x, p1.y, p2.x, p2.y, tickCounts.b),
        ...sideTickMarks(p2.x, p2.y, p0.x, p0.y, tickCounts.c),
      ]
    : [];

  return (
    <Svg width={svgW} height={svgH} testID="sss-svg">
      <Polygon
        points={`${p0.x},${p0.y} ${p1.x},${p1.y} ${p2.x},${p2.y}`}
        fill={theme.contentSurface}
        stroke={theme.primary}
        strokeWidth={2}
      />
      {showAltitude ? (
        <Line
          x1={p2.x}
          y1={p2.y}
          x2={foot.x}
          y2={foot.y}
          stroke={colors.height}
          strokeWidth={2}
          strokeDasharray="5,4"
          accessible={false}
        />
      ) : null}
      {showMedian && !altitudeIsMedian ? (
        <Line
          x1={p2.x}
          y1={p2.y}
          x2={mid.x}
          y2={mid.y}
          stroke={colors.median}
          strokeWidth={1.5}
          strokeDasharray="2,3"
          accessible={false}
        />
      ) : null}
      {showMedian && altitudeIsMedian && !showAltitude ? (
        <Line
          x1={p2.x}
          y1={p2.y}
          x2={mid.x}
          y2={mid.y}
          stroke={colors.median}
          strokeWidth={1.5}
          strokeDasharray="2,3"
          accessible={false}
        />
      ) : null}
      {tickSegments.length > 0 ? <TickMarks segments={tickSegments} color={theme.textSecondary} /> : null}
      {showAngle ? (
        <InteriorAngleMarks
          vertices={[p0, p1, p2]}
          color={theme.textSecondary}
          fill={theme.contentSurface}
          degreeLabels={[labels.angle_b, labels.angle_c, labels.angle_a]}
        />
      ) : null}
      {showLabels ? (
        <>
          <SvgText x={(p0.x + p1.x) / 2} y={p0.y + 18} fill={theme.text} fontSize={13} fontFamily={UI_FONT.semibold} textAnchor="middle">
            {labels.a}
          </SvgText>
          <SvgText x={(p1.x + p2.x) / 2 + 8} y={(p1.y + p2.y) / 2} fill={theme.text} fontSize={13} fontFamily={UI_FONT.semibold}>
            {labels.b}
          </SvgText>
          <SvgText x={(p2.x + p0.x) / 2 - 8} y={(p2.y + p0.y) / 2} fill={theme.text} fontSize={13} fontFamily={UI_FONT.semibold} textAnchor="end">
            {labels.c}
          </SvgText>
          {spec.relative_lengths || labels.area ? (
            <SvgText
              x={(p0.x + p1.x + p2.x) / 3}
              y={Math.max(p0.y, p1.y) + 34}
              fill={theme.textSecondary}
              fontSize={12}
              fontFamily={UI_FONT.regular}
              textAnchor="middle"
              testID={spec.relative_lengths ? "sss-relative-label" : "sss-area-label"}
            >
              {spec.relative_lengths
                ? i18n.t("rich.relative_side_lengths")
                : `${i18n.t("rich.area")}\u00A0${labels.area}`}
            </SvgText>
          ) : null}
        </>
      ) : null}
    </Svg>
  );
}
