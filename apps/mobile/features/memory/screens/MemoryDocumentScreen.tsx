import { memo, useCallback, useEffect, useMemo, useState } from "react";
import {
  type GestureResponderEvent,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { Redirect, useLocalSearchParams, useRouter } from "expo-router";
import { useTranslation } from "react-i18next";

import { FieldSheet } from "@/ui/overlay/FieldSheet";
import { useAuth } from "@/contexts/AuthContext";
import { useActionFeedbackOptional } from "@/contexts/actionFeedbackCore";
import { MemoryComposer } from "@/features/memory/components/MemoryComposer";
import { useMemoryDocuments } from "@/features/memory/hooks/useMemoryDocuments";
import { useSubmitInstruction } from "@/features/memory/hooks/useSubmitInstruction";
import {
  documentSummary,
  documentTitle,
  parseMemoryDate,
} from "@/features/memory/model/memoryDocuments";
import { MEMORY_TEXT_MAX_LENGTH, stripMemoryAsOf } from "@/features/memory/model/memoryFacts";
import type { Memory } from "@/features/memory/types";
import { useAccountViewOwner } from "@/hooks/useAccountViewOwner";
import { useReconnectRefresh } from "@/hooks/useReconnectRefresh";
import { formatDate } from "@/lib/datetime/format";
import { notifyDestructive, tap } from "@/lib/haptics";
import { reportRecoverableError } from "@/lib/reportRecoverableError";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { type Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";
import { SkeletonList } from "@/ui/feedback/SkeletonLoader";
import { StateView } from "@/ui/feedback/StateView";
import { confirmDialog } from "@/ui/overlay/dialogs";
import { Menu } from "@/ui/overlay/Menu";
import { MemoryHeaderMenu } from "@/features/memory/components/MemoryHeaderMenu";
import { useClearAllMemories } from "@/features/memory/hooks/useClearAllMemories";
import { memoryFailureKey } from "@/features/memory/model/memoryFailure";

type FactMenu = { fact: Memory; point: { x: number; y: number } };

export default function MemoryDocumentScreen() {
  const view = useAccountViewOwner();
  return <DocumentContent key={view.key} isCurrentView={view.isCurrent} />;
}

function DocumentContent({ isCurrentView }: { isCurrentView: () => boolean }) {
  const { token } = useAuth();
  const { key } = useLocalSearchParams<{ key: string }>();
  const { t } = useTranslation();
  const theme = useTheme();
  const router = useRouter();
  const feedback = useActionFeedbackOptional();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const memory = useMemoryDocuments(token);
  const { load, readAt, instruct, deleteDocument, deleteFact, editFact, setFactMuted } = memory;
  const { clearAll } = useClearAllMemories(isCurrentView);
  const document = memory.documents.find((doc) => doc.key === key);
  const [menu, setMenu] = useState<FactMenu | null>(null);
  const [editing, setEditing] = useState<{ fact: Memory; text: string } | null>(null);
  const [saving, setSaving] = useState(false);

  // Opened from a link, the pages may not be loaded yet.
  const missing = !document;
  useEffect(() => {
    if (missing && isCurrentView()) void load();
  }, [missing, isCurrentView, load]);
  // The API back after an outage: the pages read again.
  useReconnectRefresh(() => void load(), { onScreen: isCurrentView, readAt });

  const title = document ? documentTitle(document, t) : "";
  const summary = document ? documentSummary(document, t) : "";
  const updated = parseMemoryDate(document?.updated_at);

  const openMenu = useCallback((fact: Memory, event: GestureResponderEvent) => {
    tap();
    setMenu({ fact, point: { x: event.nativeEvent.pageX, y: event.nativeEvent.pageY } });
  }, []);

  const removeDocument = useCallback(() => {
    if (!document) return;
    void confirmDialog({
      title: t("memory.delete_document_title", { title }),
      message: t("memory.delete_document_body"),
      confirmLabel: t("common.delete"),
      destructive: true,
    }).then(async (ok) => {
      if (!ok) return;
      const done = await deleteDocument(document.key);
      if (!isCurrentView()) return;
      if (!done.ok) {
        reportRecoverableError(feedback, t(memoryFailureKey(done.failure, "memory.delete_failed")));
        return;
      }
      notifyDestructive();
      router.back();
    });
  }, [document, t, title, deleteDocument, isCurrentView, feedback, router]);

  const removeFact = useCallback((fact: Memory) => {
    const lastFact = document?.facts.length === 1;
    void confirmDialog({
      title: t("memory.delete_fact_title"),
      message: stripMemoryAsOf(fact.text),
      confirmLabel: t("common.delete"),
      destructive: true,
    }).then(async (ok) => {
      if (!ok) return;
      const done = await deleteFact(fact.id);
      if (!isCurrentView()) return;
      if (!done.ok) {
        reportRecoverableError(feedback, t(memoryFailureKey(done.failure, "memory.delete_failed")));
        return;
      }
      notifyDestructive();
      // The page is gone with its last fact.
      if (lastFact) router.back();
    });
  }, [document, t, deleteFact, isCurrentView, feedback, router]);

  const saveEdit = useCallback(async () => {
    const text = editing?.text.trim();
    if (!editing || !text || saving) return;
    setSaving(true);
    const saved = await editFact(editing.fact.id, text);
    if (!isCurrentView()) return;
    setSaving(false);
    if (!saved.ok) {
      reportRecoverableError(feedback, t(memoryFailureKey(saved.failure, "memory.edit_failed")));
      return;
    }
    setEditing(null);
  }, [editing, saving, editFact, isCurrentView, feedback, t]);

  const toggleMuted = useCallback(async (fact: Memory) => {
    const changed = await setFactMuted(fact.id, fact.status !== "muted");
    if (!changed.ok && isCurrentView()) {
      reportRecoverableError(feedback, t(memoryFailureKey(changed.failure, "memory.mute_failed")));
    }
  }, [setFactMuted, isCurrentView, feedback, t]);

  const submit = useSubmitInstruction(
    instruct,
    isCurrentView,
    typeof key === "string" ? key : undefined,
  );

  if (!token) return <Redirect href="/login" />;
  if (!document) {
    if (memory.loading) return <SkeletonList />;
    // A failed read is not a deleted page: say so and offer the read again.
    if (memory.error) {
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
      <View style={s.center}>
        <StateView
          variant="empty"
          icon="sparkles"
          title={t("memory.document_gone")}
          onRetry={() => router.back()}
          retryLabel={t("memory.back_to_memory")}
        />
      </View>
    );
  }

  return (
    <View style={s.root}>
      <MemoryHeaderMenu
        items={[
          {
            key: "delete-page",
            label: t("memory.delete_page"),
            icon: "trash",
            destructive: true,
            onPress: removeDocument,
            testID: "memory-document-delete",
          },
          {
            key: "clear-all",
            label: t("settings.memory_clear_all"),
            icon: "trash",
            destructive: true,
            onPress: () =>
              void clearAll().then((done) => done && isCurrentView() && router.back()),
          },
        ]}
      />
      <ScrollView
        style={s.scroll}
        contentContainerStyle={s.content}
        keyboardShouldPersistTaps="handled"
        testID="memory-document"
      >
        <View style={s.titleRow}>
          <Text style={s.title} accessibilityRole="header">{title}</Text>
        </View>
        {updated ? (
          <View style={s.block}>
            <Text style={s.label}>{t("memory.last_updated")}</Text>
            <Text style={s.value}>{formatDate(updated, "monthDayYear")}</Text>
          </View>
        ) : null}
        {summary ? (
          <View style={s.block}>
            <Text style={s.label}>{t("memory.summary_label")}</Text>
            <Text style={s.value}>{summary}</Text>
          </View>
        ) : null}
        <View style={s.block}>
          <Text style={s.label}>{t("memory.details_label")}</Text>
          {document.facts.map((fact) => (
            <FactRow key={fact.id} fact={fact} s={s} onOpenMenu={openMenu} />
          ))}
        </View>
      </ScrollView>
      <MemoryComposer
        placeholder={t("memory.composer_placeholder_document")}
        onSubmit={submit}
      />
      <Menu
        visible={menu != null}
        anchorPoint={menu?.point ?? null}
        onClose={() => setMenu(null)}
        items={[
          {
            key: "edit",
            label: t("memory.edit_fact"),
            icon: "pencil",
            onPress: () => {
              const fact = menu?.fact;
              setMenu(null);
              if (fact) setEditing({ fact, text: stripMemoryAsOf(fact.text) });
            },
          },
          {
            key: "mute",
            label: t(menu?.fact.status === "muted" ? "memory.unmute_fact" : "memory.mute_fact"),
            icon: menu?.fact.status === "muted" ? "eye" : "eye-off",
            onPress: () => {
              const fact = menu?.fact;
              setMenu(null);
              if (fact) void toggleMuted(fact);
            },
          },
          {
            key: "delete",
            label: t("common.delete"),
            icon: "trash",
            destructive: true,
            onPress: () => {
              const fact = menu?.fact;
              setMenu(null);
              if (fact) removeFact(fact);
            },
          },
        ]}
        testID="memory-fact-menu"
      />
      <FieldSheet
        visible={editing != null}
        title={t("memory.edit_title")}
        value={editing?.text ?? ""}
        onChangeText={(text) => setEditing((current) => (current ? { ...current, text } : current))}
        onClose={() => { if (!saving) setEditing(null); }}
        onSave={() => void saveEdit()}
        multiline
        maxLength={MEMORY_TEXT_MAX_LENGTH}
        saving={saving}
      />
    </View>
  );
}

type Styles = ReturnType<typeof makeStyles>;

/**
 * One fact of the page. Memoized: typing in the edit sheet or opening a fact's
 * menu redrew every fact on the page (150 per keystroke on a full page).
 */
const FactRow = memo(function FactRow({ fact, s, onOpenMenu }: {
  fact: Memory;
  s: Styles;
  onOpenMenu: (fact: Memory, event: GestureResponderEvent) => void;
}) {
  const { t } = useTranslation();
  const muted = fact.status === "muted";
  const text = stripMemoryAsOf(fact.text);
  const source = fact.source_chat_title
    ? t("memory.source_chat", { title: fact.source_chat_title })
    : null;
  return (
    <Pressable
      style={({ pressed }) => [s.fact, pressed && s.factPressed]}
      onPress={(event) => onOpenMenu(fact, event)}
      onLongPress={(event) => onOpenMenu(fact, event)}
      accessibilityRole="button"
      accessibilityLabel={muted ? `${text}. ${t("memory.muted_label")}` : text}
      accessibilityHint={t("memory.fact_hint")}
      testID={`memory-fact-${fact.id}`}
    >
      <Text style={s.bullet}>•</Text>
      <View style={s.factBody}>
        <Text style={[s.factText, muted && s.factMuted]}>{text}</Text>
        {muted ? (
          <Text style={s.factMeta} testID={`memory-fact-muted-${fact.id}`}>
            {t("memory.muted_label")}
          </Text>
        ) : null}
        {source ? <Text style={s.factMeta}>{source}</Text> : null}
      </View>
    </Pressable>
  );
});

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
    content: { padding: Space.md, paddingBottom: Space.lg, gap: Space.lg },
    titleRow: {
      flexDirection: "row",
      alignItems: "center",
      gap: Space.sm,
    },
    title: { ...Type.title, color: theme.text, flex: 1 },
    block: { gap: Space.xxs },
    label: { ...Type.label, color: theme.textSecondary },
    value: { ...Type.body, color: theme.text },
    fact: {
      flexDirection: "row",
      gap: Space.xs,
      paddingVertical: Space.xxs,
      paddingHorizontal: Space.xxs,
      marginHorizontal: -Space.xxs,
      borderRadius: Radius.md,
    },
    factPressed: { backgroundColor: theme.pressed },
    bullet: { ...Type.body, ...Weight.semibold, color: theme.textSecondary },
    factBody: { flex: 1, gap: Space.xxs },
    factText: { ...Type.body, color: theme.text },
    factMuted: { color: theme.textSecondary },
    factMeta: { ...Type.label, color: theme.textSecondary },
  });
}
