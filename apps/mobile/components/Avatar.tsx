import { useMemo, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { Image } from "expo-image";

import { getInitials } from "@/lib/profile";
import { attachmentRequestHeaders, resolveAttachmentUri } from "@/features/attachments/model/attachmentUri";
import { Theme, useTheme } from "@/lib/theme";
import { Weight } from "@/lib/type";

/** The profile picture when it loads, otherwise the user's initials (also when it fails). */
export function Avatar({
  name,
  uri,
  token = null,
  size = 34,
}: {
  name: string | null;
  uri?: string | null;
  token?: string | null;
  size?: number;
}) {
  const theme = useTheme();
  const styles = useMemo(() => makeStyles(theme), [theme]);
  const dim = { width: size, height: size, borderRadius: size / 2 };
  // A photo that fails (deleted, expired, offline) falls back to the initials, not a blank circle.
  const [failedUri, setFailedUri] = useState<string | null>(null);

  if (uri && uri !== failedUri) {
    const resolvedUri = resolveAttachmentUri({ path: uri }) ?? uri;
    return (
      <Image
        testID="avatar-image"
        source={{ uri: resolvedUri, headers: attachmentRequestHeaders(resolvedUri, token) }}
        style={[dim, { backgroundColor: theme.surface }]}
        contentFit="cover"
        cachePolicy="memory-disk"
        onError={() => setFailedUri(uri)}
      />
    );
  }
  return (
    <View style={[dim, styles.fallback]}>
      {/* The circle is a fixed size, so its initials are too. */}
      <Text style={[styles.text, { fontSize: size * 0.4 }]} allowFontScaling={false}>
        {getInitials(name)}
      </Text>
    </View>
  );
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    fallback: {
      backgroundColor: theme.primary,
      alignItems: "center",
      justifyContent: "center",
    },
    text: { color: theme.onPrimary, ...Weight.bold },
  });
}
