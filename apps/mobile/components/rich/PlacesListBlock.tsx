import { useMemo, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useTranslation } from "react-i18next";

import { Sheet } from "@/ui/overlay/Sheet";
import { Icon } from "@/ui/icons/Icon";
import { openPlaceLink } from "@/lib/places/openPlaceLink";
import { PlaceItem, resolvePlaceLinkUrl } from "@/lib/places/placesList";
import { Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";
import { IconSize } from "@/ui/icons/sizes";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";

type Props = {
  places: PlaceItem[];
};

export function PlacesListBlock({ places }: Props) {
  const { t } = useTranslation();
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const [selected, setSelected] = useState<PlaceItem | null>(null);

  if (places.length === 0) return null;

  return (
    <View style={s.list}>
      {places.map((place, index) => {
        return (
          <View key={`${place.name}-${index}`} style={s.row}>
            <Text style={s.index}>{index + 1}.</Text>
            <View style={s.body}>
              <Pressable
                onPress={() => setSelected(place)}
                accessibilityRole="button"
                accessibilityLabel={t("places.show_details_a11y", { name: place.name })}
              >
                <Text style={s.name} numberOfLines={2}>
                  {place.name}
                </Text>
              </Pressable>
              {place.note ? (
                <Text style={s.note} numberOfLines={3}>
                  {place.note}
                </Text>
              ) : null}
              <View style={s.metaRow}>
                {place.price ? <Text style={s.price}>{place.price}</Text> : null}
                {place.address ? (
                  <Text style={s.address} numberOfLines={2}>
                    {place.address}
                  </Text>
                ) : null}
              </View>
            </View>
          </View>
        );
      })}

      <PlaceDetailsSheet
        place={selected}
        onClose={() => setSelected(null)}
      />
    </View>
  );
}

function PlaceDetailsSheet({
  place,
  onClose,
}: {
  place: PlaceItem | null;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const theme = useTheme();
  const s = useMemo(() => makeSheetStyles(theme), [theme]);
  const visible = place !== null;

  const openInMaps = () => {
    if (!place) return;
    const url = resolvePlaceLinkUrl(place);
    void openPlaceLink(url, place.name);
  };

  return (
    <Sheet
      visible={visible}
      onClose={onClose}
      minBottomPadding={16}
      contentContainerStyle={s.sheet}
    >
      {place ? (
        <>
          <Text style={s.title} numberOfLines={3} accessibilityRole="header">
            {place.name}
          </Text>
          {place.note ? (
            <Text style={s.note} numberOfLines={5}>
              {place.note}
            </Text>
          ) : null}
          <View style={s.metaRow}>
            {place.price ? <Text style={s.price}>{place.price}</Text> : null}
            {place.address ? (
              <Text style={s.address} numberOfLines={3}>
                {place.address}
              </Text>
            ) : null}
          </View>
          <Pressable style={s.openBtn} onPress={openInMaps} accessibilityRole="button">
            <Icon name="map" size={IconSize.sm} color={theme.onPrimary} />
            <Text style={s.openBtnText}>{t("places.open_in_maps")}</Text>
          </Pressable>
        </>
      ) : null}
    </Sheet>
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    list: {
      marginVertical: Space.xs,
      gap: Space.sm,
    },
    row: {
      flexDirection: "row",
      alignItems: "flex-start",
      gap: Space.xs,
    },
    index: {
      width: 22,
      paddingTop: 1,
      ...Type.body,
      ...Weight.semibold,
      color: t.text,
    },
    body: {
      flex: 1,
      minWidth: 0,
      gap: Space.xxs,
    },
    name: {
      ...Type.body,
      ...Weight.semibold,
      color: t.text,
      textDecorationLine: "underline",
      textDecorationStyle: "dotted",
      textDecorationColor: t.textSecondary,
    },
    note: {
      ...Type.secondary,
      lineHeight: 20,
      color: t.textSecondary,
    },
    metaRow: {
      flexDirection: "row",
      flexWrap: "wrap",
      alignItems: "center",
      gap: Space.xs,
    },
    price: {
      ...Type.compact,
      ...Weight.semibold,
      color: t.textSecondary,
    },
    address: {
      flexShrink: 1,
      ...Type.compact,
      color: t.textTertiary,
    },
  });
}

function makeSheetStyles(t: Theme) {
  return StyleSheet.create({
    sheet: {
      paddingHorizontal: Space.gutter,
      gap: Space.sm,
    },
    title: {
      ...Type.h2,
      color: t.text,
    },
    note: {
      ...Type.callout,
      ...Weight.regular,
      color: t.textSecondary,
    },
    metaRow: {
      flexDirection: "row",
      flexWrap: "wrap",
      alignItems: "center",
      gap: Space.xs,
    },
    price: {
      ...Type.label,
      color: t.textSecondary,
    },
    address: {
      flexShrink: 1,
      ...Type.secondary,
      color: t.textTertiary,
    },
    openBtn: {
      flexDirection: "row",
      alignItems: "center",
      justifyContent: "center",
      gap: Space.xs,
      backgroundColor: t.primary,
      borderRadius: Radius.lg,
      paddingVertical: Space.sm,
      marginTop: Space.xs,
    },
    openBtnText: {
      ...Type.body,
      ...Weight.bold,
      color: t.onPrimary,
    },
  });
}
