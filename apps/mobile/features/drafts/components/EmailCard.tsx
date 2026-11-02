import { useEffect, useMemo, useRef, useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { useTranslation } from "react-i18next";

import { CopyButton } from "@/components/CopyButton";
import { Icon } from "@/ui/icons/Icon";
import { CardShell } from "@/components/rich/CardShell";
import { BrandMark } from "@/ui/icons/brand";
import { useActionFeedbackOptional } from "@/contexts/actionFeedbackCore";
import { useEmailCardPersist } from "@/features/drafts/hooks/useEmailCardPersist";
import { fullEmailText } from "@/features/drafts/model/emailCompose";
import { openGmailCompose } from "@/features/drafts/model/openGmailCompose";
import { notifySuccess, tap } from "@/lib/haptics";
import { IconSize } from "@/ui/icons/sizes";
import { EmailDraft } from "@/lib/richBlocks";
import { Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";

type Props = { draft: EmailDraft };

function draftFields(draft: EmailDraft) {
  return {
    to: draft.to ?? "",
    subject: draft.subject ?? "",
    body: draft.body,
  };
}

function toDraft(fields: { to: string; subject: string; body: string }): EmailDraft {
  const to = fields.to.trim();
  const subject = fields.subject.trim();
  const body = fields.body.trim();
  return {
    ...(to ? { to } : {}),
    ...(subject ? { subject } : {}),
    body: body || fields.body,
  };
}

export function EmailCard({ draft }: Props) {
  const theme = useTheme();
  const { t } = useTranslation();
  const feedback = useActionFeedbackOptional();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const [gmailOpening, setGmailOpening] = useState(false);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const editingRef = useRef(editing);
  editingRef.current = editing;
  const [fields, setFields] = useState(() => draftFields(draft));
  const fieldsRef = useRef(fields);
  fieldsRef.current = fields;

  const draftTo = draft.to;
  const draftSubject = draft.subject;
  const draftBody = draft.body;

  useEffect(() => {
    if (editingRef.current) return;
    setFields(draftFields({ to: draftTo, subject: draftSubject, body: draftBody }));
  }, [draftTo, draftSubject, draftBody]);

  const currentDraft = useMemo(() => toDraft(fields), [fields]);
  const persistNow = useEmailCardPersist(currentDraft, editing);
  const copyPayload = fullEmailText(currentDraft);

  const onGmail = async () => {
    if (gmailOpening) return;
    setGmailOpening(true);
    try {
      const result = await openGmailCompose(currentDraft);
      if (result === "copied_only") {
        if (feedback) feedback.success(t("chat.email_card_gmail_copied"));
      } else {
        notifySuccess();
      }
    } finally {
      setGmailOpening(false);
    }
  };

  const toggleEditing = async () => {
    if (saving) return;
    tap();
    if (editing) {
      const prev = fieldsRef.current;
      const next = {
        to: prev.to.trim(),
        subject: prev.subject.trim(),
        body: prev.body.trimEnd(),
      };
      fieldsRef.current = next;
      setFields(next);
      setSaving(true);
      try {
        if (await persistNow(toDraft(next))) setEditing(false);
      } finally {
        setSaving(false);
      }
      return;
    }
    setEditing(true);
  };

  return (
    <CardShell
      label={t("rich.email_draft")}
      icon="mail"
      accent={false}
      headerActions={
        <>
          <Pressable
            style={[s.iconBtn, editing && s.iconBtnActive]}
            onPress={() => { void toggleEditing(); }}
            disabled={saving}
            accessibilityState={{ busy: saving, disabled: saving }}
            hitSlop={6}
            accessibilityRole="button"
            accessibilityLabel={
              editing ? t("chat.email_card_done") : t("chat.email_card_edit")
            }
          >
            {editing ? (
              <Icon name="check" size={IconSize.sm} />
            ) : (
              <Icon name="edit" size={IconSize.sm} color={theme.text} />
            )}
          </Pressable>
          <CopyButton
            text={copyPayload}
            accessibilityLabel={t("chat.email_card_copy")}
          />
          <Pressable
            style={[s.iconBtn, gmailOpening && s.gmailBtnBusy]}
            onPress={() => void onGmail()}
            hitSlop={6}
            accessibilityRole="button"
            accessibilityLabel={t("chat.email_card_gmail")}
            disabled={gmailOpening || editing}
          >
            <BrandMark name="gmail" size={IconSize.sm} />
          </Pressable>
        </>
      }
    >
      <View style={s.body}>
        {editing ? (
          <>
            <Text style={s.fieldLabel}>{t("chat.email_card_to")}</Text>
            <TextInput
              style={s.input}
              value={fields.to}
              onChangeText={(to) => {
                setFields((prev) => {
                  const next = { ...prev, to };
                  fieldsRef.current = next;
                  return next;
                });
              }}
              placeholder={t("chat.email_card_to_placeholder")}
              placeholderTextColor={theme.textDisabled}
              autoCapitalize="none"
              keyboardType="email-address"
              autoCorrect={false}
            />
            <Text style={s.fieldLabel}>{t("chat.email_card_subject")}</Text>
            <TextInput
              style={s.input}
              value={fields.subject}
              onChangeText={(subject) => {
                setFields((prev) => {
                  const next = { ...prev, subject };
                  fieldsRef.current = next;
                  return next;
                });
              }}
              placeholder={t("chat.email_card_subject_placeholder")}
              placeholderTextColor={theme.textDisabled}
            />
            <TextInput
              style={[s.input, s.bodyInput]}
              value={fields.body}
              onChangeText={(body) => {
                setFields((prev) => {
                  const next = { ...prev, body };
                  fieldsRef.current = next;
                  return next;
                });
              }}
              multiline
              textAlignVertical="top"
              placeholder={t("chat.email_card_body_placeholder")}
              placeholderTextColor={theme.textDisabled}
            />
          </>
        ) : (
          <>
            {currentDraft.to ? (
              <Text style={s.meta} selectable>
                <Text style={s.metaKey}>{t("chat.email_card_to")} </Text>
                {currentDraft.to}
              </Text>
            ) : null}
            {currentDraft.subject ? (
              <Text style={s.subject} selectable>
                <Text style={s.subjectKey}>{t("chat.email_card_subject")} </Text>
                {currentDraft.subject}
              </Text>
            ) : null}
            <Text style={s.bodyText} selectable>
              {currentDraft.body}
            </Text>
          </>
        )}
      </View>
    </CardShell>
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    iconBtn: {
      width: 32,
      height: 32,
      alignItems: "center",
      justifyContent: "center",
      borderRadius: Radius.xs,
    },
    iconBtnActive: { backgroundColor: t.primaryLight },
    gmailBtnBusy: { opacity: 0.6 },
    body: { gap: Space.xs },
    fieldLabel: {
      ...Type.overline,
      color: t.textTertiary,
    },
    input: {
      backgroundColor: t.bg,
      borderRadius: Radius.sm,
      borderWidth: 1,
      borderColor: t.border,
      paddingHorizontal: Space.sm,
      paddingVertical: Space.sm,
      ...Type.body,
      color: t.text,
    },
    bodyInput: { minHeight: 140, lineHeight: 24 },
    meta: { ...Type.secondary, lineHeight: 20, color: t.textSecondary },
    metaKey: { ...Weight.semibold, color: t.textTertiary },
    subject: {
      ...Type.body,
      ...Weight.bold,
      color: t.text,
    },
    // The same quiet key as "To", so both fields read as label + value.
    subjectKey: { ...Type.secondary, ...Weight.semibold, color: t.textTertiary },
    bodyText: {
      ...Type.body,
      color: t.text,
    },
  });
}
