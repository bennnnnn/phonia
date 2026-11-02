/**
 * 3D molecule viewer — native-first Skia ball-and-stick from SDF coordinates.
 * A WebView WebGL viewer stays blank in WKWebView (CSP / zero-size canvas), so we
 * project the same 3D coords that RDKit already computed. Expo Go and stale
 * native clients safely use the matching SVG renderer.
 */
import { lazy, Suspense, useCallback, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Pressable, StyleSheet, View } from "react-native";
import Svg, { Circle, G, Line, Text as SvgText } from "react-native-svg";

import { CopyButton } from "@/components/CopyButton";
import { MoleculeCaption, MoleculeNote } from "@/components/rich/MoleculeChrome";
import { MoleculeRotateModal } from "@/components/rich/MoleculeRotateModal";
import {
  ATOM_INK,
  atomColor,
  atomLabelColor,
  bondStrokeWidth,
  layoutMolecule,
  showsAtomLabel,
  MOLECULE_PREVIEW_HEIGHT,
  type MoleculeStyle,
} from "@/lib/chemistry/molecule3dLayout";
import { useFenceRefused } from "@/components/rich/useFenceRefused";
import { VisualCard } from "@/components/rich/VisualCard";
import {
  parseMolGeometry,
  parseMolecule3DFence,
  type MolGeometry,
} from "@/lib/chemistry/molecule3dFence";
import { CODE_FONT } from "@/lib/fonts";
import { isSkiaAvailable } from "@/lib/skiaAvailability";
import { Space } from "@/lib/space";
import { Theme, useTheme } from "@/lib/theme";
import { SegmentedControl } from "@/ui/controls/SegmentedControl";
import { Icon } from "@/ui/icons/Icon";
import { IconSize } from "@/ui/icons/sizes";

type Props = { content: string };

const SkiaMoleculeCanvasLazy = lazy(() =>
  import("@/components/rich/skia/SkiaMoleculeCanvas").then((module) => ({
    default: module.SkiaMoleculeCanvas,
  })),
);

type MoleculeCanvasProps = {
  geom: MolGeometry;
  style: MoleculeStyle;
  theme: Theme;
  yaw: number;
  pitch: number;
  width: number;
  height?: number;
};

const ROTATE_PER_PX = 0.012;
const PITCH_LIMIT = 1.2;

function SvgMoleculeCanvas({
  geom,
  style,
  theme,
  yaw,
  pitch,
  width,
  height = MOLECULE_PREVIEW_HEIGHT,
}: MoleculeCanvasProps) {
  const { t } = useTranslation();
  const laidOut = useMemo(
    () => layoutMolecule(geom, yaw, pitch, width, height, style),
    [geom, height, pitch, style, width, yaw],
  );

  return (
    <Svg
      testID="molecule-svg-fallback"
      width={width}
      height={height}
      accessibilityLabel={t("rich.chemistry_3d_a11y")}
    >
      {laidOut.drawOrder.map((item) => {
        if (item.kind === "bond") {
          const bond = laidOut.bonds[item.index]!;
          return (
            <Line
              key={`bond-${bond.key}`}
              x1={bond.x1}
              y1={bond.y1}
              x2={bond.x2}
              y2={bond.y2}
              stroke={theme.text}
              strokeWidth={bondStrokeWidth(style)}
              strokeLinecap="round"
            />
          );
        }
        const atom = laidOut.atoms[item.index]!;
        return (
          <G key={`atom-${atom.index}`}>
            <Circle cx={atom.x} cy={atom.y} r={atom.radius + 1.75} fill={ATOM_INK} />
            <Circle cx={atom.x} cy={atom.y} r={atom.radius} fill={atomColor(atom.element)} />
            {showsAtomLabel(style) ? (
              <SvgText
                x={atom.x}
                y={atom.y + 4}
                fill={atomLabelColor(atom.element)}
                fontFamily={CODE_FONT}
                fontSize={12}
                textAnchor="middle"
              >
                {atom.element}
              </SvgText>
            ) : null}
          </G>
        );
      })}
    </Svg>
  );
}

function MoleculeCanvas(props: MoleculeCanvasProps) {
  if (!isSkiaAvailable()) return <SvgMoleculeCanvas {...props} />;
  return (
    <Suspense fallback={<SvgMoleculeCanvas {...props} />}>
      <SkiaMoleculeCanvasLazy {...props} />
    </Suspense>
  );
}

/** 3D canvas + style picker without card chrome — used by Molecule3DBlock and MoleculeCard. */
export function Molecule3DView({ geom }: { geom: MolGeometry }) {
  const theme = useTheme();
  const { t } = useTranslation();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const [style, setStyle] = useState<MoleculeStyle>("ball-stick");
  const [canvasWidth, setCanvasWidth] = useState(320);
  const [yaw, setYaw] = useState(0.7);
  const [pitch, setPitch] = useState(0.35);
  const [open, setOpen] = useState(false);
  const yawRef = useRef(0.7);
  const pitchRef = useRef(0.35);
  const startYaw = useRef(0.7);
  const startPitch = useRef(0.35);
  yawRef.current = yaw;
  pitchRef.current = pitch;

  const onGrant = useCallback(() => {
    startYaw.current = yawRef.current;
    startPitch.current = pitchRef.current;
  }, []);
  const onMove = useCallback((translationX: number, translationY: number) => {
    setYaw(startYaw.current + translationX * ROTATE_PER_PX);
    setPitch(
      Math.max(
        -PITCH_LIMIT,
        Math.min(PITCH_LIMIT, startPitch.current + translationY * ROTATE_PER_PX),
      ),
    );
  }, []);

  const styles = useMemo(
    () => [
      { key: "ball-stick" as const, label: t("rich.chemistry_style_ball") },
      { key: "spacefill" as const, label: t("rich.chemistry_style_sphere") },
      { key: "wireframe" as const, label: t("rich.chemistry_style_wire") },
    ],
    [t],
  );

  return (
    <>
      <Pressable
        style={s.stage}
        onLayout={(event) => setCanvasWidth(Math.max(1, event.nativeEvent.layout.width))}
        onPress={() => setOpen(true)}
        testID="molecule-expand"
        accessibilityRole="button"
        accessibilityLabel={t("rich.expand")}
      >
        <MoleculeCanvas
          geom={geom}
          style={style}
          theme={theme}
          yaw={yaw}
          pitch={pitch}
          width={canvasWidth}
        />
        <View style={s.expandBadge} pointerEvents="none" testID="molecule-expand-cue">
          <Icon name="expand" size={IconSize.xs} color={theme.textSecondary} />
        </View>
      </Pressable>
      <MoleculeRotateModal visible={open} onClose={() => setOpen(false)} onGrant={onGrant} onMove={onMove}>
        {(size) => (
          <MoleculeCanvas
            geom={geom}
            style={style}
            theme={theme}
            yaw={yaw}
            pitch={pitch}
            width={size.width}
            height={size.height}
          />
        )}
      </MoleculeRotateModal>
      <View style={s.styleRow}>
        <SegmentedControl
          segments={styles}
          value={style}
          onChange={setStyle}
          accessibilityLabel={t("rich.chemistry_style_a11y")}
          testID="molecule-style"
        />
      </View>
    </>
  );
}

export function Molecule3DBlock({ content }: Props) {
  const theme = useTheme();
  const { t } = useTranslation();
  const s = useMemo(() => makeStyles(theme), [theme]);

  const parsed = useMemo(() => parseMolecule3DFence(content), [content]);
  const sdf = parsed?.sdf ?? "";
  const caption = parsed?.caption;
  const geom = useMemo(() => (sdf ? parseMolGeometry(sdf) : null), [sdf]);
  useFenceRefused("molecule3d", content, !parsed || !geom);

  if (!parsed || !geom) {
    return (
      <VisualCard label={t("rich.chemistry_structure")} icon="flask">
        <MoleculeNote text={t("rich.chemistry_invalid")} />
      </VisualCard>
    );
  }

  return (
    <VisualCard
      label={t("rich.chemistry_structure")}
      icon="flask"
      actions={
        <>
          <View style={s.spacer} />
          <CopyButton text={sdf} accessibilityLabel={t("rich.chemistry_copy_structure")} />
        </>
      }
    >
      {caption ? <MoleculeCaption text={caption} /> : null}

      <Molecule3DView geom={geom} />
    </VisualCard>
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    stage: {
      height: MOLECULE_PREVIEW_HEIGHT,
      backgroundColor: t.contentSurface,
    },
    expandBadge: {
      position: "absolute",
      bottom: 8,
      right: 8,
      width: 28,
      height: 28,
      alignItems: "center",
      justifyContent: "center",
    },
    spacer: { flex: 1 },
    styleRow: {
      paddingHorizontal: Space.sm + 2,
      paddingTop: Space.xs + 2,
    },
  });
}
