import Svg, { Circle, Line, Text as SvgText } from "react-native-svg";

import { diagramColors } from "@/components/rich/geometry/GeometryMarks";
import {
  computeCircleLabels,
  scaleToFit,
  type CircleSpec,
} from "@/lib/math/geometryBlock";
import i18n from "@/lib/i18n";
import { type Theme } from "@/lib/theme";
import { UI_FONT } from "@/lib/uiFont";

export function CircleDiagram({
  spec,
  screenWidth,
  theme,
}: {
  spec: CircleSpec;
  screenWidth: number;
  theme: Theme;
}) {
  const colors = diagramColors(theme);
  const labels = computeCircleLabels(spec);
  const layout = scaleToFit(spec.radius * 2, spec.radius * 2, screenWidth - 48);
  const r = layout.w / 2;
  const offsetX = 40;
  const offsetY = 36;
  const cx = offsetX + r;
  const cy = offsetY + r;
  const svgW = r * 2 + offsetX * 2;
  const captions = [
    spec.show_diameter && labels.diameter
      ? `${i18n.t("rich.diameter")}\u00A0${labels.diameter}`
      : "",
    spec.show_area && labels.area ? `${i18n.t("rich.area")}\u00A0${labels.area}` : "",
    spec.show_circumference && labels.circumference
      ? `${i18n.t("rich.circumference")}\u00A0${labels.circumference}`
      : "",
  ].filter((line) => line.length > 0);
  const svgH =
    r * 2 + offsetY * 2 + (captions.length > 0 ? 16 * captions.length + 20 : 0);
  const showLabels = spec.show_labels !== false;

  return (
    <Svg width={svgW} height={svgH}>
      <Circle
        cx={cx}
        cy={cy}
        r={r}
        fill={theme.contentSurface}
        stroke={theme.primary}
        strokeWidth={2}
      />
      <Line
        x1={spec.show_diameter ? cx - r : cx}
        y1={cy}
        x2={cx + r}
        y2={cy}
        stroke={colors.diagonal}
        strokeWidth={2}
        strokeDasharray="6,4"
      />
      {showLabels ? (
        <SvgText
          x={spec.show_diameter ? cx : cx + r / 2}
          y={cy - 8}
          fill={colors.diagonal}
          fontSize={12}
          fontFamily={UI_FONT.semibold}
          textAnchor="middle"
        >
          {spec.show_diameter && labels.diameter ? labels.diameter : labels.radius}
        </SvgText>
      ) : null}
      {captions.map((line, index) => (
        <SvgText
          key={line}
          x={cx}
          y={cy + r + 34 + index * 16}
          fill={theme.textSecondary}
          fontSize={12}
          fontFamily={UI_FONT.regular}
          textAnchor="middle"
        >
          {line}
        </SvgText>
      ))}
    </Svg>
  );
}
