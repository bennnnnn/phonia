import Svg, {
  Line,
  Path,
  Polygon,
  Rect,
  Text as SvgText,
} from "react-native-svg";

import {
  TickMarks,
  diagramColors,
} from "@/components/rich/geometry/GeometryMarks";
import {
  computeRectangleLabels,
  diagonalAngleArcPath,
  geometryLabelInset,
  rectangleAngleDisplay,
  scaleToFit,
  shouldShowTicks,
  sideTickMarks,
  type RectangleSpec,
} from "@/lib/math/geometryBlock";
import i18n from "@/lib/i18n";
import { type Theme } from "@/lib/theme";
import { UI_FONT } from "@/lib/uiFont";

export function RectangleDiagram({
  spec,
  screenWidth,
  theme,
}: {
  spec: RectangleSpec;
  screenWidth: number;
  theme: Theme;
}) {
  const colors = diagramColors(theme);
  const labels = computeRectangleLabels(spec);
  const verticalLabel = spec.type === "square" ? labels.side : labels.height;
  const offsetX = geometryLabelInset(verticalLabel);
  const rightPad = Math.max(
    geometryLabelInset(verticalLabel),
    spec.show_diagonal ? geometryLabelInset(labels.diagonal, 12) : 40,
  );
  const layout = scaleToFit(
    spec.width,
    spec.height,
    screenWidth - 48,
    offsetX + rightPad,
  );
  const offsetY = 36;
  const x = offsetX;
  const y = offsetY;
  const w = layout.w;
  const h = layout.h;
  const svgW = w + offsetX + rightPad;
  const svgH = h + offsetY + (spec.show_area || spec.show_perimeter ? 72 : 42);
  const isSquare = spec.type === "square";
  const corner = 12;
  const { showCornerBracket, showDiagonalAngleLabel } =
    rectangleAngleDisplay(spec);
  const showTicks = shouldShowTicks(spec.show_ticks, true);
  // Square: one tick on every side. Rectangle: 1 on the length pair, 2 on the width pair.
  const tickSegments = showTicks
    ? [
        ...sideTickMarks(x, y, x + w, y, 1),
        ...sideTickMarks(x, y + h, x + w, y + h, 1),
        ...sideTickMarks(x, y, x, y + h, isSquare ? 1 : 2),
        ...sideTickMarks(x + w, y, x + w, y + h, isSquare ? 1 : 2),
      ]
    : [];
  const cornerMarks = [
    {
      name: "top-left",
      points: `${x},${y} ${x + corner},${y} ${x + corner},${y + corner} ${x},${y + corner}`,
    },
    {
      name: "top-right",
      points: `${x + w},${y} ${x + w - corner},${y} ${x + w - corner},${y + corner} ${x + w},${y + corner}`,
    },
    {
      name: "bottom-right",
      points: `${x + w},${y + h} ${x + w - corner},${y + h} ${x + w - corner},${y + h - corner} ${x + w},${y + h - corner}`,
    },
    {
      name: "bottom-left",
      points: `${x},${y + h} ${x + corner},${y + h} ${x + corner},${y + h - corner} ${x},${y + h - corner}`,
    },
  ];

  return (
    <Svg width={svgW} height={svgH}>
      <Rect
        x={x}
        y={y}
        width={w}
        height={h}
        fill={theme.contentSurface}
        stroke={theme.primary}
        strokeWidth={2}
        rx={isSquare ? 2 : 4}
      />
      {tickSegments.length > 0 ? (
        <TickMarks segments={tickSegments} color={theme.textSecondary} />
      ) : null}
      {showCornerBracket ? (
        <>
          {cornerMarks.map((mark) => (
            <Polygon
              key={mark.name}
              testID={`rectangle-right-angle-${mark.name}`}
              points={mark.points}
              fill="none"
              stroke={theme.textSecondary}
              strokeWidth={1.5}
              accessible={false}
            />
          ))}
        </>
      ) : null}
      {spec.show_diagonal ? (
        <Line
          x1={x}
          y1={y}
          x2={x + w}
          y2={y + h}
          stroke={colors.diagonal}
          strokeWidth={2}
          strokeDasharray="6,4"
        />
      ) : null}
      <SvgText
        testID="rectangle-side-label-top"
        x={x + w / 2}
        y={y - 10}
        fill={theme.text}
        fontSize={13}
        fontFamily={UI_FONT.semibold}
        textAnchor="middle"
      >
        {isSquare ? labels.side : labels.width}
      </SvgText>
      <SvgText
        testID="rectangle-side-label-bottom"
        x={x + w / 2}
        y={y + h + 18}
        fill={theme.text}
        fontSize={13}
        fontFamily={UI_FONT.semibold}
        textAnchor="middle"
      >
        {isSquare ? labels.side : labels.width}
      </SvgText>
      <SvgText
        testID="rectangle-side-label-left"
        x={x - 8}
        y={y + h / 2}
        fill={theme.text}
        fontSize={13}
        fontFamily={UI_FONT.semibold}
        textAnchor="end"
        alignmentBaseline="middle"
      >
        {isSquare ? labels.side : labels.height}
      </SvgText>
      <SvgText
        testID="rectangle-side-label-right"
        x={x + w + 8}
        y={y + h / 2}
        fill={theme.text}
        fontSize={13}
        fontFamily={UI_FONT.semibold}
        textAnchor="start"
        alignmentBaseline="middle"
      >
        {isSquare ? labels.side : labels.height}
      </SvgText>
      {spec.show_diagonal && labels.diagonal ? (
        <SvgText
          x={x + w / 2 + 8}
          y={y + h / 2 - 6}
          fill={colors.diagonal}
          fontSize={12}
          fontFamily={UI_FONT.semibold}
        >
          {labels.diagonal}
        </SvgText>
      ) : null}
      {showDiagonalAngleLabel && labels.angle ? (
        // Diagonal-vs-base angle at the top-left (where TL→BR diagonal
        // meets the top edge) — NOT the rectangle's own 90° corner.
        // Arc + ∠ label; bracket is suppressed when the diagonal is drawn.
        <>
          <Path
            d={diagonalAngleArcPath(x, y, w, h)}
            fill="none"
            stroke={theme.textSecondary}
            strokeWidth={1.5}
            accessible={false}
          />
          <SvgText
            x={x + 22}
            y={y + 28}
            fill={theme.textSecondary}
            fontSize={12}
            fontFamily={UI_FONT.regular}
          >
            {`∠\u00A0${labels.angle}`}
          </SvgText>
        </>
      ) : null}
      {spec.show_area && labels.area ? (
        <SvgText
          x={x + w / 2}
          y={y + h + 40}
          fill={theme.textSecondary}
          fontSize={12}
          fontFamily={UI_FONT.regular}
          textAnchor="middle"
        >
          {`${i18n.t("rich.area")}\u00A0${labels.area}`}
        </SvgText>
      ) : null}
      {spec.show_perimeter && labels.perimeter ? (
        <SvgText
          x={x + w / 2}
          y={y + h + (spec.show_area ? 56 : 40)}
          fill={theme.textSecondary}
          fontSize={12}
          fontFamily={UI_FONT.regular}
          textAnchor="middle"
        >
          {`${i18n.t("rich.perimeter")}\u00A0${labels.perimeter}`}
        </SvgText>
      ) : null}
    </Svg>
  );
}
