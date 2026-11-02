import { Pressable, StyleSheet, View } from "react-native";
import Svg, { Rect } from "react-native-svg";
import { useTranslation } from "react-i18next";

import { useTheme } from "@/lib/theme";
import { IconSize } from "@/ui/icons/sizes";

type Props = {
  /** The composer's control size: the button sits in its row. */
  size: number;
  disabled?: boolean;
  onPress: () => void;
};

/** ChatGPT voice-mode glyph: four rounded vertical bars. */
function LiveTalkWaveformIcon({ size = 18, color }: { size?: number; color: string }) {
  const w = 2.2;
  const gap = 1.7;
  const bars = [8, 16, 12, 6];
  const total = bars.length * w + (bars.length - 1) * gap;
  const originX = (24 - total) / 2;
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24">
      {bars.map((h, i) => (
        <Rect
          key={i}
          x={originX + i * (w + gap)}
          y={(24 - h) / 2}
          width={w}
          height={h}
          rx={1.1}
          fill={color}
        />
      ))}
    </Svg>
  );
}

export function LiveTalkButton({ size, disabled, onPress }: Props) {
  const { t } = useTranslation();
  const theme = useTheme();
  const box = { width: size, height: size };

  return (
    <Pressable
      style={[styles.hit, box, disabled && styles.dim]}
      onPress={onPress}
      disabled={disabled}
      hitSlop={8}
      accessibilityRole="button"
      accessibilityLabel={t("chat.live_talk_a11y")}
      testID="live-talk-button"
    >
      {/* The user's bubble tint as a filled circle, so it follows their accent. */}
      <View
        testID="live-talk-circle"
        style={[styles.btn, box, { borderRadius: size / 2, backgroundColor: theme.userBubble }]}
      >
        <LiveTalkWaveformIcon size={IconSize.md} color={theme.text} />
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  hit: {
    alignItems: "center",
    justifyContent: "center",
  },
  dim: { opacity: 0.55 },
  btn: {
    alignItems: "center",
    justifyContent: "center",
  },
});
