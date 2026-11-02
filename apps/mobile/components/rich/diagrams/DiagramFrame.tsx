/**
 * What every physics diagram shares around its canvas: the title above it in
 * the figure style, the canvas as one image for a screen reader, the label
 * font, and the fallback line a malformed fence shows instead.
 */
import { useMemo, type ReactNode } from "react";
import { StyleSheet, Text, View } from "react-native";
import { useTranslation } from "react-i18next";
import { Canvas, useFont, type SkFont } from "@shopify/react-native-skia";

import { figureTitleStyle } from "@/components/rich/figure";
import { DIAGRAM_FONT_SIZE } from "@/components/rich/diagrams/textWidth";
import type { PhysicsDiagramSpec } from "@/components/rich/diagrams/spec";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { Theme, useTheme } from "@/lib/theme";
import { Type } from "@/lib/type";

/**
 * The invisible markers exist for component tests, which cannot see inside a
 * Skia canvas. They are never shipped to a screen reader.
 */
const RENDER_TEST_MARKERS = process.env.NODE_ENV === "test";

/**
 * Source Sans 3, the app's UI face: unlike SpaceMono it carries Ω, λ and θ,
 * and a Skia font has no fallback for a glyph it lacks. `textWidth.ts` holds
 * its advances, so the layout knows every label's width before it loads.
 */
export function useDiagramFont(): SkFont | null {
  return useFont(
    require("@expo-google-fonts/source-sans-3/400Regular/SourceSans3_400Regular.ttf"),
    DIAGRAM_FONT_SIZE,
  );
}

/** The translated scene title when the fence names one, else its English title. */
export function useDiagramTitle(spec: PhysicsDiagramSpec): string {
  const { t } = useTranslation();
  const fallback = spec.title ?? t(`rich.diagram_title_${spec.kind}`);
  return spec.titleKey
    ? t(`rich.scene_title_${spec.titleKey}`, { defaultValue: fallback })
    : fallback;
}

export function DiagramFrame({
  testID,
  title,
  description,
  width,
  height,
  markers,
  children,
  footer,
}: {
  testID: string;
  title: string;
  /** The fence's `alt`, or a description built from the diagram. */
  description: string;
  width: number;
  height: number;
  /** Test-only ids for what the canvas drew; see `RENDER_TEST_MARKERS`. */
  markers: string[];
  children: ReactNode;
  footer?: ReactNode;
}) {
  const theme = useTheme();
  const styles = useMemo(() => makeFigureFrameStyles(theme), [theme]);
  return (
    <View style={styles.wrap}>
      <Text style={styles.title}>{title}</Text>
      <View
        accessible
        accessibilityRole="image"
        accessibilityLabel={description}
        style={{ width, height }}
      >
        <Canvas testID={testID} style={{ width, height }}>
          {children}
        </Canvas>
        {RENDER_TEST_MARKERS ? (
          <View
            pointerEvents="none"
            accessibilityElementsHidden
            importantForAccessibility="no-hide-descendants"
            style={StyleSheet.absoluteFill}
          >
            {markers.map((id, index) => (
              <View key={`${id}-${index}`} testID={id} style={markerStyle} />
            ))}
          </View>
        ) : null}
      </View>
      {footer}
    </View>
  );
}

export function DiagramFallback() {
  const theme = useTheme();
  const { t } = useTranslation();
  const styles = useMemo(() => makeFigureFrameStyles(theme), [theme]);
  return (
    <View testID="physics-diagram-fallback" style={styles.fallback}>
      <Text style={styles.fallbackText}>{t("rich.simulation_error")}</Text>
    </View>
  );
}

const markerStyle = {
  position: "absolute" as const,
  width: 1,
  height: 1,
  opacity: 0,
};

/** The frame's styles; a simulation scene draws in the same frame. */
export function makeFigureFrameStyles(theme: Theme) {
  return StyleSheet.create({
    wrap: {
      marginVertical: Space.xs,
      alignItems: "center",
    },
    title: figureTitleStyle(theme),
    fallback: {
      marginVertical: Space.xs,
      padding: Space.sm,
      borderRadius: Radius.md,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: theme.border,
    },
    fallbackText: {
      ...Type.compact,
      color: theme.textSecondary,
    },
  });
}
