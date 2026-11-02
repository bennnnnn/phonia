import { useMemo, useState } from "react";
import { Pressable, StyleSheet, Text, View, type StyleProp, type ImageStyle } from "react-native";
import { Image } from "expo-image";
import { useTranslation } from "react-i18next";

import { imageHost } from "@/lib/images/imageUriPolicy";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { Theme, useTheme } from "@/lib/theme";
import { Type } from "@/lib/type";
import { Icon } from "@/ui/icons/Icon";
import { IconSize } from "@/ui/icons/sizes";

type Props = {
  uri: string;
  alt: string;
  imageStyle: StyleProp<ImageStyle>;
};

/**
 * An image from a host the app does not trust (imageUriPolicy "ask"): nothing
 * is fetched until the reader taps. The card names the host, since the URL
 * itself may carry data a prompt-injected reply put there.
 */
export function TapToLoadImage({ uri, alt, imageStyle }: Props) {
  const theme = useTheme();
  const { t } = useTranslation();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const [loaded, setLoaded] = useState(false);
  const host = imageHost(uri);
  const title = t("chat.image_remote_title", { host });

  if (loaded) {
    return (
      <Image
        source={{ uri }}
        style={imageStyle}
        contentFit="contain"
        cachePolicy="memory-disk"
        accessibilityRole="image"
        accessibilityLabel={alt || undefined}
        accessible={alt.length > 0}
      />
    );
  }

  return (
    <Pressable
      style={s.card}
      onPress={() => setLoaded(true)}
      accessibilityRole="button"
      accessibilityLabel={alt ? `${alt}. ${title}` : title}
      accessibilityHint={t("chat.image_remote_hint")}
      testID="tap-to-load-image"
    >
      <Icon name="image" size={IconSize.sm} color={theme.textSecondary} />
      <View style={s.text}>
        <Text style={s.title} numberOfLines={2}>
          {alt || title}
        </Text>
        <Text style={s.hint} numberOfLines={1}>
          {alt ? `${title} · ${t("chat.image_remote_hint")}` : t("chat.image_remote_hint")}
        </Text>
      </View>
    </Pressable>
  );
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    card: {
      flexDirection: "row",
      alignItems: "center",
      alignSelf: "stretch",
      gap: Space.sm,
      minHeight: 44,
      paddingHorizontal: Space.sm,
      paddingVertical: Space.sm,
      marginVertical: Space.xs,
      borderRadius: Radius.md,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: theme.border,
      backgroundColor: theme.contentSurface,
    },
    text: { flex: 1, gap: Space.xxs },
    title: { ...Type.secondary, color: theme.text },
    hint: { ...Type.meta, color: theme.textSecondary },
  });
}
