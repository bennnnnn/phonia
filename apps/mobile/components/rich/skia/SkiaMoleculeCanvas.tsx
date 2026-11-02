import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import {
  Canvas,
  Circle,
  Group,
  Path,
  Text as SkiaText,
  useFont,
} from "@shopify/react-native-skia";

import {
  ATOM_INK,
  atomColor,
  atomLabelColor,
  bondStrokeWidth,
  layoutMolecule,
  MOLECULE_PREVIEW_HEIGHT,
  showsAtomLabel,
  type MoleculeStyle,
} from "@/lib/chemistry/molecule3dLayout";
import type { MolGeometry } from "@/lib/chemistry/molecule3dFence";
import type { Theme } from "@/lib/theme";
import { linePath } from "@/components/rich/skia/paths";

type Props = {
  geom: MolGeometry;
  style: MoleculeStyle;
  theme: Theme;
  yaw: number;
  pitch: number;
  width: number;
  height?: number;
};

export function SkiaMoleculeCanvas({
  geom,
  style,
  theme,
  yaw,
  pitch,
  width,
  height = MOLECULE_PREVIEW_HEIGHT,
}: Props) {
  const { t } = useTranslation();
  const font = useFont(require("../../../assets/fonts/SpaceMono-Regular.ttf"), 12);
  const laidOut = useMemo(
    () => layoutMolecule(geom, yaw, pitch, width, height, style),
    [geom, height, pitch, style, width, yaw],
  );
  const paths = useMemo(
    () => laidOut.bonds.map((bond) => linePath(bond.x1, bond.y1, bond.x2, bond.y2)),
    [laidOut.bonds],
  );

  return (
    <Canvas
      testID="molecule-skia-canvas"
      accessibilityLabel={t("rich.chemistry_3d_a11y")}
      style={{ width, height }}
    >
      {laidOut.drawOrder.map((item) => {
        if (item.kind === "bond") {
          return (
            <Path
              key={`bond-${laidOut.bonds[item.index]!.key}`}
              path={paths[item.index]!}
              color={theme.text}
              style="stroke"
              strokeWidth={bondStrokeWidth(style)}
              strokeCap="round"
            />
          );
        }
        const atom = laidOut.atoms[item.index]!;
        return (
          <Group key={`atom-${atom.index}`}>
            <Circle cx={atom.x} cy={atom.y} r={atom.radius + 1.75} color={ATOM_INK} />
            <Circle cx={atom.x} cy={atom.y} r={atom.radius} color={atomColor(atom.element)} />
            {showsAtomLabel(style) && font ? (
              <SkiaText
                x={atom.x - font.measureText(atom.element).width / 2}
                y={atom.y + 4}
                text={atom.element}
                font={font}
                color={atomLabelColor(atom.element)}
              />
            ) : null}
          </Group>
        );
      })}
    </Canvas>
  );
}
