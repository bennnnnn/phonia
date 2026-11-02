import { useMemo } from "react";
import { StyleSheet, Text } from "react-native";
import { useTranslation } from "react-i18next";

import { EditableProfileAvatar } from "@/features/account/components/EditableProfileAvatar";
import { useAuth } from "@/contexts/AuthContext";
import { getDisplayName } from "@/lib/profile";
import { Space } from "@/lib/space";
import { type Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";

/** The avatar and name at the top of Settings and Profile. */
export function ProfileHeader({ label, onPress }: { label: string; onPress: () => void }) {
  const { user, token } = useAuth();
  const { t } = useTranslation();
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);

  return (
    <>
      <EditableProfileAvatar
        name={user?.name ?? null}
        uri={user?.avatar_url}
        token={token}
        size={88}
        icon="pencil"
        label={label}
        onPress={onPress}
      />
      <Text style={s.name} accessibilityRole="header">
        {getDisplayName(user?.name, t("common.you"))}
      </Text>
    </>
  );
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    name: {
      ...Type.h1,
      ...Weight.semibold,
      color: theme.text,
      textAlign: "center",
      marginTop: Space.md,
      paddingHorizontal: Space.md,
    },
  });
}
