import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";
import { useTranslation } from "react-i18next";

import { Icon } from "@/ui/icons/Icon";
import { SkeletonList } from "@/ui/feedback/SkeletonLoader";
import { StateView } from "@/ui/feedback/StateView";
import { Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";
import type { SearchResult } from "@/lib/api";
import { Space } from "@/lib/space";
import { IconSize } from "@/ui/icons/sizes";

type ChromeProps = {
  hasSearchQuery: boolean;
  searchLoading: boolean;
  searchError: boolean;
  resultCount: number;
  onRetry: () => void;
};

/** Section title + non-row states for drawer search (rows live in FlashList data). */
export function DrawerSearchResultsChrome({
  hasSearchQuery,
  searchLoading,
  searchError,
  resultCount,
  onRetry,
}: ChromeProps) {
  const { t } = useTranslation();
  const theme = useTheme();
  const s = makeStyles(theme);

  return (
    <View style={s.section}>
      <Text style={s.sectionTitle} accessibilityRole="header">{t("search.results")}</Text>
      {!hasSearchQuery ? (
        <Text style={s.searchHint}>{t("search.empty")}</Text>
      ) : searchLoading ? (
        <SkeletonList count={3} />
      ) : searchError ? (
        <StateView variant="error" compact message={t("common.error")} onRetry={onRetry} />
      ) : resultCount === 0 ? (
        <StateView variant="empty" compact message={t("search.no_results")} />
      ) : null}
    </View>
  );
}

type RowProps = {
  result: SearchResult;
  /** The chat's title as the drawer shows it (the chat feature owns how titles read). */
  title: string;
  onOpenChat: (chatId: string, messageId?: string | null) => void;
};

export function DrawerSearchResultRow({ result, title, onOpenChat }: RowProps) {
  const { t } = useTranslation();
  const theme = useTheme();
  const s = makeStyles(theme);

  return (
    <Pressable
      style={s.searchResult}
      accessibilityRole="button"
      onPress={() => onOpenChat(result.chat_id, result.message_id)}
    >
      <View style={s.searchResultHeader}>
        <Icon
          name={
            result.match_type === "title"
              ? "message"
              : result.role === "user"
                ? "user"
                : "sparkles"
          }
          size={IconSize.xxs}
          color={result.match_type === "title" ? theme.primary : theme.textSecondary}
        />
        <Text style={s.searchResultTitle} numberOfLines={1}>
          {title}
        </Text>
        {result.match_type === "title" ? (
          <Text style={s.searchResultBadge}>{t("search.topic_match")}</Text>
        ) : null}
        {result.archived ? (
          <Text style={s.searchResultBadge}>{t("search.archived_tag")}</Text>
        ) : null}
      </View>
      <Text style={s.searchResultSnippet} numberOfLines={2}>
        {result.content}
      </Text>
    </Pressable>
  );
}

type LoadMoreProps = {
  /** What the row says; search results by default. */
  label?: string;
  loadingMore?: boolean;
  loadingMoreError?: boolean;
  onLoadMore?: () => void;
};

export function DrawerSearchLoadMore({ label, loadingMore, loadingMoreError, onLoadMore }: LoadMoreProps) {
  const { t } = useTranslation();
  const theme = useTheme();
  const s = makeStyles(theme);
  const text = label ?? t("search.load_more");

  if (loadingMoreError && !loadingMore) {
    return <StateView variant="error" compact message={t("common.error")} onRetry={onLoadMore} />;
  }

  return (
    <Pressable
      style={s.loadMore}
      onPress={onLoadMore}
      disabled={loadingMore}
      accessibilityRole="button"
      accessibilityLabel={text}
    >
      {loadingMore ? (
        <ActivityIndicator size="small" color={theme.primary} />
      ) : (
        <Text style={s.loadMoreText}>{text}</Text>
      )}
    </Pressable>
  );
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    section: { marginBottom: Space.xs },
    sectionTitle: {
      ...Type.overline,
      color: theme.textTertiary,
      paddingHorizontal: Space.md,
      paddingTop: Space.sm,
      paddingBottom: Space.xs,
    },
    searchHint: {
      ...Type.secondary,
      color: theme.textSecondary,
      paddingHorizontal: Space.md,
      paddingVertical: Space.sm,
    },
    searchResult: {
      paddingHorizontal: Space.md,
      paddingVertical: Space.sm,
      borderBottomWidth: StyleSheet.hairlineWidth,
      borderBottomColor: theme.border,
    },
    searchResultHeader: {
      flexDirection: "row",
      alignItems: "center",
      gap: Space.xs,
    },
    searchResultTitle: { flex: 1, ...Type.compact, color: theme.textSecondary },
    searchResultBadge: {
      ...Type.micro,
      color: theme.primary,
    },
    searchResultSnippet: { ...Type.callout, ...Weight.regular, color: theme.text },
    loadMore: { paddingVertical: Space.sm, alignItems: "center" },
    loadMoreText: { ...Type.label, color: theme.primary },
  });
}
