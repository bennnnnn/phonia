import { Line, Path, Polygon, Rect, Text as SvgText } from "react-native-svg";

import {
  isRightAngleDeg,
  polygonInteriorAngleMarks,
  type TickSegment,
  type VertexAngleMark,
} from "@/lib/math/geometryBlock";
import { type Theme } from "@/lib/theme";
import { UI_FONT } from "@/lib/uiFont";

export function diagramColors(theme: Theme) {
  return {
    diagonal: theme.danger,
    height: theme.accent,
    hypotenuse: theme.danger,
    median: theme.textSecondary,
  };
}

export function TickMarks({
  segments,
  color,
}: {
  segments: TickSegment[];
  color: string;
}) {
  return (
    <>
      {segments.map((seg, i) => (
        <Line
          key={`tick-${i}-${seg.x1}-${seg.y1}`}
          x1={seg.x1}
          y1={seg.y1}
          x2={seg.x2}
          y2={seg.y2}
          stroke={color}
          strokeWidth={1.5}
          accessible={false}
        />
      ))}
    </>
  );
}

export function InteriorAngleMarks({
  vertices,
  color,
  fill,
  degreeLabels,
}: {
  vertices: { x: number; y: number }[];
  color: string;
  fill: string;
  /** Server-provided degree strings, one per vertex. Missing entries draw the
   * arc or right-angle square without a number. */
  degreeLabels?: readonly (string | undefined)[];
}) {
  const n = vertices.length;
  const marks = polygonInteriorAngleMarks(vertices);
  return (
    <>
      {marks.map((mark, i) => {
        const b = vertices[i];
        const a = vertices[(i + n - 1) % n];
        const c = vertices[(i + 1) % n];
        return (
          <VertexAngleGraphic
            key={`ang-${i}-${mark.text}`}
            mark={mark}
            a={a}
            b={b}
            c={c}
            color={color}
            fill={fill}
            degreeText={degreeLabels?.[i] || undefined}
          />
        );
      })}
    </>
  );
}

function VertexAngleGraphic({
  mark,
  a,
  b,
  c,
  color,
  fill,
  degreeText,
}: {
  mark: VertexAngleMark;
  a: { x: number; y: number };
  b: { x: number; y: number };
  c: { x: number; y: number };
  color: string;
  fill: string;
  degreeText?: string;
}) {
  const right = isRightAngleDeg(mark.deg);
  const size = 14;
  const la = Math.hypot(a.x - b.x, a.y - b.y) || 1;
  const lc = Math.hypot(c.x - b.x, c.y - b.y) || 1;
  const ux = ((a.x - b.x) / la) * size;
  const uy = ((a.y - b.y) / la) * size;
  const vx = ((c.x - b.x) / lc) * size;
  const vy = ((c.y - b.y) / lc) * size;
  return (
    <>
      {right ? (
        <Polygon
          points={`${b.x},${b.y} ${b.x + ux},${b.y + uy} ${b.x + ux + vx},${b.y + uy + vy} ${b.x + vx},${b.y + vy}`}
          fill="none"
          stroke={color}
          strokeWidth={1.5}
          accessible={false}
        />
      ) : (
        <Path
          d={mark.path}
          fill="none"
          stroke={color}
          strokeWidth={1.5}
          accessible={false}
        />
      )}
      {degreeText && mark.leader ? (
        <Line
          x1={mark.leader.x1}
          y1={mark.leader.y1}
          x2={mark.leader.x2}
          y2={mark.leader.y2}
          stroke={color}
          strokeWidth={1}
          accessible={false}
        />
      ) : null}
      {degreeText ? (
        <Rect
          x={mark.labelX - mark.labelWidth / 2}
          y={mark.labelY - mark.labelHeight / 2}
          width={mark.labelWidth}
          height={mark.labelHeight}
          rx={3}
          fill={fill}
          accessible={false}
        />
      ) : null}
      {degreeText ? (
        <SvgText
          x={mark.labelX}
          y={mark.labelY}
          fill={color}
          fontSize={11}
          fontFamily={UI_FONT.semibold}
          textAnchor="middle"
          alignmentBaseline="middle"
          accessible={false}
        >
          {degreeText}
        </SvgText>
      ) : null}
    </>
  );
}
