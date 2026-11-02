/** The words for a scene: its title, and what a screen reader hears for it. */
import { type SimulationSpec } from "@/lib/physics/simulation/spec";

type Translate = (key: string, options?: Record<string, unknown>) => string;

/**
 * The scene's title: the translated name when the server sent a key this build
 * knows, else the server's English `title`, else the generic word.
 */
export function sceneTitle(spec: SimulationSpec, t: Translate): string {
  if (spec.titleKey) {
    const key = `rich.scene_title_${spec.titleKey}`;
    const translated = t(key);
    // i18next hands a missing key back unchanged.
    if (translated && translated !== key) return translated;
  }
  return spec.title ?? t("rich.simulation_title");
}

/**
 * What a screen reader hears for the scene when the server sent no `alt`: its
 * title, its bodies, the arrows it derives and the labels the solver stated —
 * the same facts the picture shows, in the order a sighted reader takes them in.
 */
export function describeSimulation(spec: SimulationSpec, t: Translate): string {
  const sentences: string[] = [sceneTitle(spec, t)];
  if (spec.bodies.length > 0) {
    sentences.push(
      spec.bodies.map((body) => body.label ?? t("rich.simulation_a11y_body")).join(", "),
    );
  }
  if (spec.inclineDeg !== undefined) {
    sentences.push(t("rich.simulation_a11y_slope", { degrees: Math.round(spec.inclineDeg) }));
  }
  if (spec.arrows.length > 0) {
    const names = spec.arrows.map((arrow) => {
      const name = t(`rich.simulation_arrow_${arrow}`);
      const label = spec.arrowLabels[arrow];
      return label ? `${name} ${label}` : name;
    });
    sentences.push(t("rich.simulation_a11y_arrows", { list: names.join(", ") }));
  }
  const labels = [
    ...spec.vectors.flatMap((vector) => (vector.label ? [vector.label] : [])),
    ...spec.angles.flatMap((angle) => (angle.label ? [angle.label] : [])),
  ];
  if (labels.length > 0) sentences.push(labels.join(", "));
  return sentences.map((sentence) => sentence.replace(/[.\s]+$/, "")).join(". ") + ".";
}

/** The canvas's accessibility label: the server's sentence when it sent one. */
export function simulationAccessibilityLabel(spec: SimulationSpec, t: Translate): string {
  return spec.alt ?? describeSimulation(spec, t);
}
