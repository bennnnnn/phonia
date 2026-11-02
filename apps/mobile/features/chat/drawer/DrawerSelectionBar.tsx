import { Pressable, Text, View } from "react-native";
import { useTranslation } from "react-i18next";

import { Icon } from "@/ui/icons/Icon";
import type { Theme } from "@/lib/theme";
import type { ConversationListStyles } from "./conversationListStyles";
import { IconSize } from "@/ui/icons/sizes";

type Props = {
  styles: ConversationListStyles;
  theme: Theme;
  paddingBottom: number;
  selectedCount: number;
  archivableCount: number;
  onArchive: () => void;
  onDelete: () => void;
};

export function DrawerSelectionBar({
  styles: s,
  theme,
  paddingBottom,
  selectedCount,
  archivableCount,
  onArchive,
  onDelete,
}: Props) {
  const { t } = useTranslation();
  const disabled = selectedCount === 0;
  const archiveDisabled = disabled || archivableCount === 0;

  return (
    <View style={[s.selectionBar, { paddingBottom }]} pointerEvents="box-none">
      <Pressable
        style={[s.selectionAction, archiveDisabled && s.selectionActionDisabled]}
        disabled={archiveDisabled}
        onPress={onArchive}
        accessibilityRole="button"
      >
        <Icon
          name="archive"
          size={IconSize.sm}
          color={archiveDisabled ? theme.textTertiary : theme.primary}
        />
        <Text style={[s.selectionActionText, archiveDisabled && s.selectionActionTextDisabled]}>
          {t("drawer.bulk_archive")}
        </Text>
      </Pressable>
      <Pressable
        style={[s.selectionAction, disabled && s.selectionActionDisabled]}
        disabled={disabled}
        onPress={onDelete}
        accessibilityRole="button"
      >
        <Icon
          name="trash"
          size={IconSize.sm}
          color={disabled ? theme.textTertiary : theme.danger}
        />
        <Text
          style={[
            s.selectionActionText,
            s.selectionActionTextDanger,
            disabled && s.selectionActionTextDisabled,
          ]}
        >
          {t("drawer.bulk_delete")}
        </Text>
      </Pressable>
    </View>
  );
}
