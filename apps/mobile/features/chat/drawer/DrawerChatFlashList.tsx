import { useCallback, useMemo } from "react";
import { Pressable, RefreshControl, Text } from "react-native";
import { FlashList } from "@shopify/flash-list";
import { useTranslation } from "react-i18next";

import { Icon } from "@/ui/icons/Icon";
import { StateView } from "@/ui/feedback/StateView";
import {
  ConversationRow,
  makeConversationRowStyles,
} from "@/features/chat/drawer/ConversationRow";
import {
  DrawerSearchLoadMore,
  DrawerSearchResultRow,
} from "@/features/search/components/DrawerSearchResults";
import { makeConversationListStyles } from "@/features/chat/drawer/conversationListStyles";
import {
  ARCHIVED_CHAT_SECTION,
  CHAT_DATE_SECTIONS,
  drawerSectionTitleKey,
  isCollapsibleChatSection,
  PINNED_CHAT_SECTION,
  type ChatListSectionKey,
} from "@/features/chat/model/listSections";
import { isChatTitleGenerating } from "@/features/chat/drawer/drawer";
import { displayChatTitle } from "@/features/chat/model/title";
import { Chat, ChatList, type SearchResult } from "@/lib/api";
import { useTheme } from "@/lib/theme";
import { IconSize } from "@/ui/icons/sizes";

export type DrawerChatListItem =
  | {
      type: "sectionHeader";
      key: ChatListSectionKey;
      title: string;
      count: number;
      collapsible: boolean;
    }
  | { type: "row"; key: string; chat: Chat }
  | { type: "searchRow"; key: string; result: SearchResult; onOpen: (id: string, messageId?: string | null) => void }
  | {
      type: "searchLoadMore";
      key: "search-load-more";
      loadingMore: boolean;
      loadingMoreError: boolean;
      onLoadMore?: () => void;
    }
  | { type: "archivedMore"; key: "archived-more" };

const NO_ITEMS: DrawerChatListItem[] = [];

type Props = {
  groups: ChatList;
  activeChatCount: number;
  loading: boolean;
  error: boolean;
  isSectionCollapsed: (key: ChatListSectionKey) => boolean;
  toggleSectionCollapsed: (key: ChatListSectionKey) => void;
  highlightedIds?: Set<string>;
  /** Chat currently open on the home screen (drawer active indicator). */
  activeChatId?: string | null;
  onOpenChat: (id: string, messageId?: string | null) => void;
  onOpenSearchResult: (id: string, messageId?: string | null) => void;
  onShowRowMenu: (chat: Chat, point: { x: number; y: number }) => void;
  selectionMode?: boolean;
  selectedIds?: ReadonlySet<string>;
  onToggleSelect?: (chatId: string) => void;
  listHeader: React.ReactElement;
  contentPaddingTop: number;
  contentPaddingBottom: number;
  refreshing: boolean;
  onRefresh: () => void;
  searchOpen?: boolean;
  searchResults?: SearchResult[];
  searchHasMore?: boolean;
  searchLoadingMore?: boolean;
  searchLoadingMoreError?: boolean;
  onSearchLoadMore?: () => void;
  /** Read the next page of older chats; omitted when the list holds them all. */
  onLoadOlderChats?: () => void;
  /** Read more archived chats; omitted when the archived section holds them all. */
  onLoadMoreArchived?: () => void;
  archivedPaging?: "idle" | "loading" | "failed";
};

export function DrawerChatFlashList({
  groups,
  activeChatCount,
  loading,
  error,
  isSectionCollapsed,
  toggleSectionCollapsed,
  highlightedIds,
  activeChatId = null,
  onOpenChat,
  onOpenSearchResult,
  onShowRowMenu,
  selectionMode = false,
  selectedIds,
  onToggleSelect,
  listHeader,
  contentPaddingTop,
  contentPaddingBottom,
  refreshing,
  onRefresh,
  searchOpen = false,
  searchResults = [],
  searchHasMore = false,
  searchLoadingMore = false,
  searchLoadingMoreError = false,
  onSearchLoadMore,
  onLoadOlderChats,
  onLoadMoreArchived,
  archivedPaging = "idle",
}: Props) {
  const { t } = useTranslation();
  const theme = useTheme();
  const s = useMemo(() => makeConversationListStyles(theme), [theme]);
  const rowStyles = useMemo(() => makeConversationRowStyles(theme), [theme]);

  // Each keystroke starts a new search with new result handlers. They ride on the search
  // items, so the chat rows under them keep their items and renderItem and are not redrawn.
  const searchItems = useMemo<DrawerChatListItem[]>(() => {
    if (!searchOpen || searchResults.length === 0) return NO_ITEMS;
    const items: DrawerChatListItem[] = [];
    for (const result of searchResults) {
      const key = result.message_id
        ? `search-${result.message_id}`
        : `search-title-${result.chat_id}`;
      items.push({ type: "searchRow", key, result, onOpen: onOpenSearchResult });
    }
    if (searchHasMore || searchLoadingMoreError) {
      items.push({
        type: "searchLoadMore",
        key: "search-load-more",
        loadingMore: searchLoadingMore,
        loadingMoreError: searchLoadingMoreError,
        onLoadMore: onSearchLoadMore,
      });
    }
    return items;
  }, [
    onOpenSearchResult,
    onSearchLoadMore,
    searchHasMore,
    searchLoadingMore,
    searchLoadingMoreError,
    searchOpen,
    searchResults,
  ]);

  const chatItems = useMemo<DrawerChatListItem[]>(() => {
    const items: DrawerChatListItem[] = [];
    if (activeChatCount === 0 && groups.archived.length === 0) return items;

    const sections: { key: ChatListSectionKey; chats: Chat[] }[] = [
      { key: PINNED_CHAT_SECTION, chats: groups.pinned },
      ...CHAT_DATE_SECTIONS.map((key) => ({ key, chats: groups[key] })),
      { key: ARCHIVED_CHAT_SECTION, chats: groups.archived },
    ];

    for (const section of sections) {
      if (section.chats.length === 0) continue;
      items.push({
        type: "sectionHeader",
        key: section.key,
        title: t(drawerSectionTitleKey(section.key)),
        count: section.chats.length,
        collapsible: isCollapsibleChatSection(section.key),
      });
      if (isSectionCollapsed(section.key)) continue;
      for (const chat of section.chats) {
        items.push({ type: "row", key: chat.id, chat });
      }
      if (section.key === ARCHIVED_CHAT_SECTION && onLoadMoreArchived) {
        items.push({ type: "archivedMore", key: "archived-more" });
      }
    }
    return items;
  }, [activeChatCount, groups, isSectionCollapsed, onLoadMoreArchived, t]);

  const chatListData = useMemo(
    () => (searchItems.length > 0 ? [...searchItems, ...chatItems] : chatItems),
    [searchItems, chatItems],
  );

  const renderChatItem = useCallback(
    ({ item }: { item: DrawerChatListItem }) => {
      if (item.type === "searchRow") {
        return (
          <DrawerSearchResultRow
            result={item.result}
            title={displayChatTitle(item.result.chat_title, {}, t)}
            onOpenChat={item.onOpen}
          />
        );
      }
      if (item.type === "searchLoadMore") {
        return (
          <DrawerSearchLoadMore
            loadingMore={item.loadingMore}
            loadingMoreError={item.loadingMoreError}
            onLoadMore={item.onLoadMore}
          />
        );
      }
      if (item.type === "archivedMore") {
        return (
          <DrawerSearchLoadMore
            label={t("drawer.archived_show_more")}
            loadingMore={archivedPaging === "loading"}
            loadingMoreError={archivedPaging === "failed"}
            onLoadMore={onLoadMoreArchived}
          />
        );
      }
      if (item.type === "sectionHeader") {
        if (!item.collapsible) {
          return (
            <Text style={[s.sectionTitle, s.section]} accessibilityRole="header">{item.title}</Text>
          );
        }
        const collapsed = isSectionCollapsed(item.key);
        return (
          <Pressable
            style={[s.sectionHeader, s.section]}
            onPress={() => toggleSectionCollapsed(item.key)}
            accessibilityRole="button"
            accessibilityState={{ expanded: !collapsed }}
          >
            <Text style={s.sectionTitle}>{item.title}</Text>
            <Text style={s.sectionCount}>{item.count}</Text>
            <Icon
              name={collapsed ? "chevron-down" : "chevron-up"}
              size={IconSize.xs}
              color={theme.textTertiary}
            />
          </Pressable>
        );
      }
      return (
        <ConversationRow
          chat={item.chat}
          rowStyles={rowStyles}
          highlighted={highlightedIds?.has(item.chat.id) ?? false}
          active={activeChatId != null && item.chat.id === activeChatId}
          titleGenerating={isChatTitleGenerating(item.chat.id)}
          onOpen={onOpenChat}
          onLongPress={onShowRowMenu}
          selectionMode={selectionMode}
          selected={selectedIds?.has(item.chat.id) ?? false}
          onToggleSelect={selectionMode ? onToggleSelect : undefined}
        />
      );
    },
    [
      s,
      rowStyles,
      highlightedIds,
      activeChatId,
      isSectionCollapsed,
      toggleSectionCollapsed,
      theme,
      onOpenChat,
      onShowRowMenu,
      selectionMode,
      selectedIds,
      onToggleSelect,
      archivedPaging,
      onLoadMoreArchived,
      t,
    ],
  );

  const listEmpty =
    !searchOpen && activeChatCount === 0 && !loading && !error ? (
      <StateView variant="empty" compact message={t("drawer.no_conversations")} />
    ) : null;

  const contentContainerStyle = useMemo(
    () => ({
      paddingTop: contentPaddingTop,
      paddingBottom: contentPaddingBottom,
    }),
    [contentPaddingTop, contentPaddingBottom],
  );

  const refreshControl = useMemo(
    () => (
      <RefreshControl
        refreshing={refreshing}
        onRefresh={onRefresh}
        colors={[theme.primary]}
        tintColor={theme.primary}
      />
    ),
    [refreshing, onRefresh, theme.primary],
  );

  return (
    <FlashList
      style={s.list}
      data={chatListData}
      renderItem={renderChatItem}
      keyExtractor={(item) =>
        item.type === "sectionHeader" ? `section-${item.key}` : item.key
      }
      getItemType={(item) => item.type}
      showsVerticalScrollIndicator={false}
      contentContainerStyle={contentContainerStyle}
      keyboardShouldPersistTaps="handled"
      ListHeaderComponent={listHeader}
      ListEmptyComponent={listEmpty}
      refreshControl={refreshControl}
      onEndReached={searchOpen ? undefined : onLoadOlderChats}
      onEndReachedThreshold={0.5}
    />
  );
}
