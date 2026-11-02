import { useMemo } from "react";
import { ActivityIndicator, Pressable, StyleSheet, View } from "react-native";

import { Avatar } from "@/components/Avatar";
import { Icon } from "@/ui/icons/Icon";
import { type Theme, useTheme } from "@/lib/theme";
import { Radius } from "@/lib/radius";
import { IconSize } from "@/ui/icons/sizes";

type Props = {
  name: string | null;
  uri?: string | null;
  token: string | null;
  size: number;
  icon: "pencil" | "camera";
  label: string;
  onPress: () => void;
  disabled?: boolean;
  busy?: boolean;
};

export function EditableProfileAvatar({
  name, uri, token, size, icon, label, onPress, disabled, busy,
}: Props) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled || busy}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ disabled: Boolean(disabled || busy), busy: Boolean(busy) }}
      style={({ pressed }) => [s.avatar, pressed && s.pressed]}
    >
      <View accessibilityElementsHidden importantForAccessibility="no-hide-descendants">
        <Avatar name={name} uri={uri} token={token} size={size} />
        <View style={s.badge}>
          {busy ? <ActivityIndicator size="small" color={theme.text} /> : (
            <Icon name={icon} size={IconSize.md} color={theme.text} />
          )}
        </View>
      </View>
    </Pressable>
  );
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    avatar: { alignSelf: "center" },
    pressed: { opacity: 0.65 },
    badge: {
      position: "absolute",
      right: -2,
      bottom: 0,
      width: 40,
      height: 40,
      borderRadius: Radius.full,
      borderWidth: 3,
      borderColor: theme.bg,
      backgroundColor: theme.settingsSurface,
      alignItems: "center",
      justifyContent: "center",
    },
  });
}
