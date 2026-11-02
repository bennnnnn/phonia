/** A static circuit schematic: the source on the left, the network along the top. */
import { useMemo } from "react";
import { useWindowDimensions } from "react-native";
import { useTranslation } from "react-i18next";
import { Circle, Group, Path, Skia, type SkFont } from "@shopify/react-native-skia";

import { figureWidth } from "@/components/rich/figure";
import { HaloText } from "@/components/rich/skia/HaloText";
import { arrowPath } from "@/components/rich/skia/paths";
import { partSymbolPaths, sourceSymbolPaths } from "@/components/rich/diagrams/circuitSymbols";
import {
  DiagramFrame,
  useDiagramFont,
  useDiagramTitle,
} from "@/components/rich/diagrams/DiagramFrame";
import type { CircuitDiagramSpec } from "@/components/rich/diagrams/spec";
import { measureDiagramText } from "@/components/rich/diagrams/textWidth";
import {
  BRACKET_TICK,
  describeCircuit,
  layoutCircuit,
  type CircuitRole,
  type TextMark,
} from "@/lib/physics/circuit";
import { useTheme, type Theme } from "@/lib/theme";

const WIRE_STROKE = 1.5;
const PLATE_STROKE = 3;
const JUNCTION_RADIUS = 2.5;
const CURRENT_HEAD = 6;

function ink(role: CircuitRole, theme: Theme, fallback: string): string {
  return role === "result" ? theme.primary : fallback;
}

/**
 * A label where the layout put it. The layout measured it with the face's own
 * advances (`textWidth.ts`), which is what Skia draws, so no re-measure.
 */
function Label({ mark, font, color, theme }: { mark: TextMark; font: SkFont; color: string; theme: Theme }) {
  return <HaloText x={mark.x} y={mark.y} text={mark.text} font={font} color={color} halo={theme.bg} />;
}

export function CircuitDiagram({ spec }: { spec: CircuitDiagramSpec }) {
  const theme = useTheme();
  const { t } = useTranslation();
  const { width: screenWidth } = useWindowDimensions();
  const width = figureWidth(screenWidth);
  const font = useDiagramFont();
  const title = useDiagramTitle(spec);
  const layout = useMemo(() => layoutCircuit(spec.circuit, width, measureDiagramText), [spec, width]);
  // The title is its own text above the canvas, so the description does not repeat it.
  const description = useMemo(() => spec.alt ?? describeCircuit(spec.circuit, t), [spec, t]);

  const drawing = useMemo(() => {
    const wires = Skia.Path.Make();
    for (const segment of layout.wires) {
      wires.moveTo(segment.x1, segment.y1);
      wires.lineTo(segment.x2, segment.y2);
    }
    const brackets = layout.groups.map((group) => {
      const path = Skia.Path.Make();
      path.moveTo(group.x1, group.y + BRACKET_TICK);
      path.lineTo(group.x1, group.y);
      path.lineTo(group.x2, group.y);
      path.lineTo(group.x2, group.y + BRACKET_TICK);
      return path;
    });
    const current = layout.current
      ? arrowPath(
          layout.current.x,
          layout.current.tailY,
          0,
          -1,
          layout.current.tailY - layout.current.tipY,
          CURRENT_HEAD,
          "filled",
        )
      : null;
    return {
      wires,
      brackets,
      current,
      source: sourceSymbolPaths(layout.source.kind, layout.source.cx, layout.source.cy),
      parts: layout.parts.map((part) => partSymbolPaths(part.part, part.cx, part.cy)),
    };
  }, [layout]);

  const markers = useMemo(
    () => [
      `diagram-source-${spec.circuit.source.kind}`,
      ...layout.parts.map((part) => `diagram-part-${part.part}`),
      ...layout.parts.filter((part) => part.role === "result").map(() => "diagram-part-result"),
      ...layout.groups.map((group) => (group.role === "result" ? "diagram-group-result" : "diagram-group")),
      ...layout.junctions.map(() => "diagram-junction"),
      ...(layout.current ? ["diagram-current"] : []),
    ],
    [layout, spec],
  );

  const wireColor = theme.textSecondary;
  return (
    <DiagramFrame
      testID="circuit-canvas"
      title={title}
      description={description}
      width={width}
      height={layout.height}
      markers={markers}
    >
      <Group transform={[{ translateX: layout.offsetX }, { scale: layout.scale }]}>
        <Path
          path={drawing.wires}
          color={wireColor}
          style="stroke"
          strokeWidth={WIRE_STROKE}
          strokeCap="round"
          strokeJoin="round"
        />
        {layout.junctions.map((junction, index) => (
          <Circle key={`junction-${index}`} cx={junction.x} cy={junction.y} r={JUNCTION_RADIUS} color={wireColor} />
        ))}
        <Path
          path={drawing.source.stroke}
          color={wireColor}
          style="stroke"
          strokeWidth={WIRE_STROKE}
          strokeCap="round"
          strokeJoin="round"
        />
        {drawing.source.heavy ? (
          <Path path={drawing.source.heavy} color={wireColor} style="stroke" strokeWidth={PLATE_STROKE} />
        ) : null}
        {drawing.parts.map((paths, index) => {
          const color = ink(layout.parts[index].role, theme, wireColor);
          return (
            <Group key={`part-${index}`}>
              <Path
                path={paths.stroke}
                color={color}
                style="stroke"
                strokeWidth={WIRE_STROKE}
                strokeCap="round"
                strokeJoin="round"
              />
              {paths.heavy ? (
                <Path path={paths.heavy} color={color} style="stroke" strokeWidth={2} strokeCap="round" />
              ) : null}
            </Group>
          );
        })}
        {drawing.brackets.map((path, index) => (
          <Path
            key={`bracket-${index}`}
            path={path}
            color={ink(layout.groups[index].role, theme, theme.textTertiary)}
            style="stroke"
            strokeWidth={1}
            strokeJoin="round"
          />
        ))}
        {drawing.current ? (
          <>
            <Path path={drawing.current} color={wireColor} style="stroke" strokeWidth={WIRE_STROKE} strokeJoin="round" />
            <Path path={drawing.current} color={wireColor} style="fill" />
          </>
        ) : null}
        {/* Labels last, each with a halo, so no wire strikes one through. */}
        {font ? (
          <>
            {layout.parts.map((part, index) => (
              <Group key={`part-labels-${index}`}>
                {part.label ? (
                  <Label mark={part.label} font={font} color={ink(part.role, theme, theme.text)} theme={theme} />
                ) : null}
                {part.detail ? (
                  <Label
                    mark={part.detail}
                    font={font}
                    color={ink(part.role, theme, theme.textSecondary)}
                    theme={theme}
                  />
                ) : null}
              </Group>
            ))}
            {layout.groups.map((group, index) => (
              <Label
                key={`group-label-${index}`}
                mark={group.text}
                font={font}
                color={ink(group.role, theme, theme.textSecondary)}
                theme={theme}
              />
            ))}
            {layout.source.label ? (
              <Label mark={layout.source.label} font={font} color={theme.text} theme={theme} />
            ) : null}
            {layout.current ? (
              <Label mark={layout.current.label} font={font} color={theme.text} theme={theme} />
            ) : null}
          </>
        ) : null}
      </Group>
    </DiagramFrame>
  );
}
