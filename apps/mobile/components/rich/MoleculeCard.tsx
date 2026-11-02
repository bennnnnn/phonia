/**
 * Combined 2D + optional 3D molecule card. Display-only ```molecule fences
 * (smiles paired with a following molecule3d) render here so the thread
 * does not stack two full cards.
 */
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { StyleSheet, View } from "react-native";

import { CopyButton } from "@/components/CopyButton";
import { Chemistry2DView } from "@/components/rich/ChemistryBlock";
import { MoleculeCaption, MoleculeNote } from "@/components/rich/MoleculeChrome";
import { Molecule3DView } from "@/components/rich/Molecule3DBlock";
import { useFenceRefused } from "@/components/rich/useFenceRefused";
import { VisualCard } from "@/components/rich/VisualCard";
import { parseMolGeometry, parseMolecule3DFence } from "@/lib/chemistry/molecule3dFence";
import { parseMoleculeFence } from "@/lib/chemistry/moleculePair";
import { SegmentedControl } from "@/ui/controls/SegmentedControl";

type Mode = "2d" | "3d";

/** Wide enough for two short labels; the control has no width of its own in a header. */
const MODE_TOGGLE_WIDTH = 116;

export function MoleculeCard({ content }: { content: string }) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<Mode>("2d");
  // Once 3D has been shown it stays mounted, so flipping back keeps its angle and style, and
  // the 2D WebView is never torn down and reloaded.
  const [seen3d, setSeen3d] = useState(false);

  const parsed = useMemo(() => parseMoleculeFence(content), [content]);
  const smiles = parsed?.smiles ?? "";
  const caption = parsed?.caption;
  const geometry = useMemo(() => {
    const raw = parsed?.sdf;
    if (!raw) return null;
    const mol = parseMolecule3DFence(raw);
    return mol?.sdf ? parseMolGeometry(mol.sdf) : null;
  }, [parsed]);
  useFenceRefused("molecule", content, parsed === null);

  if (!parsed) {
    return (
      <VisualCard label={t("rich.chemistry_structure")} icon="flask">
        <MoleculeNote text={t("rich.chemistry_invalid")} />
      </VisualCard>
    );
  }

  const active: Mode = geometry && mode === "3d" ? "3d" : "2d";
  const modeToggle = geometry ? (
    <View style={s.toggle}>
      <SegmentedControl
        segments={[
          { key: "2d", label: t("rich.chemistry_2d") },
          { key: "3d", label: t("rich.chemistry_3d") },
        ]}
        value={active}
        onChange={(next) => {
          if (next === "3d") setSeen3d(true);
          setMode(next);
        }}
        accessibilityLabel={t("rich.chemistry_view_a11y")}
        testID="molecule-mode"
      />
    </View>
  ) : undefined;

  return (
    <VisualCard
      label={t("rich.chemistry_structure")}
      icon="flask"
      headerRight={modeToggle}
      actions={<CopyButton text={smiles} accessibilityLabel={t("rich.chemistry_copy_smiles")} />}
    >
      {caption ? <MoleculeCaption text={caption} /> : null}

      <View style={active === "2d" ? undefined : s.hidden}>
        <Chemistry2DView smiles={smiles} fence="molecule" />
      </View>
      {geometry && (seen3d || active === "3d") ? (
        <View style={active === "3d" ? undefined : s.hidden}>
          <Molecule3DView geom={geometry} />
        </View>
      ) : null}
    </VisualCard>
  );
}

const s = StyleSheet.create({
  toggle: { width: MODE_TOGGLE_WIDTH },
  hidden: { display: "none" },
});
