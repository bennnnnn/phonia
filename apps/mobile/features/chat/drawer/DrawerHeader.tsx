import { Pressable, Text, TextInput, View } from "react-native";
import { useTranslation } from "react-i18next";

import { Icon } from "@/ui/icons/Icon";
import { SearchField } from "@/ui/controls/SearchField";
import { tap } from "@/lib/haptics";
import { IconSize } from "@/ui/icons/sizes";
import type { Theme } from "@/lib/theme";

import type { ConversationListStyles } from "./conversationListStyles";

type Props = {
  styles: ConversationListStyles;
  theme: Theme;
  paddingTop: number;
  searchOpen: boolean;
  searchQuery: string;
  searchInputRef: React.RefObject<TextInput | null>;
  onSearchChange: (text: string) => void;
  onOpenSearch: () => void;
  onCloseSearch: () => void;
  selectionMode?: boolean;
  selectedCount?: number;
  onExitSelection?: () => void;
  onSelectAll?: () => void;
};

export function DrawerHeader({
  styles: s,
  theme,
  paddingTop,
  searchOpen,
  searchQuery,
  searchInputRef,
  onSearchChange,
  onOpenSearch,
  onCloseSearch,
  selectionMode = false,
  selectedCount = 0,
  onExitSelection,
  onSelectAll,
}: Props) {
  const { t } = useTranslation();

  return (
    <View style={[s.topOverlay, { paddingTop }]} pointerEvents="box-none">
      <View style={s.header}>
        {searchOpen ? (
          <SearchField
            inputRef={searchInputRef}
            value={searchQuery}
            onChangeText={onSearchChange}
            placeholder={t("search.placeholder")}
            clearButtonMode="while-editing"
            trailing={
              <Pressable
                hitSlop={{ top: 13, bottom: 13, left: 8, right: 8 }}
                onPress={() => {
                  tap();
                  onCloseSearch();
                }}
                style={s.searchCancel}
                accessibilityRole="button"
                accessibilityLabel={t("common.cancel")}
              >
                <Text style={s.searchCancelText}>{t("common.cancel")}</Text>
              </Pressable>
            }
          />
        ) : selectionMode ? (
          <View style={s.selectionHeader}>
            <Pressable
              hitSlop={11}
              onPress={() => {
                tap();
                onExitSelection?.();
              }}
              style={s.selectionHeaderAction}
              accessibilityRole="button"
              accessibilityLabel={t("common.cancel")}
            >
              <Text style={s.selectionHeaderActionText}>{t("common.cancel")}</Text>
            </Pressable>
            <Text style={s.selectionHeaderTitle}>
              {t("drawer.selected_count", { count: selectedCount })}
            </Text>
            <Pressable
              hitSlop={11}
              onPress={() => {
                tap();
                onSelectAll?.();
              }}
              style={s.selectionHeaderAction}
              accessibilityRole="button"
              accessibilityLabel={t("drawer.select_all")}
            >
              <Text style={s.selectionHeaderActionText}>{t("drawer.select_all")}</Text>
            </Pressable>
          </View>
        ) : (
          <View style={s.logo}>
            <Text style={s.logoText}>{t("app.name")}</Text>
            <View style={s.headerActions}>
              <Pressable
                hitSlop={8}
                style={s.searchBtn}
                onPress={() => {
                  tap();
                  onOpenSearch();
                }}
                accessibilityRole="button"
                accessibilityLabel={t("search.open_accessibility")}
              >
                <Icon name="search" size={IconSize.sm} color={theme.text} />
              </Pressable>
            </View>
          </View>
        )}
      </View>
    </View>
  );
}
