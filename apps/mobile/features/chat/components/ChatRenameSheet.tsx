import { StyleSheet, View } from "react-native";
import { useTranslation } from "react-i18next";

import { Sheet } from "@/ui/overlay/Sheet";
import { SheetFormHeader } from "@/ui/overlay/SheetFormHeader";
import { TextField } from "@/ui/controls/TextField";
import { Space } from "@/lib/space";

type Props = {
  visible: boolean;
  value: string;
  onChangeText: (text: string) => void;
  onClose: () => void;
  onSave: () => void;
};

export function ChatRenameSheet({
  visible,
  value,
  onChangeText,
  onClose,
  onSave,
}: Props) {
  const { t } = useTranslation();

  return (
    <Sheet
      visible={visible}
      onClose={onClose}
      variant="bottom"
      keyboardAvoiding
      withHandle={false}
      contentContainerStyle={s.sheet}
    >
      <SheetFormHeader
        title={t("chat.rename_title")}
        onCancel={onClose}
        onSave={onSave}
        cancelLabel={t("common.cancel")}
        saveLabel={t("settings.save")}
      />
      <View style={s.body}>
        <TextField
          value={value}
          onChangeText={onChangeText}
          autoFocus
          returnKeyType="done"
          onSubmitEditing={onSave}
          maxLength={80}
        />
      </View>
    </Sheet>
  );
}

const s = StyleSheet.create({
  sheet: {
    paddingHorizontal: 0,
    paddingTop: 0,
  },
  body: { padding: Space.md },
});
