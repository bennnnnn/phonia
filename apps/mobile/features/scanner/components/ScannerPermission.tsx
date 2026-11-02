import { useMemo } from "react";
import { Linking, Pressable, StyleSheet, Text, View } from "react-native";
import { useTranslation } from "react-i18next";

import { cameraPermissionNeedsSettings, type CameraPermissionSnapshot } from "@/lib/cameraPermission";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { type Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";

type Props = {
  permission: CameraPermissionSnapshot | null;
  requestPermission: () => void;
  /** The system Photos picker: it needs no photo-library permission. */
  onChoosePhoto: () => void;
  /** The Files picker, for an image saved outside Photos. */
  onChooseFile: () => void;
};

/** Without the camera: allow it (or open Settings), or read an image from Photos or Files. */
export function ScannerPermission({ permission, requestPermission, onChoosePhoto, onChooseFile }: Props) {
  const { t } = useTranslation();
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const settings = cameraPermissionNeedsSettings(permission);
  const allow = settings ? t("chat.location_open_settings") : t("chat.math_scan_allow_camera");

  return (
    <View style={s.center}>
      <Text style={s.text}>{t("chat.math_scan_permission")}</Text>
      <Pressable
        style={s.primary}
        testID="math-scanner-permission"
        accessibilityRole="button"
        accessibilityLabel={allow}
        onPress={() => {
          if (settings) {
            void Linking.openSettings();
            return;
          }
          requestPermission();
        }}
      >
        <Text style={s.primaryText}>{allow}</Text>
      </Pressable>
      <Pressable
        style={s.secondary}
        onPress={onChoosePhoto}
        testID="math-scanner-permission-photos"
        accessibilityRole="button"
        accessibilityLabel={t("chat.math_scan_photos_a11y")}
      >
        <Text style={s.secondaryText}>{t("chat.math_scan_choose_photo")}</Text>
      </Pressable>
      <Pressable
        style={s.secondary}
        onPress={onChooseFile}
        testID="math-scanner-permission-files"
        accessibilityRole="button"
        accessibilityLabel={t("chat.math_scan_files_a11y")}
      >
        <Text style={s.secondaryText}>{t("chat.math_scan_choose_file")}</Text>
      </Pressable>
    </View>
  );
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    center: {
      flex: 1,
      alignItems: "center",
      justifyContent: "center",
      paddingHorizontal: Space.xl,
      gap: Space.md,
    },
    text: {
      ...Type.body,
      color: theme.onMedia,
      textAlign: "center",
    },
    primary: {
      backgroundColor: theme.primary,
      paddingHorizontal: Space.gutter,
      paddingVertical: Space.sm,
      borderRadius: Radius.md,
    },
    primaryText: {
      ...Type.label,
      color: theme.onPrimary,
      ...Weight.bold,
    },
    secondary: {
      paddingHorizontal: Space.md,
      paddingVertical: Space.sm,
    },
    secondaryText: {
      ...Type.label,
      color: theme.onMedia,
      ...Weight.bold,
    },
  });
}
