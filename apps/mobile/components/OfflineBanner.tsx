import { StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTranslation } from "react-i18next";

import { Icon } from "@/ui/icons/Icon";
import { Layer } from "@/lib/layer";
import type { ConnectivityStatus } from "@/lib/networkProbe";
import { Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";
import { Space } from "@/lib/space";
import { IconSize } from "@/ui/icons/sizes";

type Props = {
  status: ConnectivityStatus;
};

export function OfflineBanner({ status }: Props) {
  const { t } = useTranslation();
  const theme = useTheme();
  const insets = useSafeAreaInsets();
  const s = makeStyles(theme);

  if (status === "online") return null;

  const label =
    status === "api_unreachable" ? t("common.api_unreachable") : t("common.no_internet");

  return (
    <View style={[s.wrap, { paddingTop: insets.top + 6 }]} accessibilityRole="alert">
      <Icon name="cloud-off" size={IconSize.xs} color={theme.onWarning} />
      <Text style={s.text}>{label}</Text>
    </View>
  );
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    wrap: {
      position: "absolute",
      top: 0,
      left: 0,
      right: 0,
      zIndex: Layer.toast,
      flexDirection: "row",
      alignItems: "center",
      justifyContent: "center",
      gap: Space.xs,
      paddingBottom: Space.xs,
      paddingHorizontal: Space.md,
      backgroundColor: theme.warning,
    },
    text: {
      ...Type.compact,
      ...Weight.bold,
      color: theme.onWarning,
    },
  });
}
