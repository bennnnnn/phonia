import { useEffect, useMemo, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { Icon } from "@/ui/icons/Icon";
import { useTranslation } from "react-i18next";

import { useLinkPreviewAllowed } from "@/components/markdown/LinkPreviewTrust";
import { busyPreviewRetryAt, fetchLinkPreview, LinkPreview } from "@/lib/linkPreview";
import { openAllowedUrl } from "@/lib/linkSchemePolicy";
import { Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { IconSize } from "@/ui/icons/sizes";
import { PARAGRAPH_GAP } from "@/components/markdown/markdownContentStyles";

type Props = { url: string };

/**
 * Times a card on screen asks again after a busy refusal. This phone asks for three previews
 * at a time, as many as the server loads at once (`lib/linkPreview.ts`), so a refusal means
 * another install of the account holds slots; its previews end within the server's 8 s
 * deadline. Bounded, since every request counts against the server's 20 a minute.
 */
const BUSY_RETRIES = 2;

export function LinkPreviewCard({ url }: Props) {
  const theme = useTheme();
  const { t } = useTranslation();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const mayFetch = useLinkPreviewAllowed(url);
  const [preview, setPreview] = useState<LinkPreview | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    // A link the model wrote on its own: the server must not fetch it (its
    // URL can carry the user's data), so it stays a plain link card.
    if (!mayFetch) return;
    let cancelled = false;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let retriesLeft = BUSY_RETRIES;
    // Cards showing the same link wait for the same moment and then share one request.
    const askAt = (at: number) => {
      retry = setTimeout(() => (Date.now() < at ? askAt(at) : load()), Math.max(0, at - Date.now()));
    };
    const load = () => {
      fetchLinkPreview(url).then(
        (data) => {
          if (cancelled) return;
          setPreview(data);
          setFailed(false);
        },
        () => {
          if (cancelled) return;
          setFailed(true);
          // Only a busy refusal is asked again while the card is shown; any other failure never is.
          const at = busyPreviewRetryAt(url);
          if (at === null || retriesLeft === 0) return;
          retriesLeft -= 1;
          askAt(at);
        },
      );
    };
    load();
    return () => {
      cancelled = true;
      clearTimeout(retry);
    };
  }, [url, mayFetch]);

  const open = () => {
    void openAllowedUrl(url);
  };

  if (failed || !mayFetch) {
    return (
      <Pressable
        style={s.wrap}
        onPress={open}
        accessibilityRole="link"
        accessibilityLabel={url}
      >
        <Icon name="link" size={IconSize.xs} color={theme.primary} />
        <Text style={s.url} numberOfLines={2}>
          {url}
        </Text>
      </Pressable>
    );
  }

  if (!preview) {
    return (
      <View style={[s.wrap, s.loading]}>
        <Text style={s.loadingText}>{t("chat.link_preview_loading")}</Text>
      </View>
    );
  }

  return (
    <Pressable
      style={s.wrap}
      onPress={open}
      accessibilityRole="link"
      accessibilityLabel={preview.title || preview.url}
    >
      <Text style={s.title} numberOfLines={2}>
        {preview.title || preview.url}
      </Text>
      {preview.description ? (
        <Text style={s.desc} numberOfLines={3}>
          {preview.description}
        </Text>
      ) : null}
      <Text style={s.domain}>{preview.domain}</Text>
    </Pressable>
  );
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    wrap: {
      alignSelf: "stretch",
      borderRadius: Radius.card,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: theme.border,
      backgroundColor: theme.surface,
      paddingHorizontal: Space.sm,
      paddingVertical: Space.sm,
      marginTop: 0,
      marginBottom: PARAGRAPH_GAP,
      gap: Space.xxs,
    },
    loading: { opacity: 0.7 },
    loadingText: { ...Type.secondary, color: theme.textSecondary },
    title: { ...Type.callout, ...Weight.bold, color: theme.text },
    desc: { ...Type.secondary, lineHeight: 20, color: theme.textSecondary },
    domain: { ...Type.meta, color: theme.primary, marginTop: 2 },
    url: { flex: 1, ...Type.secondary, color: theme.primary },
  });
}
