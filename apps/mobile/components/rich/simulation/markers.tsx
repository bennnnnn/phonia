/** The scene's test markers, one per drawn part, and the switch that renders them. */
import { StyleSheet, View } from "react-native";

import type { SceneLayout, SimulationSpec } from "@/lib/physics/simulation";

/**
 * The invisible geometry markers exist for component tests, which cannot see
 * inside a Skia canvas. They are never shipped to a screen reader.
 */
export const RENDER_TEST_MARKERS = process.env.NODE_ENV === "test";

export function SceneMarkers({
  spec,
  layout,
  surface,
  centre,
  beam,
  pivot,
  spring,
  reduceMotion,
}: {
  spec: SimulationSpec;
  layout: SceneLayout;
  surface: boolean;
  centre: boolean;
  beam: boolean;
  pivot: boolean;
  spring: boolean;
  reduceMotion: boolean;
}) {
  const marker = (testID: string, key?: string) => (
    <View key={key ?? testID} testID={testID} style={markerStyle} />
  );
  return (
    <View
      pointerEvents="none"
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={StyleSheet.absoluteFill}
    >
      {surface ? marker("simulation-slope") : null}
      {spec.ground ? marker("simulation-ground") : null}
      {beam ? marker("simulation-beam") : null}
      {pivot ? marker("simulation-pivot") : null}
      {centre ? marker("simulation-centre") : null}
      {spring ? marker("simulation-spring") : null}
      {reduceMotion ? marker("simulation-static") : null}
      {layout.pulley ? marker("simulation-pulley") : null}
      {layout.planet ? marker("simulation-planet") : null}
      {layout.tethers.map((tether, index) => (
        <View key={`tether-marker-${index}`} testID="simulation-tether" style={markerStyle}>
          {tether.support ? marker("simulation-support") : null}
        </View>
      ))}
      {layout.angles.map((angle, index) => (
        <View
          key={`angle-marker-${index}`}
          testID={`simulation-angle-${angle.angle.role}`}
          style={markerStyle}
        >
          {angle.head ? marker("simulation-angle-arrow") : null}
          {angle.label ? marker("simulation-angle-label") : null}
        </View>
      ))}
      {layout.solids.map((solid, index) =>
        marker(`simulation-solid-${solid.solid.kind}`, `solid-marker-${index}`),
      )}
      {layout.arrowLabels.map((label, index) =>
        marker(`simulation-arrow-label-${label.kind}`, `arrow-label-marker-${index}`),
      )}
      {spec.bodies.map((body, bodyIndex) => (
        <View key={`body-marker-${bodyIndex}`}>
          <View testID="simulation-body" style={markerStyle} />
          {layout.boxAngles[bodyIndex] !== null ? marker("simulation-body-box") : null}
          {body.label ? <View testID="simulation-body-label" style={markerStyle} /> : null}
          {layout.strobes[bodyIndex].map((_, copy) =>
            marker("simulation-strobe", `strobe-marker-${bodyIndex}-${copy}`),
          )}
          {spec.arrows.map((arrow) => (
            <View
              key={`${bodyIndex}-${arrow}`}
              testID={`simulation-arrow-${arrow}`}
              style={markerStyle}
            />
          ))}
        </View>
      ))}
      {layout.vectors.map((vector, index) => (
        <View
          key={`vector-marker-${index}`}
          testID={`simulation-vector-${vector.vector.role}`}
          style={markerStyle}
        >
          {vector.label ? <View testID="simulation-vector-label" style={markerStyle} /> : null}
          {vector.body !== null ? marker("simulation-vector-attached") : null}
        </View>
      ))}
    </View>
  );
}

const markerStyle = {
  position: "absolute" as const,
  width: 1,
  height: 1,
  opacity: 0,
};
