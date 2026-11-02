import Svg, { Line, Polygon, Text as SvgText } from "react-native-svg";

import { diagramColors } from "@/components/rich/geometry/GeometryMarks";
import {
  baseHeightTriangleVertices,
  computeTriangleLabels,
  geometryLabelInset,
  scaleToFit,
  type TriangleSpec,
} from "@/lib/math/geometryBlock";
import { type Theme } from "@/lib/theme";
import { UI_FONT } from "@/lib/uiFont";

export function TriangleDiagram({ spec, screenWidth, theme }: { spec: TriangleSpec; screenWidth: number; theme: Theme }) {
  const colors = diagramColors(theme);
  const labels = computeTriangleLabels(spec);
  const offsetX = 48;
  const rightPad = spec.show_labels !== false ? geometryLabelInset(labels.height, 12, 10, 48) : 48;
  const layout = scaleToFit(spec.base, spec.height, screenWidth - 48, offsetX + rightPad);
  const offsetY = 28;
  const b = layout.w;
  const h = layout.h;
  const raw = baseHeightTriangleVertices(b, h);
  const x0 = offsetX + raw.x0;
  const y0 = offsetY + raw.y0;
  const x1 = offsetX + raw.x1;
  const y1 = offsetY + raw.y1;
  const x2 = offsetX + raw.x2;
  const y2 = offsetY + raw.y2;
  const svgW = b + offsetX + rightPad;
  const svgH = h + offsetY + 36;
  const showLabels = spec.show_labels !== false;
  const showAltitude = spec.show_altitude !== false;
  const verts = [
    { x: x0, y: y0 },
    { x: x1, y: y1 },
    { x: x2, y: y2 },
  ];
  // Base and height do not determine side equality or interior angles.

  return (
    <Svg width={svgW} height={svgH}>
      <Polygon
        points={`${verts[0].x},${verts[0].y} ${verts[1].x},${verts[1].y} ${verts[2].x},${verts[2].y}`}
        fill={theme.contentSurface}
        stroke={theme.primary}
        strokeWidth={2}
        accessible={false}
      />
      {showAltitude ? (
        <Line
          x1={verts[2].x}
          y1={verts[2].y}
          x2={verts[2].x}
          y2={verts[0].y}
          stroke={colors.height}
          strokeWidth={2}
          strokeDasharray="5,4"
          accessible={false}
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
            x={verts[2].x + 10}
            y={(verts[2].y + verts[0].y) / 2}
            fill={colors.height}
            fontSize={12}
            fontFamily={UI_FONT.semibold}
          >
            {labels.height}
          </SvgText>
          {labels.area ? (
            <SvgText x={verts[2].x} y={verts[2].y - 8} fill={theme.textSecondary} fontSize={11} fontFamily={UI_FONT.regular} textAnchor="middle">
              {labels.area}
            </SvgText>
          ) : null}
        </>
      ) : null}
    </Svg>
  );
}
