/** Play / pause under a moving figure: the kit's 44 pt IconButton on a hairline plate. */
import { StyleSheet } from "react-native";

import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { useTheme } from "@/lib/theme";
import { IconButton } from "@/ui/controls/IconButton";
import { Icon } from "@/ui/icons/Icon";
import { IconSize } from "@/ui/icons/sizes";

export function PlaybackButton({
  testID,
  isPlaying,
  onPlay,
  onPause,
  playLabel,
  pauseLabel,
}: {
  /** Prefix for `-control`, `-play-symbol` and `-stop-symbol`. */
  testID: string;
  isPlaying: boolean;
  onPlay: () => void;
  onPause: () => void;
  playLabel: string;
  pauseLabel: string;
}) {
  const theme = useTheme();
  return (
    <IconButton
      testID={`${testID}-control`}
      onPress={isPlaying ? onPause : onPlay}
      accessibilityLabel={isPlaying ? pauseLabel : playLabel}
      icon={
        <Icon
          testID={isPlaying ? `${testID}-stop-symbol` : `${testID}-play-symbol`}
          name={isPlaying ? "pause" : "play"}
          size={IconSize.sm}
          color={theme.primary}
        />
      }
      style={[styles.plate, { borderColor: theme.border }]}
    />
  );
}

const styles = StyleSheet.create({
  plate: {
    marginTop: Space.xxs,
    borderRadius: Radius.full,
    borderWidth: StyleSheet.hairlineWidth,
  },
});
