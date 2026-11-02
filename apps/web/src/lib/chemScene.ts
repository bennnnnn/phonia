/** A short markdown summary of a server ```chem_scene fence.
 *
 * The phone draws the scene; the web slice is text only. This never shows the JSON: an
 * unreadable scene falls back to its title, or to a plain label.
 */

type Json = Record<string, unknown>;

function record(value: unknown): Json | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Json)
    : null;
}

function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function list(value: unknown): Json[] {
  return Array.isArray(value)
    ? value.flatMap((item) => {
        const row = record(item);
        return row ? [row] : [];
      })
    : [];
}

function bullets(lines: string[]): string {
  return lines.filter(Boolean).map((line) => `- ${line}`).join("\n");
}

function sceneLines(scene: Json): string[] {
  switch (text(scene.kind)) {
    case "balance": {
      const charge = record(scene.charge);
      const rows = list(scene.rows).map(
        (row) => `${text(row.element)}: ${String(row.left)} → ${String(row.right)}`,
      );
      return charge ? [...rows, `charge: ${String(charge.left)} → ${String(charge.right)}`] : rows;
    }
    case "stoich":
      return list(scene.steps).map((step, index) => `${index + 1}. ${text(step.label)} = ${text(step.value)}`);
    case "vsepr": {
      const terminals = Array.isArray(scene.terminals) ? scene.terminals.join(" · ") : "";
      return [
        `${terminals} around ${text(scene.central)}`,
        `${text(scene.geometry)}, ${text(scene.bond_angle)}, ${String(scene.lone_pairs)} lone pair(s)`,
        `electron geometry ${text(scene.electron_geometry)}, ideal ${text(scene.ideal_angle)}`,
      ];
    }
    case "titration":
      return [
        text(scene.region),
        ...list(scene.anchors).map((anchor) =>
          [
            text(anchor.label),
            text(anchor.ph) && `pH ${text(anchor.ph)}`,
            text(anchor.volume),
            text(anchor.value),
          ]
            .filter(Boolean)
            .join(" · "),
        ),
      ];
    case "equilibrium":
      return list(scene.rows).map(
        (row) =>
          `${text(row.species)}: ${text(row.initial)} ${text(row.change)} → ${text(row.equilibrium)}`,
      );
    case "cell":
      return [
        `anode ${text(scene.anode)}`,
        `cathode ${text(scene.cathode)}`,
        text(scene.potential),
        `electrons ${text(scene.electrons)}`,
      ];
    default:
      return [];
  }
}

export function chemSceneMarkdown(body: string): string {
  let scene: Json | null;
  try {
    scene = record(JSON.parse(body.trim()));
  } catch {
    scene = null;
  }
  if (!scene) return "*Chemistry diagram*";
  const title = text(scene.title);
  const lines = bullets(sceneLines(scene));
  const heading = title ? `*${title}*` : "*Chemistry diagram*";
  return lines ? `${heading}\n\n${lines}` : heading;
}
