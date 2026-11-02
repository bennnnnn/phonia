import { useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useTranslation } from "react-i18next";

import { useAccountSession } from "@/contexts/accountSession";
import {
  AttachmentViewerChrome,
  type AttachmentViewerProps,
} from "@/features/attachments/components/AttachmentViewerChrome";
import { resolveAttachmentUri } from "@/features/attachments/model/attachmentUri";
import { fetchAttachmentBytes } from "@/features/attachments/model/fetchAttachmentBytes";
import { Space } from "@/lib/space";
import { Theme, useTheme } from "@/lib/theme";
import { Type } from "@/lib/type";

const MAX_PREVIEW_CHARS = 200_000;

type Props = AttachmentViewerProps & {
  attachmentId?: string | null;
  path?: string | null;
};

export function AttachmentTextViewer({ visible, attachmentId, path, ...chrome }: Props) {
  const { t } = useTranslation();
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const { account, getToken } = useAccountSession();
  const [text, setText] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);

  const remoteUri = useMemo(
    () => resolveAttachmentUri({ attachmentId, path }),
    [attachmentId, path],
  );

  useEffect(() => {
    if (!visible || !remoteUri) {
      setText(null);
      setFailed(false);
      return;
    }
    // Closing the viewer stops the download, not just its result.
    const controller = new AbortController();
    setLoading(true);
    setFailed(false);
    void (async () => {
      try {
        const bytes = await fetchAttachmentBytes(remoteUri, getToken(), controller.signal);
        if (controller.signal.aborted) return;
        const decoded = new TextDecoder("utf-8", { fatal: false }).decode(bytes);
        setText(decoded.length > MAX_PREVIEW_CHARS ? decoded.slice(0, MAX_PREVIEW_CHARS) : decoded);
      } catch {
        if (!controller.signal.aborted) setFailed(true);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    })();
    return () => controller.abort();
  }, [visible, remoteUri, account, getToken]);

  return (
    <AttachmentViewerChrome
      {...chrome}
      visible={visible}
      closeLabel={t("preview.close")}
      shareLabel={t("preview.share")}
    >
      <View style={s.body}>
        {loading ? (
          <ActivityIndicator color={theme.primary} size="large" />
        ) : failed || text == null ? (
          <Text style={s.error}>{t("gallery.file_preview_failed")}</Text>
        ) : (
          <ScrollView
            testID="attachment-text-preview"
            contentContainerStyle={s.scroll}
          >
            <Text style={s.fileText} selectable>
              {text}
            </Text>
          </ScrollView>
        )}
      </View>
    </AttachmentViewerChrome>
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    body: { flex: 1 },
    scroll: { padding: Space.md },
    fileText: { ...Type.body, color: t.text },
    error: {
      ...Type.body,
      color: t.textSecondary,
      paddingHorizontal: Space.lg,
      textAlign: "center",
      marginTop: Space.xl,
    },
  });
}
