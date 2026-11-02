import { useMemo } from "react";
import { StyleSheet, Text, View } from "react-native";
import { useTranslation } from "react-i18next";

import { useFenceRefused } from "@/components/rich/useFenceRefused";
import { VisualCard } from "@/components/rich/VisualCard";
import { CHEMISTRY_SCENE_KINDS, parseChemistryScene, type ChemistryScene } from "@/lib/chemistry/scene";
import { Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";
import { Space } from "@/lib/space";

type Props = { content: string };
type Styles = ReturnType<typeof makeStyles>;
type Translate = (key: string, options?: Record<string, unknown>) => string;

/** Card title per scene kind. A vsepr card is titled by its formula, which the server sends. */
const SCENE_LABEL = {
  balance: "rich.chemistry_scene_balance",
  stoich: "rich.chemistry_scene_stoich",
  titration: "rich.chemistry_scene_titration",
  equilibrium: "rich.chemistry_scene_equilibrium",
  cell: "rich.chemistry_scene_cell",
} as const;

/** The fixed vocabulary of titration anchors the server emits. */
const ANCHOR_LABEL: Record<string, string> = {
  start: "rich.chemistry_anchor_start",
  "half-equivalence": "rich.chemistry_anchor_half",
  equivalence: "rich.chemistry_anchor_equivalence",
  solved: "rich.chemistry_anchor_solved",
};

/** What the galvanic-cell scene says about electron flow; the only fixed sentence it carries. */
const ELECTRON_FLOW = "anode to cathode";

const SCENE_BODY = { json: true, kinds: { field: "kind", known: CHEMISTRY_SCENE_KINDS } };

/** Draws a verified chemistry scene. It never computes a result. */
export function ChemistrySceneBlock({ content }: Props) {
  const theme = useTheme();
  const { t } = useTranslation();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const scene = useMemo(() => parseChemistryScene(content), [content]);
  useFenceRefused("chem_scene", content, scene === null, SCENE_BODY);

  if (!scene) {
    return (
      <VisualCard label={t("rich.chemistry_diagram")} icon="flask">
        <View style={s.body}>
          <Text style={s.muted}>{t("rich.chemistry_scene_invalid")}</Text>
        </View>
      </VisualCard>
    );
  }

  const label = scene.kind === "vsepr" ? scene.title : t(SCENE_LABEL[scene.kind]);
  return (
    <VisualCard label={label} icon="flask">
      <View style={s.body} testID="chemistry-scene-body">
        <SceneBody scene={scene} styles={s} t={t} />
      </View>
    </VisualCard>
  );
}

function Grid({
  header,
  rows,
  styles,
}: {
  header: string[];
  rows: string[][];
  styles: Styles;
}) {
  return (
    <View>
      <View style={styles.gridRow}>
        {header.map((cell, column) => (
          <Text key={column} style={[styles.cell, styles.head, column === 0 && styles.firstCell]}>
            {cell}
          </Text>
        ))}
      </View>
      {rows.map((row, index) => (
        <View key={`${row[0]}-${index}`} style={styles.gridRow}>
          {row.map((cell, column) => (
            <Text key={column} style={[styles.cell, column === 0 && styles.firstCell]}>
              {cell}
            </Text>
          ))}
        </View>
      ))}
    </View>
  );
}

function SceneBody({
  scene,
  styles,
  t,
}: {
  scene: ChemistryScene;
  styles: Styles;
  t: Translate;
}) {
  switch (scene.kind) {
    case "balance":
      return (
        <View>
          <Grid
            styles={styles}
            header={[
              t("rich.chemistry_element"),
              t("rich.chemistry_reactants"),
              t("rich.chemistry_products"),
            ]}
            rows={[
              ...scene.rows.map((row) => [row.element, String(row.left), String(row.right)]),
              [t("rich.chemistry_charge"), String(scene.charge.left), String(scene.charge.right)],
            ]}
          />
        </View>
      );
    case "stoich":
      return (
        <View>
          {scene.steps.map((step, index) => (
            <Text key={`${step.label}-${index}`} style={styles.line}>
              {index + 1}. {step.label} = {step.value}
            </Text>
          ))}
        </View>
      );
    case "vsepr":
      return (
        <View>
          <Text style={styles.angle}>{scene.bond_angle}</Text>
          <Text style={styles.line}>
            {t("rich.chemistry_around", {
              terminals: scene.terminals.join(" · "),
              central: scene.central,
            })}
          </Text>
          <Text style={styles.line}>{scene.geometry}</Text>
          <Text style={styles.muted}>
            {t("rich.chemistry_lone_pairs", { count: scene.lone_pairs })}
          </Text>
          <Text style={styles.muted}>
            {t("rich.chemistry_ideal_angle", {
              geometry: scene.electron_geometry,
              angle: scene.ideal_angle,
            })}
          </Text>
        </View>
      );
    case "titration":
      return (
        <View>
          <Text style={styles.line}>{scene.region}</Text>
          {scene.anchors.map((anchor) => {
            const key = ANCHOR_LABEL[anchor.label];
            const parts = [
              key ? t(key) : anchor.label,
              anchor.ph ? t("rich.chemistry_ph_value", { value: anchor.ph }) : "",
              anchor.volume ?? "",
              anchor.value ?? "",
              anchor.detail ?? "",
            ].filter(Boolean);
            return (
              <Text key={anchor.label} style={styles.line}>
                {parts.join(" · ")}
              </Text>
            );
          })}
        </View>
      );
    case "equilibrium":
      return (
        <Grid
          styles={styles}
          header={[
            t("rich.chemistry_species"),
            t("rich.chemistry_initial"),
            t("rich.chemistry_change"),
            t("rich.chemistry_equilibrium"),
          ]}
          rows={scene.rows.map((row) => [row.species, row.initial, row.change, row.equilibrium])}
        />
      );
    case "cell":
      return (
        <View>
          <Text style={styles.line}>
            {t("rich.chemistry_anode")}: {scene.anode}
          </Text>
          <Text style={styles.line}>
            {t("rich.chemistry_cathode")}: {scene.cathode}
          </Text>
          <Text style={styles.angle}>{scene.potential}</Text>
          <Text style={styles.muted}>
            {t("rich.chemistry_electrons")}:{" "}
            {scene.electrons === ELECTRON_FLOW
              ? t("rich.chemistry_anode_to_cathode")
              : scene.electrons}
          </Text>
        </View>
      );
    default: {
      const unreachable: never = scene;
      return unreachable;
    }
  }
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    // VisualCard leaves its content edge to edge (charts fill it); text keeps the header's inset,
    // or it sits on the border and the rounded corner clips the last line's first letter.
    body: { paddingHorizontal: Space.sm, paddingVertical: Space.sm },
    line: { ...Type.callout, color: t.text, marginBottom: Space.xs },
    angle: { ...Type.title, ...Weight.semibold, color: t.text, marginBottom: Space.xs },
    muted: { ...Type.caption, color: t.textSecondary },
    gridRow: { flexDirection: "row", gap: Space.sm, marginBottom: Space.xs },
    cell: { ...Type.callout, color: t.text, flex: 1 },
    firstCell: { flex: 0.8 },
    head: { ...Type.caption, ...Weight.semibold, color: t.textSecondary },
  });
}
