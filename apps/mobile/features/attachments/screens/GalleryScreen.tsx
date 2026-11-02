import { useCallback, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
  type AccessibilityActionEvent,
  type AccessibilityActionInfo,
  type GestureResponderEvent,
} from "react-native";
import { FlashList } from "@shopify/flash-list";
import { useTranslation } from "react-i18next";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import {
  GALLERY_COLUMN_SEPARATOR_INSET,
  GalleryColumnRow,
} from "@/features/attachments/components/GalleryColumnRow";
import { GalleryLibraryHeader } from "@/features/attachments/components/GalleryLibraryHeader";
import { GalleryMediaModals } from "@/features/attachments/components/GalleryMediaModals";
import { GalleryThumbnail } from "@/features/attachments/components/GalleryThumbnail";
import { useActionFeedbackOptional } from "@/contexts/actionFeedbackCore";
import { Icon } from "@/ui/icons/Icon";
import { ListSeparator } from "@/ui/list/ListGroup";
import { SkeletonGrid, SkeletonList } from "@/ui/feedback/SkeletonLoader";
import { StateView } from "@/ui/feedback/StateView";
import { useGalleryData } from "@/features/attachments/hooks/useGalleryData";
import { useGalleryLibrary } from "@/features/attachments/hooks/useGalleryLibrary";
import { type AttachmentListItem } from "@/lib/api";
import {
  GALLERY_GRID_COLUMNS,
  galleryDisplayName,
  galleryEmptyKey,
  galleryGridLayout,
  galleryItemActions,
  galleryPressAction,
  type GalleryFilter,
  type GalleryItemAction,
} from "@/features/attachments/model/gallery";
import { reportRecoverableError } from "@/lib/reportRecoverableError";
import { Space } from "@/lib/space";
import { Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";
import { Radius } from "@/lib/radius";
import { IconSize } from "@/ui/icons/sizes";

/** One gap between grid tiles, across and down. */
const GRID_GAP = Space.xs;

export default function GalleryScreen() {
  const { t } = useTranslation();
  const C = useTheme();
  const s = useMemo(() => makeStyles(C), [C]);
  const insets = useSafeAreaInsets();
  const feedback = useActionFeedbackOptional();
  const { width } = useWindowDimensions();
  const grid = galleryGridLayout(width, Space.md, GRID_GAP);
  const thumbSize = grid.thumbSize;

  const [filter, setFilter] = useState<GalleryFilter>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const {
    items,
    loading,
    loadingMore,
    error,
    pageError,
    retryPage,
    pullRefreshing,
    refresh,
    loadMore,
    retry,
    removeItem,
  } = useGalleryData(filter, searchQuery);
  const library = useGalleryLibrary(items, removeItem);
  const {
    layout,
    busyItemId,
    attachToComposer,
    openImage,
    openFile,
    openActions,
    openChat,
    shareFile,
    confirmDelete,
  } = library;
  const isGrid = layout === "grid";

  const onRefresh = useCallback(() => {
    void refresh().then((ok) => {
      // With items on screen the failure would only show in the list footer.
      if (!ok && items.length > 0) reportRecoverableError(feedback, t("gallery.refresh_failed"));
    });
  }, [refresh, items.length, feedback, t]);

  const actionLabels = useMemo<Record<GalleryItemAction, string>>(
    () => ({
      use: t("gallery.use_in_chat"),
      open_chat: t("gallery.open_chat"),
      share: t("gallery.share"),
      delete: t("common.delete"),
    }),
    [t],
  );

  const renderItem = useCallback(
    ({ item }: { item: AttachmentListItem }) => {
      const name = galleryDisplayName(item);
      const isImage = galleryPressAction(item.content_type) === "view-image";
      const busy = busyItemId === item.id;
      const onPress = () => {
        if (isImage) openImage(item);
        else void openFile(item);
      };
      const onLongPress = (point: { x: number; y: number }) => openActions(item, point);
      const hint = isImage ? t("chat.image_view_a11y") : t("gallery.open_file_a11y");
      // The long-press menu, for screen readers.
      const accessibilityActions: AccessibilityActionInfo[] = galleryItemActions(item).map((action) => ({
        name: action,
        label: actionLabels[action],
      }));
      const onAccessibilityAction = (event: AccessibilityActionEvent) => {
        const action = event.nativeEvent.actionName as GalleryItemAction;
        if (action === "use") void attachToComposer(item);
        else if (action === "open_chat") openChat(item);
        else if (action === "share") void shareFile(item);
        else if (action === "delete") confirmDelete(item);
      };

      if (!isGrid) {
        return (
          <GalleryColumnRow
            item={item}
            title={name}
            busy={busy}
            onPress={onPress}
            onLongPress={onLongPress}
            onMissing={removeItem}
            accessibilityHint={hint}
            accessibilityActions={accessibilityActions}
            onAccessibilityAction={onAccessibilityAction}
          />
        );
      }
      return (
        <View style={s.cell}>
          <Pressable
            onPress={onPress}
            onLongPress={(event: GestureResponderEvent) =>
              onLongPress({ x: event.nativeEvent.pageX, y: event.nativeEvent.pageY })
            }
            disabled={busy}
            accessibilityRole="button"
            accessibilityLabel={name}
            accessibilityHint={hint}
            accessibilityState={{ busy, disabled: busy }}
            accessibilityActions={accessibilityActions}
            onAccessibilityAction={onAccessibilityAction}
            style={({ pressed }) => pressed && s.tilePressed}
          >
            {isImage ? (
              <GalleryThumbnail
                attachmentId={item.id}
                downloadUrl={item.download_url}
                size={thumbSize}
                onMissing={removeItem}
              />
            ) : (
              <View style={[s.fileTile, { width: thumbSize, height: thumbSize }]}>
                <Icon name="file" size={IconSize.xl} color={C.textTertiary} />
                <Text style={s.fileLabel} numberOfLines={1} ellipsizeMode="middle">
                  {name}
                </Text>
              </View>
            )}
            {busy ? (
              <View style={[s.busy, { width: thumbSize, height: thumbSize }]} testID="gallery-item-busy">
                <ActivityIndicator color={C.onMedia} />
              </View>
            ) : null}
          </Pressable>
        </View>
      );
    },
    [
      t,
      s,
      C,
      thumbSize,
      isGrid,
      busyItemId,
      actionLabels,
      attachToComposer,
      openImage,
      openFile,
      openActions,
      openChat,
      shareFile,
      confirmDelete,
      removeItem,
    ],
  );

  const listPadding = isGrid ? grid.listPadding : 0;

  return (
    <View style={s.root}>
      <GalleryLibraryHeader
        filter={filter}
        searchQuery={searchQuery}
        layout={layout}
        onSearchChange={setSearchQuery}
        onFilterChange={(next) => {
          library.setViewerId(null);
          library.setFileItem(null);
          setFilter(next);
        }}
        onToggleLayout={library.toggleLayout}
      />

      {loading && items.length === 0 && !error ? (
        isGrid ? (
          <SkeletonGrid
            columns={GALLERY_GRID_COLUMNS}
            size={thumbSize}
            cellPadding={grid.cellPadding}
            padding={grid.listPadding}
            radius={Radius.sm}
          />
        ) : (
          <SkeletonList />
        )
      ) : error && items.length === 0 ? (
        <StateView
          variant="error"
          title={t("common.error")}
          onRetry={() => void retry({ reset: true })}
          retryLabel={t("common.retry")}
        />
      ) : (
        <FlashList
          key={layout}
          data={items}
          keyExtractor={(item) => item.id}
          numColumns={isGrid ? GALLERY_GRID_COLUMNS : 1}
          extraData={busyItemId}
          contentContainerStyle={{
            paddingHorizontal: listPadding,
            paddingBottom: insets.bottom + Space.xl,
          }}
          ItemSeparatorComponent={isGrid ? undefined : ColumnSeparator}
          refreshControl={
            <RefreshControl
              refreshing={pullRefreshing}
              onRefresh={onRefresh}
              tintColor={C.primary}
            />
          }
          onEndReached={loadMore}
          onEndReachedThreshold={0.5}
          ListFooterComponent={
            loadingMore ? (
              <View style={s.footer}>
                <ActivityIndicator color={C.textTertiary} />
              </View>
            ) : pageError ? (
              <StateView variant="error" title={t("common.error")}
                onRetry={() => void retryPage()} retryLabel={t("common.retry")} />
            ) : null
          }
          ListEmptyComponent={
            <StateView
              variant="empty"
              icon="image"
              title={t(galleryEmptyKey(filter, searchQuery))}
              message={
                searchQuery.trim()
                  ? undefined
                  : t("gallery.empty_hint")
              }
            />
          }
          renderItem={renderItem}
        />
      )}

      <GalleryMediaModals items={items} library={library} onLoadMore={loadMore} />
    </View>
  );
}

function ColumnSeparator() {
  return <ListSeparator appearance="plain" inset={GALLERY_COLUMN_SEPARATOR_INSET} />;
}

function makeStyles(C: Theme) {
  return StyleSheet.create({
    root: { flex: 1, backgroundColor: C.bg },
    // Half the gap around every tile: equal gaps across and down.
    cell: {
      padding: GRID_GAP / 2,
      alignItems: "center",
    },
    tilePressed: { opacity: 0.7 },
    footer: {
      paddingVertical: Space.md,
      alignItems: "center",
    },
    fileTile: {
      borderRadius: Radius.sm,
      backgroundColor: C.surfaceAlt,
      borderWidth: 1,
      borderColor: C.border,
      alignItems: "center",
      justifyContent: "center",
      gap: Space.xs,
      paddingHorizontal: Space.xs,
    },
    fileLabel: {
      ...Type.overline,
      ...Weight.semibold,
      color: C.textTertiary,
    },
    busy: {
      position: "absolute",
      top: 0,
      left: 0,
      borderRadius: Radius.sm,
      backgroundColor: C.scrim,
      alignItems: "center",
      justifyContent: "center",
    },
  });
}

/** Its route's error view: a crash here leaves the rest of the app working. */
export { ScreenErrorBoundary as ErrorBoundary } from "@/components/ScreenErrorBoundary";
