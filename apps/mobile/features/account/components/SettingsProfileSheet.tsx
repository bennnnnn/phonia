import { useMemo } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { useTranslation } from "react-i18next";

import { Sheet } from "@/ui/overlay/Sheet";
import { EditableProfileAvatar } from "@/features/account/components/EditableProfileAvatar";
import { type useProfileEditor } from "@/features/account/hooks/useProfileEditor";
import { Space } from "@/lib/space";
import { type Theme, useTheme, withAlpha } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";
import { Radius } from "@/lib/radius";

type Props = {
  editor: ReturnType<typeof useProfileEditor>;
  avatarUri?: string | null;
  token: string | null;
};

export function SettingsProfileSheet({ editor, avatarUri, token }: Props) {
  const { t } = useTranslation();
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const busy = editor.saving || editor.picking;

  return (
    <Sheet
      visible={editor.visible}
      onClose={editor.close}
      variant="bottom"
      keyboardAvoiding
      handleColor={theme.textSecondary}
      backdropDismiss={!busy}
      backdropColor={withAlpha(theme.bg, 0.35)}
      contentContainerStyle={s.sheet}
    >
      <View style={s.body} testID="settings-profile-sheet">
        <EditableProfileAvatar
          name={editor.name}
          uri={editor.photo?.localUri ?? (editor.photoRemoved ? null : avatarUri)}
          token={token}
          size={144}
          icon="camera"
          label={t("settings.change_photo")}
          onPress={() => void editor.choosePhoto()}
          disabled={busy}
          busy={editor.picking}
        />
        {editor.photo || (avatarUri && !editor.photoRemoved) ? (
          <Pressable
            onPress={editor.removePhoto}
            disabled={busy}
            accessibilityRole="button"
            accessibilityState={{ disabled: busy }}
            style={({ pressed }) => [s.removePhoto, pressed && s.pressed]}
          >
            <Text style={s.removePhotoText}>{t("settings.remove_photo")}</Text>
          </Pressable>
        ) : null}
        <View style={s.nameField}>
          <Text style={s.nameLabel} accessible={false}>{t("settings.name_label")}</Text>
          <TextInput
            style={s.nameInput}
            accessibilityLabel={t("settings.name_label")}
            value={editor.name}
            onChangeText={editor.setName}
            editable={!busy}
            maxLength={80}
            autoCapitalize="words"
            autoCorrect={false}
            autoFocus
            returnKeyType="done"
            onSubmitEditing={() => void editor.save()}
          />
        </View>
        {editor.error ? <Text style={s.error} accessibilityRole="alert">{editor.error}</Text> : null}
        <Pressable
          onPress={() => void editor.save()}
          disabled={busy}
          accessibilityRole="button"
          accessibilityLabel={t("settings.save_profile")}
          accessibilityState={{ disabled: busy, busy: editor.saving }}
          style={({ pressed }) => [s.save, pressed && s.pressed, busy && s.disabled]}
        >
          {editor.saving ? <ActivityIndicator color={theme.bg} /> : (
            <Text style={s.saveText}>{t("settings.save_profile")}</Text>
          )}
        </Pressable>
        <Pressable
          onPress={editor.close}
          disabled={busy}
          accessibilityRole="button"
          accessibilityState={{ disabled: busy }}
          style={({ pressed }) => [s.cancel, pressed && s.pressed]}
        >
          <Text style={s.cancelText}>{t("settings.cancel")}</Text>
        </Pressable>
      </View>
    </Sheet>
  );
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    sheet: {
      backgroundColor: theme.surfaceAlt,
      borderTopLeftRadius: Radius.sheet,
      borderTopRightRadius: Radius.sheet,
    },
    body: { paddingHorizontal: Space.gutter, paddingTop: Space.xl, paddingBottom: Space.lg },
    nameField: {
      marginTop: Space.xl,
      borderWidth: 1.5,
      borderColor: theme.border,
      borderRadius: Radius.full,
      minHeight: 72,
      justifyContent: "center",
    },
    nameLabel: {
      ...Type.body,
      color: theme.textSecondary,
      position: "absolute",
      top: -14,
      left: Space.md,
      paddingHorizontal: Space.xs,
      backgroundColor: theme.surfaceAlt,
    },
    nameInput: {
      ...Type.h1,
      ...Weight.regular,
      color: theme.text,
      paddingHorizontal: Space.lg,
      paddingVertical: Space.md,
    },
    error: { ...Type.secondary, color: theme.danger, marginTop: Space.md, textAlign: "center" },
    save: {
      alignSelf: "center",
      marginTop: Space.xl,
      minWidth: 180,
      minHeight: 64,
      paddingHorizontal: Space.lg,
      paddingVertical: Space.md,
      borderRadius: Radius.full,
      backgroundColor: theme.text,
      alignItems: "center",
      justifyContent: "center",
    },
    saveText: { ...Type.h1, color: theme.bg },
    removePhoto: { alignSelf: "center", marginTop: Space.sm, minHeight: 44, justifyContent: "center", paddingHorizontal: Space.lg },
    removePhotoText: { ...Type.body, color: theme.danger },
    cancel: { alignSelf: "center", marginTop: Space.sm, minHeight: 48, justifyContent: "center", paddingHorizontal: Space.lg },
    cancelText: { ...Type.body, ...Weight.semibold, color: theme.text },
    pressed: { opacity: 0.65 },
    disabled: { opacity: 0.55 },
  });
}
