import { useRef } from "react";
import { FlashList } from "@shopify/flash-list";
import { Redirect } from "expo-router";
import { useTranslation } from "react-i18next";

import { StateView } from "@/ui/feedback/StateView";
import { SettingsSkeleton } from "@/features/account/components/SettingsSkeleton";
import {
  SettingsGroup,
  SettingsLinkRow,
  useSettingsAction,
  useSettingsContentStyle,
} from "@/features/account/components/settingsUi";
import { useAuth } from "@/contexts/AuthContext";
import { useFocusedList } from "@/features/account/hooks/useFocusedList";
import { api, type Chat } from "@/lib/api";
import {
  fetchChatList,
  fetchMoreArchivedChats,
  getChatListFetchedAt,
  invalidateChatListCache,
} from "@/features/chat/model/chatListCache";
import { notifyDestructive } from "@/lib/haptics";
import { useTheme } from "@/lib/theme";

/** The drawer's chat list holds the archived rows too: a fresh one is read from memory,
 * not downloaded again on every visit (code-health audit NET-19). */
async function readArchivedChats(token: string): Promise<Chat[]> {
  const { data, error } = await fetchChatList(token);
  if (error || !data) throw error ?? new Error("chat list unavailable");
  return data.archived ?? [];
}

export default function ArchivedChatsScreen() {
  const { token } = useAuth();
  const { t } = useTranslation();
  const theme = useTheme();
  const contentStyle = useSettingsContentStyle();
  const action = useSettingsAction();
  const {
    items: chats,
    setItems: setChats,
    loading,
    loadError,
    load,
  } = useFocusedList(token, readArchivedChats, getChatListFetchedAt);

  const drop = (chat: Chat) => setChats((rows) => rows.filter((row) => row.id !== chat.id));

  // Past the first page: the list used to stop at the newest 50 archived chats.
  const paging = useRef(false);
  const loadMore = async () => {
    if (!token || paging.current) return;
    paging.current = true;
    try {
      const grown = await fetchMoreArchivedChats(token);
      if (!grown) return;
      setChats((rows) => {
        const shown = new Set(rows.map((row) => row.id));
        return [...rows, ...grown.archived.filter((chat) => !shown.has(chat.id))];
      });
    } catch {
      // The rows shown stay; reaching the end again tries again.
    } finally {
      paging.current = false;
    }
  };

  const unarchive = (chat: Chat) => {
    if (!token) return;
    void action.run(
      `unarchive:${chat.id}`,
      async () => {
        await api.setArchive(token, chat.id, false);
        invalidateChatListCache();
        drop(chat);
      },
      { errorKey: "chat.archive_failed" },
    );
  };

  const remove = (chat: Chat) => {
    if (!token) return;
    void action.run(
      `delete:${chat.id}`,
      async () => {
        await api.deleteChat(token, chat.id);
        notifyDestructive();
        invalidateChatListCache();
        drop(chat);
      },
      {
        errorKey: "chat.delete_failed",
        confirm: {
          title: t("chat.delete_confirm_title"),
          message: t("chat.delete_confirm_body"),
          cancelLabel: t("common.cancel"),
          confirmLabel: t("common.delete"),
          destructive: true,
        },
      },
    );
  };

  if (!token) return <Redirect href="/login" />;

  if (loading && chats.length === 0 && !loadError) {
    return <SettingsSkeleton accessibilityLabel={t("settings.archived_chats")} />;
  }

  if (loadError && chats.length === 0) {
    return <StateView variant="error" title={t("common.error")} onRetry={() => void load()} />;
  }

  if (!loading && chats.length === 0) {
    return <StateView variant="empty" icon="archive" title={t("settings.archived_chats_empty")} />;
  }

  return (
    <FlashList
      data={chats}
      keyExtractor={(chat) => chat.id}
      style={{ flex: 1, backgroundColor: theme.bg }}
      contentContainerStyle={contentStyle}
      onEndReached={() => void loadMore()}
      onEndReachedThreshold={0.5}
      renderItem={({ item: chat }) => (
        <SettingsGroup>
          <SettingsLinkRow
            title={chat.title?.trim() || t("common.untitled")}
            value={t("chat.unarchive")}
            busy={action.busy === `unarchive:${chat.id}`}
            disabled={action.busy !== null}
            onPress={() => unarchive(chat)}
          />
          <SettingsLinkRow
            title={t("chat.delete")}
            danger
            busy={action.busy === `delete:${chat.id}`}
            disabled={action.busy !== null}
            onPress={() => remove(chat)}
          />
        </SettingsGroup>
      )}
    />
  );
}
