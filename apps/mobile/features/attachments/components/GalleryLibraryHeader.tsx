import { ScrollView, StyleSheet, View } from "react-native";
import { useTranslation } from "react-i18next";

import { IconButton } from "@/ui/controls/IconButton";
import { SearchField } from "@/ui/controls/SearchField";
import { type GalleryFilter } from "@/features/attachments/model/gallery";
import { type GalleryLayout } from "@/features/attachments/model/galleryLayout";
import { Space } from "@/lib/space";
import { useTheme } from "@/lib/theme";
import { IconSize } from "@/ui/icons/sizes";
import { Chip } from "@/ui/controls/Chip";

type Props = {
  filter: GalleryFilter;
  searchQuery: string;
  layout: GalleryLayout;
  onSearchChange: (query: string) => void;
  onFilterChange: (filter: GalleryFilter) => void;
  onToggleLayout: () => void;
};

export function GalleryLibraryHeader({
  filter,
  searchQuery,
  layout,
  onSearchChange,
  onFilterChange,
  onToggleLayout,
}: Props) {
  const { t } = useTranslation();
  const C = useTheme();
  const filters: { key: GalleryFilter; label: string }[] = [
    { key: "all", label: t("gallery.filter.all") },
    { key: "generated", label: t("gallery.filter.generated") },
    { key: "uploaded", label: t("gallery.filter.uploaded") },
    { key: "files", label: t("gallery.filter.files") },
  ];

  return (
    <View style={s.header}>
      <SearchField
        style={s.searchField}
        value={searchQuery}
        onChangeText={onSearchChange}
        placeholder={t("gallery.search_placeholder")}
        onClear={() => onSearchChange("")}
        clearAccessibilityLabel={t("gallery.search_clear_a11y")}
        clearTestID="gallery-search-clear"
      />
      {/* One line in every language: the chips scroll, the layout toggle stays put. */}
      <View style={s.tabsRow}>
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          style={s.tabsScroll}
          contentContainerStyle={s.tabs}
          accessibilityRole="radiogroup"
        >
          {filters.map((tab) => (
            <Chip
              key={tab.key}
              variant="filter"
              accessibilityRole="radio"
              label={tab.label}
              selected={tab.key === filter}
              onPress={() => onFilterChange(tab.key)}
            />
          ))}
        </ScrollView>
        <IconButton
          name={layout === "grid" ? "list" : "grid"}
          size={IconSize.md}
          color={C.textSecondary}
          onPress={onToggleLayout}
          accessibilityLabel={
            layout === "grid"
              ? t("gallery.layout_column_a11y")
              : t("gallery.layout_grid_a11y")
          }
          testID="gallery-layout-toggle"
        />
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  header: {
    paddingHorizontal: Space.md,
    paddingTop: Space.sm,
    paddingBottom: Space.sm,
  },
  searchField: { marginBottom: Space.sm },
  tabsRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: Space.xxs,
    minHeight: Space.minTouch,
  },
  tabsScroll: { flex: 1 },
  tabs: {
    flexDirection: "row",
    alignItems: "center",
    gap: Space.xs,
  },
});
