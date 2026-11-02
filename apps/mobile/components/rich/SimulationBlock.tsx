/** Native Skia renderer for verified physics simulation scenes. */
import { Text, View } from "react-native";
import { Canvas, Circle, DashPathEffect, Path } from "@shopify/react-native-skia";

import { FLUID_TINT, SIMULATION_PAD } from "@/lib/physics/simulation";
import { withAlpha } from "@/lib/theme";
import { PlaybackButton } from "@/components/rich/PlaybackButton";
import { linePath } from "@/components/rich/skia/paths";
import { planetFill, SceneLabels } from "@/components/rich/simulation/labels";
import { RENDER_TEST_MARKERS, SceneMarkers } from "@/components/rich/simulation/markers";
import {
  AngleArc,
  BodyMarks,
  BodyShape,
  PulleyWheel,
  SolidShape,
  SpringCoil,
  Support,
  Tether,
} from "@/components/rich/simulation/parts";
import { pivotPath, polygonPath, wallPath } from "@/components/rich/simulation/paths";
import { sceneAnchors, useSimulationScene } from "@/components/rich/simulation/useSimulationScene";
import { ARROW_STROKE, RidingVector, StatedVector } from "@/components/rich/simulation/vectors";

const CENTRE_DOT_RADIUS = 3;
/** How strongly a strobe copy shows: enough to read the spacing, never a second body. */
const STROBE_OPACITY = 0.28;

type Props = { content: string };

export function SimulationBlock({ content }: Props) {
  const {
    theme,
    t,
    font,
    fallbacks,
    spec,
    width,
    styles,
    height,
    transform,
    animated,
    layout,
    trackPaths,
    description,
    title,
    progress,
    isPlaying,
    play,
    pause,
    reduceMotion,
  } = useSimulationScene(content);

  if (!spec || !transform || !layout) {
    return (
      <View style={styles.fallback}>
        <Text style={styles.fallbackText}>{t("rich.simulation_error")}</Text>
      </View>
    );
  }

  const { tracks, closed, maxSpeed, floorY, obstacles } = layout;
  const { centre, groundY, surface, wedge, slope, beam, pivot, anchor, wheel } = sceneAnchors(
    spec,
    transform,
    layout,
  );
  const bodyColor = (role: "primary" | "secondary") =>
    role === "primary" ? theme.primary : theme.graphSeries[1];
  const fluid = theme.isDark ? FLUID_TINT.dark : FLUID_TINT.light;
  const solidFill = withAlpha(theme.textTertiary, 0.14);

  return (
    <View style={styles.wrap}>
      <Text style={styles.title}>{title}</Text>
      <View
        accessible
        accessibilityRole="image"
        accessibilityLabel={description}
        style={{ width, height }}
      >
        <Canvas testID="simulation-canvas" style={{ width, height }}>
          {/* Solids and fluids sit behind everything else. */}
          {layout.solids.map((solid, index) => (
            <SolidShape
              key={`solid-${index}`}
              layout={solid}
              fill={
                solid.solid.kind === "fluid"
                  ? withAlpha(fluid, theme.isDark ? 0.22 : 0.16)
                  : solidFill
              }
              edge={solid.solid.kind === "fluid" ? fluid : theme.textTertiary}
            />
          ))}
          {layout.planet ? (
            <>
              <Circle
                cx={layout.planet.centre.px}
                cy={layout.planet.centre.py}
                r={layout.planet.radius}
                color={planetFill(theme)}
              />
              <Circle
                cx={layout.planet.centre.px}
                cy={layout.planet.centre.py}
                r={layout.planet.radius}
                color={withAlpha(theme.textTertiary, 0.55)}
                style="stroke"
                strokeWidth={1}
              />
            </>
          ) : null}
          {wedge ? <Path path={polygonPath(wedge)} color={solidFill} /> : null}
          {trackPaths.map((path, index) => (
            <Path
              key={`track-${index}`}
              path={path}
              color={theme.textTertiary}
              style="stroke"
              strokeWidth={ARROW_STROKE}
            >
              <DashPathEffect intervals={[4, 4]} />
            </Path>
          ))}
          {surface ? (
            <Path
              path={linePath(surface.x1, surface.y1, surface.x2, surface.y2)}
              color={theme.textSecondary}
              style="stroke"
              strokeWidth={ARROW_STROKE}
            />
          ) : null}
          {spec.ground ? (
            <Path
              path={linePath(SIMULATION_PAD / 2, groundY, width - SIMULATION_PAD / 2, groundY)}
              color={theme.textSecondary}
              style="stroke"
              strokeWidth={ARROW_STROKE}
            />
          ) : null}
          {beam ? (
            <Path
              path={linePath(beam.a.px, beam.a.py, beam.b.px, beam.b.py)}
              color={theme.textSecondary}
              style="stroke"
              strokeWidth={3}
              strokeCap="round"
            />
          ) : null}
          {pivot ? <Path path={pivotPath(pivot)} color={theme.textSecondary} /> : null}
          {anchor ? (
            <Path
              path={wallPath(anchor, spec.ground ? groundY : null)}
              color={theme.textSecondary}
              style="stroke"
              strokeWidth={2}
            />
          ) : null}
          {anchor && tracks[0] ? (
            <SpringCoil
              anchor={anchor}
              track={tracks[0]}
              progress={progress}
              color={theme.textSecondary}
            />
          ) : null}
          {layout.pulley ? <PulleyWheel layout={layout.pulley} theme={theme} /> : null}
          {layout.tethers.map((tether, index) =>
            tether.support ? (
              <Support key={`support-${index}`} layout={tether.support} theme={theme} />
            ) : null,
          )}
          {layout.angles.map((angle, index) => (
            <AngleArc key={`angle-${index}`} layout={angle} theme={theme} />
          ))}
          {layout.vectors.map((vector, index) =>
            vector.body !== null ? (
              <RidingVector
                key={`vector-${index}`}
                layout={vector}
                track={tracks[vector.body]}
                progress={progress}
                wheel={wheel}
                theme={theme}
                canvasWidth={width}
                canvasHeight={height}
              />
            ) : (
              <StatedVector key={`vector-${index}`} layout={vector} theme={theme} />
            ),
          )}
          {centre && !layout.planet ? (
            <Circle cx={centre.px} cy={centre.py} r={CENTRE_DOT_RADIUS} color={theme.textSecondary} />
          ) : null}
          {spec.bodies.map((body, index) =>
            layout.strobes[index].map((point, copy) => (
              <BodyShape
                key={`strobe-${index}-${copy}`}
                at={point}
                radius={layout.radii[index]}
                boxAngle={layout.boxAngles[index]}
                color={bodyColor(body.role)}
                opacity={STROBE_OPACITY}
              />
            )),
          )}
          {layout.restLines.map((line, index) => (
            <Path
              key={`rest-${index}`}
              path={linePath(line.x1, line.y1, line.x2, line.y2)}
              color={theme.textTertiary}
              style="stroke"
              strokeWidth={1}
            >
              <DashPathEffect intervals={[3, 3]} />
            </Path>
          ))}
          {layout.tethers.map((tether, index) => (
            <Tether
              key={`tether-${index}`}
              anchor={tether.anchor}
              track={tracks[tether.body]}
              radius={layout.radii[tether.body]}
              boxAngle={layout.boxAngles[tether.body]}
              progress={progress}
              color={theme.textSecondary}
            />
          ))}
          {spec.bodies.map((body, index) => (
            <BodyMarks
              key={`body-${index}`}
              track={tracks[index]}
              closed={closed[index]}
              maxSpeed={maxSpeed}
              radius={layout.radii[index]}
              boxAngle={layout.boxAngles[index]}
              color={bodyColor(body.role)}
              arrows={spec.arrows}
              centre={centre}
              slope={slope}
              floorY={floorY}
              obstacles={obstacles}
              progress={progress}
              theme={theme}
              canvasWidth={width}
              canvasHeight={height}
            />
          ))}
          {/* Labels last, over every line, each with a halo so nothing strikes it through. */}
          {font ? (
            <SceneLabels
              spec={spec}
              layout={layout}
              font={font}
              fallbacks={fallbacks}
              wheel={wheel}
              theme={theme}
              progress={progress}
              centre={centre}
              slope={slope}
              canvasWidth={width}
              canvasHeight={height}
            />
          ) : null}
        </Canvas>
        {RENDER_TEST_MARKERS ? (
          <SceneMarkers
            spec={spec}
            layout={layout}
            surface={surface !== null}
            centre={centre !== null}
            beam={beam !== null}
            pivot={pivot !== null}
            spring={anchor !== null}
            reduceMotion={reduceMotion === true}
          />
        ) : null}
      </View>
      {animated ? (
        <PlaybackButton
          testID="simulation"
          isPlaying={isPlaying}
          onPlay={play}
          onPause={pause}
          playLabel={t("rich.simulation_play_a11y")}
          pauseLabel={t("rich.simulation_pause_a11y")}
        />
      ) : null}
    </View>
  );
}
