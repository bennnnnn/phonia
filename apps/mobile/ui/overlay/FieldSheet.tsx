/**
 * Bottom-sheet editor for one text value: a profile field, custom instructions, a
 * memory. Matches ChatRenameSheet Sheet pattern.
 */
import { useMemo } from "react";
import {
  InputAccessoryView,
  Platform,
  StyleSheet,
  Text,
  View,
  type KeyboardTypeOptions,
} from "react-native";
import { useTranslation } from "react-i18next";

import { Sheet } from "@/ui/overlay/Sheet";
import { SheetFormHeader } from "@/ui/overlay/SheetFormHeader";
import { TextField } from "@/ui/controls/TextField";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { Theme, useTheme } from "@/lib/theme";
import { Type } from "@/lib/type";

const EMPTY_NUMBER_PAD_ACCESSORY_ID = "settings-field-empty-accessory";

type Props = {
  visible: boolean;
  title: string;
  value: string;
  onChangeText: (text: string) => void;
  onClose: () => void;
  onSave: () => void;
  hint?: string;
  placeholder?: string;
  maxLength?: number;
  multiline?: boolean;
  keyboardType?: KeyboardTypeOptions;
  saving?: boolean;
};

export function FieldSheet({
  visible,
  title,
  value,
  onChangeText,
  onClose,
  onSave,
  hint,
  placeholder,
  maxLength,
  multiline = false,
  keyboardType = "default",
  saving = false,
}: Props) {
  const theme = useTheme();
  const { t } = useTranslation();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const numberPad =
    keyboardType === "number-pad" || keyboardType === "decimal-pad";
  // iOS number-pad has no Return key, so RN mounts a floating Done accessory
  // that duplicates this sheet's Save. An empty accessory replaces it.
  const hideNumberPadDone = Platform.OS === "ios" && numberPad;

  return (
    <>
      {hideNumberPadDone && visible ? (
        <InputAccessoryView nativeID={EMPTY_NUMBER_PAD_ACCESSORY_ID}>
          <View />
        </InputAccessoryView>
      ) : null}
    <Sheet
      visible={visible}
      onClose={() => {
        if (!saving) onClose();
      }}
      variant="bottom"
      keyboardAvoiding
      withHandle={false}
      contentContainerStyle={s.sheet}
    >
      <SheetFormHeader
        title={title}
        onCancel={() => {
          if (!saving) onClose();
        }}
        onSave={onSave}
        cancelLabel={t("settings.cancel")}
        saveLabel={t("settings.save")}
        saving={saving}
      />
      <View style={s.body}>
        {hint ? <Text style={s.hint}>{hint}</Text> : null}
        <TextField
          value={value}
          onChangeText={onChangeText}
          autoFocus
          returnKeyType={multiline || numberPad ? "default" : "done"}
          onSubmitEditing={multiline || numberPad ? undefined : onSave}
          inputAccessoryViewID={
            hideNumberPadDone ? EMPTY_NUMBER_PAD_ACCESSORY_ID : undefined
          }
          maxLength={maxLength}
          placeholder={placeholder}
          keyboardType={keyboardType}
          multiline={multiline}
          editable={!saving}
        />
      </View>
    </Sheet>
    </>
  );
}

function makeStyles(C: Theme) {
  return StyleSheet.create({
    sheet: {
      paddingHorizontal: 0,
      paddingTop: 0,
      backgroundColor: C.bg,
      borderTopLeftRadius: Radius.sheet,
      borderTopRightRadius: Radius.sheet,
    },
    body: { padding: Space.md, gap: Space.sm },
    hint: { ...Type.secondary, color: C.textSecondary },
  });
}
