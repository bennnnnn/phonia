import { useMemo, useState } from "react";
import { Image } from "expo-image";
import { Dimensions, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useTranslation } from "react-i18next";

import { Sheet } from "@/ui/overlay/Sheet";
import { Icon } from "@/ui/icons/Icon";
import { openAllowedUrl } from "@/lib/linkSchemePolicy";
import {
  SearchSource,
  faviconHost,
  faviconUrl,
  hostnameFromUrl,
  preferDistinctHostSources,
} from "@/lib/searchSources";
import { Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { IconSize } from "@/ui/icons/sizes";

const MAX_CHIP_ICONS = 3;

type Props = {
  sources: SearchSource[];
};

export function SearchSourcesStack({ sources }: Props) {
  const { t } = useTranslation();
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const [sheetOpen, setSheetOpen] = useState(false);

  if (sources.length === 0) return null;

  const ordered = preferDistinctHostSources(sources);
  const preview = ordered.slice(0, MAX_CHIP_ICONS);
  const label = t("chat.sources_count", { count: sources.length });

  return (
    <>
      <Pressable
        style={s.chip}
        onPress={() => setSheetOpen(true)}
        accessibilityRole="button"
        accessibilityLabel={label}
      >
        <Text style={s.chipLabel}>{label}</Text>
        <View style={s.iconCluster}>
          {preview.map((source, index) => (
            <View
              key={`${source.url}-${index}`}
              style={[s.iconSlot, index > 0 && s.iconOverlap, { zIndex: MAX_CHIP_ICONS - index }]}
            >
              <FaviconCircle url={source.url} size={22} ringColor={theme.surface} />
            </View>
          ))}
        </View>
      </Pressable>

      <SearchSourcesSheet
        visible={sheetOpen}
        sources={ordered}
        onClose={() => setSheetOpen(false)}
      />
    </>
  );
}

function SearchSourcesSheet({
  visible,
  sources,
  onClose,
}: {
  visible: boolean;
  sources: SearchSource[];
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const theme = useTheme();
  const s = useMemo(() => makeSheetStyles(theme), [theme]);
  const listMaxHeight = Math.round(Dimensions.get("window").height * 0.55);

  return (
    <Sheet visible={visible} onClose={onClose} minBottomPadding={16} contentContainerStyle={s.sheet}>
      <Text style={s.title} accessibilityRole="header">{t("chat.sources_title")}</Text>
      <ScrollView
        style={[s.list, { maxHeight: listMaxHeight }]}
        bounces={false}
        showsVerticalScrollIndicator={false}
      >
        {sources.map((source, index) => (
          <SourceRow
            key={`${source.url}-${index}`}
            source={source}
            theme={theme}
            isLast={index === sources.length - 1}
          />
        ))}
      </ScrollView>
    </Sheet>
  );
}

function SourceRow({
  source,
  theme,
  isLast,
}: {
  source: SearchSource;
  theme: Theme;
  isLast: boolean;
}) {
  const s = makeSheetStyles(theme);
  const domain = hostnameFromUrl(source.url);
  const open = () => {
    void openAllowedUrl(source.url);
  };

  return (
    <Pressable
      style={[s.row, !isLast && s.rowBorder]}
      onPress={open}
      accessibilityRole="link"
      accessibilityLabel={source.title}
    >
      <FaviconCircle url={source.url} size={28} ringColor={theme.bg} />
      <View style={s.body}>
        <Text style={s.domain} numberOfLines={1}>
          {domain}
        </Text>
        <Text style={s.rowTitle} numberOfLines={2}>
          {source.title}
        </Text>
        {source.snippet ? (
          <Text style={s.snippet} numberOfLines={2}>
            {source.snippet}
          </Text>
        ) : null}
      </View>
      <Icon name="external-link" size={IconSize.xs} color={theme.textSecondary} />
    </Pressable>
  );
}

function FaviconCircle({
  url,
  size,
  ringColor,
}: {
  url: string;
  size: number;
  ringColor: string;
}) {
  const theme = useTheme();
  const [failed, setFailed] = useState(false);
  const host = faviconHost(url);
  const uri = faviconUrl(url);
  const ring = Math.max(2, Math.round(size * 0.09));

  const frame = {
    width: size,
    height: size,
    borderRadius: size / 2,
    borderWidth: ring,
    borderColor: ringColor,
    overflow: "hidden" as const,
    backgroundColor: theme.surfaceAlt,
    alignItems: "center" as const,
    justifyContent: "center" as const,
  };

  if (failed || !uri) {
    return (
      <View style={frame}>
        <Text style={{ fontSize: size * 0.42, ...Weight.bold, color: theme.primary }}>
          {host.slice(0, 1).toUpperCase()}
        </Text>
      </View>
    );
  }

  return (
    <View style={frame}>
      <Image
        testID="search-source-favicon"
        source={{ uri }}
        style={{ width: size - ring * 2, height: size - ring * 2 }}
        contentFit="contain"
        cachePolicy="memory-disk"
        onError={() => setFailed(true)}
      />
    </View>
  );
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    chip: {
      alignSelf: "flex-start",
      flexDirection: "row",
      alignItems: "center",
      gap: Space.xs,
      marginTop: Space.sm,
      paddingLeft: Space.sm,
      paddingRight: Space.sm,
      paddingVertical: Space.xs,
      borderRadius: Radius.full,
      backgroundColor: theme.surface,
    },
    chipLabel: {
      ...Type.secondary,
      ...Weight.medium,
      color: theme.textSecondary,
    },
    iconCluster: {
      flexDirection: "row",
      alignItems: "center",
    },
    iconSlot: {
      position: "relative",
    },
    iconOverlap: {
      marginLeft: -7,
    },
  });
}

function makeSheetStyles(theme: Theme) {
  return StyleSheet.create({
    sheet: {
      paddingTop: Space.xxs,
    },
    list: {
      paddingHorizontal: Space.sm,
    },
    title: {
      ...Type.navTitle,
      color: theme.text,
      paddingHorizontal: Space.gutter,
      marginBottom: Space.xs,
    },
    row: {
      flexDirection: "row",
      alignItems: "flex-start",
      gap: Space.sm,
      paddingHorizontal: Space.xs,
      paddingVertical: Space.sm,
    },
    rowBorder: {
      borderBottomWidth: StyleSheet.hairlineWidth,
      borderBottomColor: theme.border,
    },
    body: {
      flex: 1,
      gap: 2,
    },
    domain: {
      ...Type.caption,
      ...Weight.semibold,
      color: theme.textSecondary,
    },
    rowTitle: {
      ...Type.callout,
      color: theme.text,
    },
    snippet: {
      ...Type.compact,
      color: theme.textSecondary,
      marginTop: 2,
    },
  });
}
