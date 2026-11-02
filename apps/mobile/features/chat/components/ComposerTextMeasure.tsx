import { useRef } from "react";
import { StyleSheet, Text, View } from "react-native";

import { COMPOSER_INPUT_LINE_HEIGHT } from "@/features/chat/model/composerLogic";
import { DYNAMIC_TYPE_MAX, Type } from "@/lib/type";

export type ComposerTextSize = { naturalWidth: number; height: number };

type Props = {
  text: string;
  /** The field's width; the draft wraps here exactly as the input does. */
  width: number;
  onMeasure: (size: ComposerTextSize) => void;
};

/**
 * Lays the draft out off screen in the field's font: once on one line (how wide
 * it really is) and once at the field width (how many lines it really takes).
 * Glyph estimates run wide, which wrapped the composer before the text did.
 */
export function ComposerTextMeasure({ text, width, onMeasure }: Props) {
  const size = useRef<ComposerTextSize>({ naturalWidth: 0, height: 0 });
  const report = (next: Partial<ComposerTextSize>) => {
    const merged = { ...size.current, ...next };
    if (
      merged.naturalWidth === size.current.naturalWidth &&
      merged.height === size.current.height
    ) {
      return;
    }
    size.current = merged;
    onMeasure(merged);
  };
  if (!text || width <= 0) return null;
  // A trailing return opens a line the input shows; Text drops it without a glyph after it.
  const shown = `${text}​`;
  return (
    <View
      style={styles.box}
      pointerEvents="none"
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
    >
      <Text
        style={[styles.text, styles.natural]}
        maxFontSizeMultiplier={DYNAMIC_TYPE_MAX}
        onLayout={(e) => report({ naturalWidth: Math.ceil(e.nativeEvent.layout.width) })}
      >
        {shown}
      </Text>
      <Text
        style={[styles.text, { width }]}
        maxFontSizeMultiplier={DYNAMIC_TYPE_MAX}
        onLayout={(e) => report({ height: Math.ceil(e.nativeEvent.layout.height) })}
      >
        {shown}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  // Wide enough that the one-line copy never wraps; absolute, so it takes no room.
  box: { position: "absolute", left: 0, top: 0, width: 100_000, opacity: 0 },
  text: { ...Type.body, lineHeight: COMPOSER_INPUT_LINE_HEIGHT },
  natural: { alignSelf: "flex-start" },
});
