import { Text as SvgText } from "react-native-svg";

import {
  prepareQuadrilateralFrame,
  QuadrilateralDimensionLabels,
  QuadrilateralFrame,
} from "@/components/rich/geometry/QuadrilateralFrame";
import {
  computeParallelogramLabels,
  geometryLabelInset,
  parallelogramLayout,
  type ParallelogramSpec,
} from "@/lib/math/geometryBlock";
import i18n from "@/lib/i18n";
import { type Theme } from "@/lib/theme";
import { UI_FONT } from "@/lib/uiFont";

export function ParallelogramDiagram({
  spec,
  screenWidth,
  theme,
}: {
  spec: ParallelogramSpec;
  screenWidth: number;
  theme: Theme;
}) {
  const labels = computeParallelogramLabels(spec);
  const padding =
    spec.show_labels !== false
      ? {
          left: geometryLabelInset(labels.height, 12),
          right: geometryLabelInset(labels.side, 12),
        }
      : { left: 40, right: 40 };
  const { svgW, svgH, bx0, bx1, by, tx0, tx1, ty } = parallelogramLayout(
    spec,
    screenWidth,
    padding,
  );
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
  const [tl, tr, br, bl] = verts;

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
            top={labels.base}
            bottom={labels.base}
            height={labels.height}
            theme={theme}
          />
          <SvgText
            x={(tl.x + bl.x) / 2 - 8}
            y={(tl.y + bl.y) / 2 - 10}
            fill={theme.text}
            fontSize={12}
            fontFamily={UI_FONT.semibold}
            textAnchor="end"
          >
            {labels.side}
          </SvgText>
          <SvgText
            x={(tr.x + br.x) / 2 + 8}
            y={(tr.y + br.y) / 2 - 10}
            fill={theme.text}
            fontSize={12}
            fontFamily={UI_FONT.semibold}
            textAnchor="start"
          >
            {labels.side}
          </SvgText>
          {(spec.show_perimeter ? labels.perimeter : labels.area) ? (
            <SvgText
              x={(bl.x + br.x) / 2}
              y={bl.y + 40}
              fill={theme.textSecondary}
              fontSize={12}
              fontFamily={UI_FONT.regular}
              textAnchor="middle"
            >
              {spec.show_perimeter
                ? `${i18n.t("rich.perimeter")}\u00A0${labels.perimeter}`
                : `${i18n.t("rich.area")}\u00A0${labels.area}`}
            </SvgText>
          ) : null}
        </>
      ) : null}
    </QuadrilateralFrame>
  );
}
