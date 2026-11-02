/**
 * A static ray diagram: the element at x = 0 on the optical axis, the object
 * and its image, and the rays exactly as the server traced them.
 */
import { useMemo } from "react";
import { useWindowDimensions } from "react-native";
import { useTranslation } from "react-i18next";
import { DashPathEffect, Group, Path, Skia, type SkPath } from "@shopify/react-native-skia";

import { figureWidth } from "@/components/rich/figure";
import {
  appendArrowHead,
  arrowHeadPath,
  arrowPath,
  arrowShaftPath,
  linePath,
  pointsPath,
  segmentsPath,
} from "@/components/rich/skia/paths";
import {
  DiagramFrame,
  useDiagramFont,
  useDiagramTitle,
} from "@/components/rich/diagrams/DiagramFrame";
import { DiagramLabel, MeasureLine, rectPath } from "@/components/rich/diagrams/marks";
import type { RayDiagramSpec } from "@/components/rich/diagrams/spec";
import { measureDiagramText } from "@/components/rich/diagrams/textWidth";
import { describeOptics, focalPoints, RAY_HEAD, worldViewportHeight } from "@/lib/physics/optics";
import { layoutRayScene, LENS_HEAD, type RayScene, type StandingArrow } from "@/lib/physics/rayScene";
import { useTheme, withAlpha, type Theme } from "@/lib/theme";

const ELEMENT_STROKE = 2;
const RAY_STROKE = 1.5;
const ARROW_STROKE = 2;

type ArrowPaths = { solid: SkPath | null; shaft: SkPath | null; head: SkPath | null };

/** An object or image standing on the axis; a virtual one is dashed, its head solid. */
function standingArrowPaths(arrow: StandingArrow, axis: number): ArrowPaths {
  const { x, length, uy, head } = arrow;
  if (!arrow.virtual) return { solid: arrowPath(x, axis, 0, uy, length, head, "filled"), shaft: null, head: null };
  return {
    solid: null,
    shaft: arrowShaftPath(x, axis, 0, uy, Math.max(0, length - head * 0.6)),
    head: arrowHeadPath(x, axis, 0, uy, length, head, "filled"),
  };
}

/** The element's strokes: a lens's line with its heads, an interface's boundary, a mirror's face. */
function elementPath(scene: RayScene, width: number): SkPath {
  const { element, elementX, extent, axis } = scene;
  if (element.kind === "interface") return linePath(0, axis, width, axis);
  if (element.kind === "mirror") return pointsPath(element.curve);
  const path = linePath(elementX, extent.top, elementX, extent.bottom);
  appendArrowHead(path, elementX, extent.top, 0, element.outward ? -1 : 1, LENS_HEAD, "open");
  appendArrowHead(path, elementX, extent.bottom, 0, element.outward ? 1 : -1, LENS_HEAD, "open");
  return path;
}

/** The scene's Skia paths. */
function scenePaths(scene: RayScene, width: number) {
  return {
    element: elementPath(scene, width),
    hatch: scene.element.kind === "mirror" ? segmentsPath(scene.element.hatches) : null,
    focusTicks: segmentsPath(scene.focusTicks),
    rays: scene.rays.map((ray) => {
      const heads = Skia.Path.Make();
      for (const mark of ray.marks) appendArrowHead(heads, mark.x, mark.y, mark.ux, mark.uy, RAY_HEAD, "filled");
      return { virtual: ray.virtual, line: pointsPath(ray.points), heads };
    }),
    object: scene.object ? standingArrowPaths(scene.object, scene.axis) : null,
    image: scene.image ? standingArrowPaths(scene.image, scene.axis) : null,
    angles: scene.angles.map((angle) => {
      const path = pointsPath(angle.points);
      if (angle.arrow) {
        const end = angle.points[angle.points.length - 1];
        appendArrowHead(path, end.px, end.py, angle.endDirection.ux, angle.endDirection.uy, 6, "open");
      }
      return { path, role: angle.role };
    }),
  };
}

function ArrowShape({ paths, color }: { paths: ArrowPaths; color: string }) {
  return (
    <>
      {paths.solid ? (
        <>
          <Path path={paths.solid} color={color} style="stroke" strokeWidth={ARROW_STROKE} strokeJoin="round" strokeCap="round" />
          <Path path={paths.solid} color={color} style="fill" />
        </>
      ) : null}
      {paths.shaft ? (
        <Path path={paths.shaft} color={color} style="stroke" strokeWidth={ARROW_STROKE}>
          <DashPathEffect intervals={[4, 3]} />
        </Path>
      ) : null}
      {paths.head ? (
        <>
          <Path path={paths.head} color={color} style="stroke" strokeWidth={1} strokeJoin="round" />
          <Path path={paths.head} color={color} style="fill" />
        </>
      ) : null}
    </>
  );
}

export function RayDiagram({ spec }: { spec: RayDiagramSpec }) {
  const theme = useTheme();
  const { t } = useTranslation();
  const { width: screenWidth } = useWindowDimensions();
  const width = figureWidth(screenWidth);
  const font = useDiagramFont();
  const title = useDiagramTitle(spec);
  const height = useMemo(() => worldViewportHeight(spec.bounds, width), [spec, width]);
  // The title is its own text above the canvas, so the description does not repeat it.
  const description = useMemo(
    () => spec.alt ?? describeOptics(spec.optics, spec.angles, t),
    [spec, t],
  );

  const scene = useMemo(
    () => layoutRayScene(spec, width, height, measureDiagramText, t("rich.diagram_mark_focus")),
    [height, spec, t, width],
  );
  const paths = useMemo(() => scenePaths(scene, width), [scene, width]);

  const markers = useMemo(() => {
    const { optics } = spec;
    return [
      `diagram-element-${optics.element}`,
      ...focalPoints(optics).map(() => "diagram-focus"),
      ...(optics.object ? ["diagram-object"] : []),
      ...(optics.image ? [optics.image.virtual ? "diagram-image-virtual" : "diagram-image"] : []),
      ...optics.rays.map((ray) => (ray.virtual ? "diagram-ray-virtual" : "diagram-ray")),
      ...spec.angles.map((angle) => (angle.role === "result" ? "diagram-angle-result" : "diagram-angle")),
      ...scene.media.map(() => "diagram-medium"),
      ...spec.measures.map(() => "diagram-measure"),
    ];
  }, [scene, spec]);

  const rayColor = theme.graphSeries[2];
  const faintRay = withAlpha(rayColor, 0.6);
  const interfaceKind = spec.optics.element === "interface";
  return (
    <DiagramFrame
      testID="rays-canvas"
      title={title}
      description={description}
      width={width}
      height={height}
      markers={markers}
    >
      <Group clip={Skia.XYWHRect(0, 0, width, height)}>
        {interfaceKind ? (
          <>
            <Path path={rectPath(0, 0, width, scene.axis)} color={withAlpha(theme.textTertiary, 0.07)} />
            <Path
              path={rectPath(0, scene.axis, width, height - scene.axis)}
              color={withAlpha(theme.primary, 0.1)}
            />
            <Path
              path={linePath(scene.elementX, 4, scene.elementX, height - 4)}
              color={theme.textTertiary}
              style="stroke"
              strokeWidth={1}
            >
              <DashPathEffect intervals={[4, 4]} />
            </Path>
          </>
        ) : (
          <Path
            path={linePath(0, scene.axis, width, scene.axis)}
            color={theme.textTertiary}
            style="stroke"
            strokeWidth={1}
          />
        )}
        <Path
          path={paths.element}
          color={theme.textSecondary}
          style="stroke"
          strokeWidth={interfaceKind ? 1.5 : ELEMENT_STROKE}
          strokeCap="round"
          strokeJoin="round"
        />
        {paths.hatch ? (
          <Path path={paths.hatch} color={theme.textTertiary} style="stroke" strokeWidth={1} />
        ) : null}
        <Path path={paths.focusTicks} color={theme.textSecondary} style="stroke" strokeWidth={1.5} />
        {paths.rays.map((ray, index) =>
          ray.virtual ? (
            <Path key={`ray-${index}`} path={ray.line} color={faintRay} style="stroke" strokeWidth={1}>
              <DashPathEffect intervals={[4, 4]} />
            </Path>
          ) : (
            <Group key={`ray-${index}`}>
              <Path path={ray.line} color={rayColor} style="stroke" strokeWidth={RAY_STROKE} strokeJoin="round" />
              <Path path={ray.heads} color={rayColor} style="fill" />
            </Group>
          ),
        )}
        {paths.object ? <ArrowShape paths={paths.object} color={theme.text} /> : null}
        {paths.image ? <ArrowShape paths={paths.image} color={theme.primary} /> : null}
        {paths.angles.map((angle, index) => (
          <Path
            key={`angle-${index}`}
            path={angle.path}
            color={angleColor(angle.role, theme)}
            style="stroke"
            strokeWidth={angle.role === "result" ? 2 : 1.5}
            strokeCap="round"
          />
        ))}
        {scene.measures.map((measure, index) => (
          <MeasureLine key={`measure-${index}`} layout={measure} color={theme.textSecondary} />
        ))}
      </Group>
      {font ? (
        <>
          {scene.media.map((label, index) => (
            <DiagramLabel key={`medium-${index}`} label={label} font={font} color={theme.textSecondary} theme={theme} />
          ))}
          {scene.focusLabels.map((label, index) => (
            <DiagramLabel key={`focus-${index}`} label={label} font={font} color={theme.textSecondary} theme={theme} />
          ))}
          {scene.objectLabel ? (
            <DiagramLabel label={scene.objectLabel} font={font} color={theme.text} theme={theme} />
          ) : null}
          {scene.imageLabel ? (
            <DiagramLabel label={scene.imageLabel} font={font} color={theme.primary} theme={theme} />
          ) : null}
          {scene.angleLabels.map((label, index) =>
            label ? (
              <DiagramLabel
                key={`angle-label-${index}`}
                label={label}
                font={font}
                color={angleColor(scene.angles[index].role, theme)}
                theme={theme}
              />
            ) : null,
          )}
          {scene.measures.map((measure, index) =>
            measure.label ? (
              <DiagramLabel
                key={`measure-label-${index}`}
                label={measure.label}
                font={font}
                color={theme.textSecondary}
                theme={theme}
              />
            ) : null,
          )}
        </>
      ) : null}
    </DiagramFrame>
  );
}

function angleColor(role: "given" | "result", theme: Theme): string {
  return role === "result" ? theme.primary : theme.textSecondary;
}
