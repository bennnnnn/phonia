import { useMemo } from "react";
import { Pressable, StyleSheet } from "react-native";
import Animated, { type SharedValue } from "react-native-reanimated";
import { Icon } from "@/ui/icons/Icon";
import { useTranslation } from "react-i18next";

import { CountBadge } from "@/ui/feedback/CountBadge";
import { Theme, useTheme } from "@/lib/theme";
import { formatScrollAwayBadge } from "@/features/chat/model/scrollLogic";
import { tap } from "@/lib/haptics";
import { IconSize } from "@/ui/icons/sizes";
import { Radius } from "@/lib/radius";
import { useBottomLiftStyle } from "@/ui/hooks/useBottomLiftStyle";

type Props = {
  visible: boolean;
  bottomOffset: number;
  /** Rides the keyboard with the composer, frame by frame. */
  lift?: SharedValue<number>;
  scrollAwayCount: number;
  onPress: () => void;
};

export function ChatScrollFab({ visible, bottomOffset, lift, scrollAwayCount, onPress }: Props) {
  const { t } = useTranslation();
  const C = useTheme();
  const s = useMemo(() => makeS(C), [C]);
  const liftStyle = useBottomLiftStyle(lift);
  const badgeLabel = formatScrollAwayBadge(scrollAwayCount);

  if (!visible) return null;

  return (
    <Animated.View
      style={[s.overlay, { bottom: bottomOffset }, lift ? liftStyle : null]}
      pointerEvents="box-none"
    >
      <Pressable
        style={s.button}
        onPress={() => {
          tap();
          onPress();
        }}
        accessibilityRole="button"
        accessibilityLabel={t("chat.scroll_to_latest")}
      >
        <Icon name="chevron-down" size={IconSize.md} color={C.text} />
        {badgeLabel ? (
          <CountBadge count={scrollAwayCount} max={9} style={s.badge} />
        ) : null}
      </Pressable>
    </Animated.View>
  );
}

const makeS = (C: Theme) =>
  StyleSheet.create({
    overlay: {
      position: "absolute",
      left: 0,
      right: 0,
      alignItems: "center",
      zIndex: 95,
    },
    button: {
      width: 44,
      height: 44,
      borderRadius: Radius.full,
      backgroundColor: C.surface,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: C.border,
      alignItems: "center",
      justifyContent: "center",
    },
    badge: {
      position: "absolute",
      top: -4,
      right: -4,
    },
  });
