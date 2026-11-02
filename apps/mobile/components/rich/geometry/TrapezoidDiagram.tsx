import { Text as SvgText } from "react-native-svg";

import {
  prepareQuadrilateralFrame,
  QuadrilateralDimensionLabels,
  QuadrilateralFrame,
} from "@/components/rich/geometry/QuadrilateralFrame";
import {
  computeTrapezoidLabels,
  geometryLabelInset,
  type TrapezoidSpec,
} from "@/lib/math/geometryBlock";
import i18n from "@/lib/i18n";
import { type Theme } from "@/lib/theme";
import { UI_FONT } from "@/lib/uiFont";

export function TrapezoidDiagram({
  spec,
  screenWidth,
  theme,
}: {
  spec: TrapezoidSpec;
  screenWidth: number;
  theme: Theme;
}) {
  const labels = computeTrapezoidLabels(spec);
  const offsetX = spec.show_labels !== false ? geometryLabelInset(labels.height, 12) : 40;
  const rightPad = 40;
  const inner = Math.max(screenWidth - 48 - offsetX - rightPad, 1);
  const scale = inner / Math.max(spec.top, spec.bottom, spec.height, 1);
  const topW = spec.top * scale;
  const bottomW = spec.bottom * scale;
  const h = spec.height * scale;
  const offsetY = 28;
  const bx0 = offsetX;
  const bx1 = offsetX + bottomW;
  const by = offsetY + h;
  const tx0 = offsetX + (bottomW - topW) / 2;
  const tx1 = tx0 + topW;
  const ty = offsetY;
  const svgW = bottomW + offsetX + rightPad;
  const svgH = h + offsetY + 40;
  const showLabels = spec.show_labels !== false;
  const showAngle = spec.show_angle === true;
  const frame = prepareQuadrilateralFrame(
    [
      { x: tx0, y: ty },
      { x: tx1, y: ty },
      { x: bx1, y: by },
      { x: bx0, y: by },
    ],
    svgW,
    svgH,
    showAngle,
  );
  const verts = frame.vertices;
  const [, , br, bl] = verts;

  return (
    <QuadrilateralFrame
      {...frame}
      theme={theme}
      showAngle={showAngle}
    >
      {showLabels ? (
        <>
          <QuadrilateralDimensionLabels
            vertices={verts}
            top={labels.top}
            bottom={labels.bottom}
            height={labels.height}
            theme={theme}
          />
          {labels.area ? (
            <SvgText x={(bl.x + br.x) / 2} y={bl.y + 34} fill={theme.textSecondary} fontSize={12} fontFamily={UI_FONT.regular} textAnchor="middle">
              {`${i18n.t("rich.area")}\u00A0${labels.area}`}
            </SvgText>
          ) : null}
        </>
      ) : null}
    </QuadrilateralFrame>
  );
}
