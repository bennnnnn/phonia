import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ActivityIndicator, RefreshControl, ScrollView, StyleSheet, Text, View } from "react-native";
import { Redirect, useRouter } from "expo-router";
import { useTranslation } from "react-i18next";

import { useAuth } from "@/contexts/AuthContext";
import { MemoryComposer } from "@/features/memory/components/MemoryComposer";
import { MemoryHeaderMenu } from "@/features/memory/components/MemoryHeaderMenu";
import { useClearAllMemories } from "@/features/memory/hooks/useClearAllMemories";
import { useMemoryDocuments } from "@/features/memory/hooks/useMemoryDocuments";
import { useSubmitInstruction } from "@/features/memory/hooks/useSubmitInstruction";
import {
  documentSummary,
  documentTitle,
  groupDocuments,
  parseMemoryDate,
} from "@/features/memory/model/memoryDocuments";
import { useAccountViewOwner } from "@/hooks/useAccountViewOwner";
import { useReconnectRefresh } from "@/hooks/useReconnectRefresh";
import { formatDate } from "@/lib/datetime/format";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { type Theme, useTheme } from "@/lib/theme";
import { Type } from "@/lib/type";
import { SkeletonList } from "@/ui/feedback/SkeletonLoader";
import { StateView } from "@/ui/feedback/StateView";
import { ListGroup } from "@/ui/list/ListGroup";
import { ListRow } from "@/ui/list/ListRow";

// While Recall reads recent chats for the first time, check back for a while.
const SCAN_POLL_MS = 5000;
const SCAN_POLLS = 36;

export default function MemoryScreen() {
  const view = useAccountViewOwner();
  return <MemoryContent key={view.key} isCurrentView={view.isCurrent} />;
}

function MemoryContent({ isCurrentView }: { isCurrentView: () => boolean }) {
  const { token } = useAuth();
  const { t, i18n } = useTranslation();
  const locale = i18n?.language;
  const theme = useTheme();
  const router = useRouter();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const { documents, scanning, loading, error, load, readAt, instruct } = useMemoryDocuments(token);
  const { clearAll } = useClearAllMemories(isCurrentView);
  const [refreshing, setRefreshing] = useState(false);
  const refreshingRef = useRef(false);

  useEffect(() => {
    if (isCurrentView()) void load();
  }, [isCurrentView, load]);
  // The API back after an outage: the pages read again.
  useReconnectRefresh(() => void load(), { onScreen: isCurrentView, readAt });

  useEffect(() => {
    if (!scanning) return;
    let polls = 0;
    const timer = setInterval(() => {
      polls += 1;
      if (polls > SCAN_POLLS || !isCurrentView()) {
        clearInterval(timer);
        return;
      }
      void load();
    }, SCAN_POLL_MS);
    return () => clearInterval(timer);
  }, [scanning, load, isCurrentView]);

  const sections = useMemo(() => groupDocuments(documents, t, locale), [documents, t, locale]);

  const submit = useSubmitInstruction(instruct, isCurrentView);

  const refresh = useCallback(async () => {
    if (!isCurrentView() || refreshingRef.current) return;
    refreshingRef.current = true;
    setRefreshing(true);
    await load();
    refreshingRef.current = false;
    if (isCurrentView()) setRefreshing(false);
  }, [isCurrentView, load]);

  if (!token) return <Redirect href="/login" />;
  if (loading) return <SkeletonList />;
  if (error) {
    return (
      <View style={s.center}>
        <StateView
          variant="error"
          title={t("common.error")}
          onRetry={() => { if (isCurrentView()) void load(); }}
          retryLabel={t("common.retry")}
        />
      </View>
    );
  }

  return (
    <View style={s.root}>
      <MemoryHeaderMenu
        items={[
          {
            key: "clear-all",
            label: t("settings.memory_clear_all"),
            icon: "trash",
            destructive: true,
            onPress: () => void clearAll().then((done) => done && isCurrentView() && void load()),
          },
        ]}
      />
      <ScrollView
        style={s.scroll}
        contentContainerStyle={s.content}
        keyboardShouldPersistTaps="handled"
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void refresh()} />}
        testID="memory-documents"
      >
        {scanning ? (
          <View style={s.scanning} accessibilityLiveRegion="polite" testID="memory-scanning">
            <ActivityIndicator size="small" color={theme.primary} />
            <Text style={s.scanningText}>{t("memory.scanning")}</Text>
          </View>
        ) : null}
        {sections.length === 0 && !scanning ? (
          <StateView
            variant="empty"
            icon="sparkles"
            title={t("memory.empty_title")}
            message={t("memory.empty_body")}
            onRetry={() => { if (isCurrentView()) router.replace("/"); }}
            retryLabel={t("chat.new_chat")}
          />
        ) : null}
        {sections.map((section) => (
          <ListGroup
            key={section.group}
            label={t(`memory.group.${section.group}`)}
            style={s.group}
            testID={`memory-group-${section.group}`}
          >
            {section.documents.map((document) => {
              const title = documentTitle(document, t);
              const updated = parseMemoryDate(document.updated_at);
              const date = updated ? formatDate(updated, "monthDay") : undefined;
              return (
                <ListRow
                  key={document.key}
                  title={title}
                  subtitle={documentSummary(document, t) || undefined}
                  detail={date}
                  accessory="chevron"
                  onPress={() => router.push({
                    pathname: "/memory/[key]",
                    params: { key: document.key },
                  })}
                  accessibilityLabel={date ? `${title}, ${t("memory.updated", { date })}` : title}
                  testID={`memory-document-${document.key}`}
                />
              );
            })}
          </ListGroup>
        ))}
      </ScrollView>
      <MemoryComposer placeholder={t("memory.composer_placeholder")} onSubmit={submit} />
    </View>
  );
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    center: {
      flex: 1,
      alignItems: "center",
      justifyContent: "center",
      backgroundColor: theme.bg,
    },
    root: { flex: 1, backgroundColor: theme.bg },
    scroll: { flex: 1 },
    content: { padding: Space.md, paddingBottom: Space.lg },
    group: { marginBottom: Space.lg },
    scanning: {
      flexDirection: "row",
      alignItems: "center",
      gap: Space.xs,
      padding: Space.sm,
      marginBottom: Space.md,
      borderRadius: Radius.lg,
      backgroundColor: theme.primaryLight,
    },
    scanningText: { ...Type.caption, color: theme.text, flex: 1 },
  });
}
