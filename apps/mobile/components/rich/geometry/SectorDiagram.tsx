import Svg, { Path, Text as SvgText } from "react-native-svg";

import {
  computeSectorLabels,
  geometryLabelInset,
  scaleToFit,
  type SectorSpec,
} from "@/lib/math/geometryBlock";
import i18n from "@/lib/i18n";
import { type Theme } from "@/lib/theme";
import { UI_FONT } from "@/lib/uiFont";

export function SectorDiagram({
  spec,
  screenWidth,
  theme,
}: {
  spec: SectorSpec;
  screenWidth: number;
  theme: Theme;
}) {
  const labels = computeSectorLabels(spec);
  const layout = scaleToFit(spec.radius * 2, spec.radius * 2, screenWidth - 48);
  const r = layout.w / 2;
  const svgW = r * 2 + 80;
  const showLabels = spec.show_labels !== false;
  // Sweep clockwise from straight up (12 o'clock) by angle_deg. Include
  // the center and every cardinal point reached by the arc in its bounds.
  const startRad = (-90 * Math.PI) / 180;
  const endRad = ((-90 + spec.angle_deg) * Math.PI) / 180;
  const midRad = (startRad + endRad) / 2;
  const labelR = r * 0.55;
  const endX = r * Math.cos(endRad);
  const endY = r * Math.sin(endRad);
  let minX = spec.angle_deg >= 270 ? -r : Math.min(0, endX);
  let maxX = spec.angle_deg >= 90 ? r : Math.max(0, endX);
  const maxY = spec.angle_deg >= 180 ? r : Math.max(0, endY);
  if (showLabels) {
    minX = Math.min(minX, -geometryLabelInset(labels.radius, 12, 6, 0));
    const angleHalfWidth = geometryLabelInset(labels.angle, 12, 0, 0) / 2;
    const angleX = labelR * Math.cos(midRad);
    minX = Math.min(minX, angleX - angleHalfWidth);
    maxX = Math.max(maxX, angleX + angleHalfWidth);
  }
  const cx = (svgW - (maxX - minX)) / 2 - minX;
  const cy = 36 + r;
  const plotBottom = cy + maxY;
  const svgH = plotBottom + (showLabels ? 62 : 16);
  const x1 = cx;
  const y1 = cy - r;
  const x2 = cx + endX;
  const y2 = cy + endY;
  const largeArc = spec.angle_deg > 180 ? 1 : 0;
  // A single SVG arc with coincident endpoints cannot draw a full circle.
  const path =
    spec.angle_deg === 360
      ? `M${cx},${cy} L${x1},${y1} A${r},${r} 0 1 1 ${cx},${cy + r} A${r},${r} 0 1 1 ${x1},${y1} Z`
      : `M${cx},${cy} L${x1},${y1} A${r},${r} 0 ${largeArc} 1 ${x2},${y2} Z`;

  return (
    <Svg width={svgW} height={svgH}>
      <Path
        d={path}
        fill={theme.contentSurface}
        stroke={theme.primary}
        strokeWidth={2}
      />
      {showLabels ? (
        <>
          <SvgText
            x={cx + labelR * Math.cos(midRad)}
            y={cy + labelR * Math.sin(midRad)}
            fill={theme.text}
            fontSize={12}
            fontFamily={UI_FONT.semibold}
            textAnchor="middle"
          >
            {labels.angle}
          </SvgText>
          <SvgText
            x={(cx + x1) / 2 - 6}
            y={(cy + y1) / 2}
            fill={theme.accent}
            fontSize={12}
            fontFamily={UI_FONT.semibold}
            textAnchor="end"
          >
            {labels.radius}
          </SvgText>
          {spec.angle_deg < 360 ? (
            <SvgText
              testID="sector-second-radius-label"
              x={(cx + x2) / 2 + 8 * Math.cos(endRad + Math.PI / 2)}
              y={(cy + y2) / 2 + 8 * Math.sin(endRad + Math.PI / 2)}
              fill={theme.accent}
              fontSize={12}
              fontFamily={UI_FONT.semibold}
              textAnchor="middle"
            >
              {labels.radius}
            </SvgText>
          ) : null}
          {labels.area ? (
            <SvgText
              x={svgW / 2}
              y={plotBottom + 34}
              fill={theme.textSecondary}
              fontSize={12}
              fontFamily={UI_FONT.regular}
              textAnchor="middle"
            >
              {`${i18n.t("rich.area")}\u00A0${labels.area}`}
            </SvgText>
          ) : null}
          {labels.arc_length ? (
            <SvgText
              x={svgW / 2}
              y={plotBottom + (labels.area ? 50 : 34)}
              fill={theme.textSecondary}
              fontSize={12}
              fontFamily={UI_FONT.regular}
              textAnchor="middle"
            >
              {`${i18n.t("rich.arc_length")}\u00A0${labels.arc_length}`}
            </SvgText>
          ) : null}
        </>
      ) : null}
    </Svg>
  );
}
