import Svg, { Polygon, Text as SvgText } from "react-native-svg";

import { InteriorAngleMarks, diagramColors } from "@/components/rich/geometry/GeometryMarks";
import {
  computeRightTriangleLabels,
  geometryLabelInset,
  padDiagramForAngleLabels,
  scaleToFit,
  type RightTriangleSpec,
} from "@/lib/math/geometryBlock";
import { type Theme } from "@/lib/theme";
import { UI_FONT } from "@/lib/uiFont";

export function RightTriangleDiagram({
  spec,
  screenWidth,
  theme,
}: {
  spec: RightTriangleSpec;
  screenWidth: number;
  theme: Theme;
}) {
  const colors = diagramColors(theme);
  const labels = computeRightTriangleLabels(spec);
  const offsetX = spec.show_labels !== false ? geometryLabelInset(labels.height, 12, 10, 48) : 48;
  const rightPad = spec.show_labels !== false && spec.show_hypotenuse !== false
    ? geometryLabelInset(labels.hypotenuse, 12, 8, 48) : 48;
  const layout = scaleToFit(spec.base, spec.height, screenWidth - 48, offsetX + rightPad);
  const offsetY = 28;
  const b = layout.w;
  const h = layout.h;
  const x0 = offsetX;
  const y0 = offsetY;
  const x1 = offsetX + b;
  const y1 = offsetY + h;
  const svgW = b + offsetX + rightPad;
  // Side-length labels sit below the base (y+18) and left of the height —
  // angle-label padding does not include them, so "6 cm" used to clip.
  const svgH = h + offsetY + 56;
  const showLabels = spec.show_labels !== false;
  const showHyp = spec.show_hypotenuse !== false;
  const showAngle = spec.show_angle !== false;
  let verts = [
    { x: x0, y: y1 },
    { x: x1, y: y1 },
    { x: x0, y: y0 },
  ];
  let outW = svgW;
  let outH = svgH;
  if (showAngle) {
    const padded = padDiagramForAngleLabels(verts, svgW, svgH);
    verts = padded.vertices;
    outW = padded.svgW;
    outH = padded.svgH;
  }
  if (showLabels) {
    const baseLabelBottom = Math.max(verts[0].y, verts[1].y) + 18 + 16;
    if (baseLabelBottom > outH) outH = baseLabelBottom;
  }

  return (
    <Svg width={outW} height={outH}>
      <Polygon
        points={`${verts[0].x},${verts[0].y} ${verts[1].x},${verts[1].y} ${verts[2].x},${verts[2].y}`}
        fill={theme.contentSurface}
        stroke={theme.primary}
        strokeWidth={2}
      />
      {showAngle ? (
        <InteriorAngleMarks
          vertices={verts}
          color={theme.textSecondary}
          fill={theme.contentSurface}
          degreeLabels={[labels.angle, labels.angle_at_base, labels.angle_at_height]}
        />
      ) : null}
      {showLabels ? (
        <>
          <SvgText
            x={(verts[0].x + verts[1].x) / 2}
            y={verts[0].y + 18}
            fill={theme.text}
            fontSize={13}
            fontFamily={UI_FONT.semibold}
            textAnchor="middle"
          >
            {labels.base}
          </SvgText>
          <SvgText
            x={verts[0].x - 10}
            y={(verts[2].y + verts[0].y) / 2}
            fill={colors.height}
            fontSize={12}
            fontFamily={UI_FONT.semibold}
            textAnchor="end"
          >
            {labels.height}
          </SvgText>
          {showHyp && labels.hypotenuse ? (
            <SvgText
              x={(verts[0].x + verts[1].x) / 2 + 8}
              y={(verts[2].y + verts[0].y) / 2 - 6}
              fill={colors.hypotenuse}
              fontSize={12}
              fontFamily={UI_FONT.semibold}
            >
              {labels.hypotenuse}
            </SvgText>
          ) : null}
        </>
      ) : null}
    </Svg>
  );
}
