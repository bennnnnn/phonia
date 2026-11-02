import type { ReactNode } from "react";
import Svg, { Line, Polygon, Text as SvgText } from "react-native-svg";

import { InteriorAngleMarks } from "@/components/rich/geometry/GeometryMarks";
import { padDiagramForAngleLabels } from "@/lib/math/geometryBlock";
import type { Theme } from "@/lib/theme";
import { UI_FONT } from "@/lib/uiFont";

type Vertex = { x: number; y: number };

export function prepareQuadrilateralFrame(
  vertices: Vertex[],
  width: number,
  height: number,
  showAngle: boolean,
): { vertices: Vertex[]; width: number; height: number } {
  if (!showAngle) return { vertices, width, height };
  const padded = padDiagramForAngleLabels(vertices, width, height);
  return {
    vertices: padded.vertices,
    width: padded.svgW,
    height: padded.svgH,
  };
}

export function QuadrilateralDimensionLabels({
  vertices,
  top,
  bottom,
  height,
  theme,
}: {
  vertices: Vertex[];
  top: string;
  bottom: string;
  height: string;
  theme: Theme;
}) {
  const [topLeft, topRight, bottomRight, bottomLeft] = vertices;
  return (
    <>
      <SvgText
        x={(topLeft.x + topRight.x) / 2}
        y={topLeft.y - 8}
        fill={theme.text}
        fontSize={13}
        fontFamily={UI_FONT.semibold}
        textAnchor="middle"
      >
        {top}
      </SvgText>
      <SvgText
        x={(bottomLeft.x + bottomRight.x) / 2}
        y={bottomLeft.y + 18}
        fill={theme.text}
        fontSize={13}
        fontFamily={UI_FONT.semibold}
        textAnchor="middle"
      >
        {bottom}
      </SvgText>
      <SvgText
        x={topLeft.x - 8}
        y={(topLeft.y + bottomLeft.y) / 2}
        fill={theme.accent}
        fontSize={12}
        fontFamily={UI_FONT.semibold}
        textAnchor="end"
      >
        {height}
      </SvgText>
    </>
  );
}

/** Shared polygon, height guide, and angle marks for four-sided diagrams. */
export function QuadrilateralFrame({
  vertices,
  width,
  height,
  theme,
  showAngle,
  children,
}: {
  vertices: Vertex[];
  width: number;
  height: number;
  theme: Theme;
  showAngle: boolean;
  children?: ReactNode;
}) {
  const [topLeft, topRight, bottomRight, bottomLeft] = vertices;
  return (
    <Svg width={width} height={height}>
      <Polygon
        points={`${topLeft.x},${topLeft.y} ${topRight.x},${topRight.y} ${bottomRight.x},${bottomRight.y} ${bottomLeft.x},${bottomLeft.y}`}
        fill={theme.contentSurface}
        stroke={theme.primary}
        strokeWidth={2}
      />
      <Line
        x1={topLeft.x}
        y1={topLeft.y}
        x2={topLeft.x}
        y2={bottomLeft.y}
        stroke={theme.accent}
        strokeWidth={2}
        strokeDasharray="5,4"
      />
      {showAngle ? (
        <InteriorAngleMarks
          vertices={vertices}
          color={theme.textSecondary}
          fill={theme.contentSurface}
        />
      ) : null}
      {children}
    </Svg>
  );
}
