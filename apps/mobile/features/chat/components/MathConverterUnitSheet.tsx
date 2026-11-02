import { useMemo } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useTranslation } from "react-i18next";

import { Sheet } from "@/ui/overlay/Sheet";
import { Icon } from "@/ui/icons/Icon";
import { Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import {
  UNIT_CATEGORIES,
  UNITS_BY_CATEGORY,
  type UnitCategory,
} from "@/features/chat/model/unitConverter";
import { IconSize } from "@/ui/icons/sizes";

/** Fixed so Length / Temp / Volume don't bounce the sheet when the list length changes. */
const UNIT_PICKER_SHEET_HEIGHT = 520;
const UNIT_PICKER_LIST_HEIGHT = 360;

type Props = {
  visible: boolean;
  category: UnitCategory;
  selectedId: string;
  onClose: () => void;
  onPickCategory: (category: UnitCategory) => void;
  onPickUnit: (id: string) => void;
};

export function MathConverterUnitSheet({
  visible,
  category,
  selectedId,
  onClose,
  onPickCategory,
  onPickUnit,
}: Props) {
  const { t } = useTranslation();
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);

  return (
    <Sheet
      visible={visible}
      onClose={onClose}
      variant="bottom"
      withHandle
      floating
      minBottomPadding={12}
      contentContainerStyle={s.sheet}
    >
      <View style={s.header}>
        <Text style={s.title} accessibilityRole="header">{t("chat.math_converter_select_unit")}</Text>
        <Pressable
          onPress={onClose}
          style={s.close}
          testID="math-converter-picker-close"
          accessibilityRole="button"
          accessibilityLabel={t("common.close")}
        >
          <Icon name="close" size={IconSize.sm} color={theme.textSecondary} />
        </Pressable>
      </View>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={s.cats}
      >
        {UNIT_CATEGORIES.map((id) => {
          const selected = id === category;
          return (
            <Pressable
              key={id}
              onPress={() => onPickCategory(id)}
              style={[s.cat, selected && s.catSelected]}
              testID={`math-converter-cat-${id}`}
              accessibilityRole="button"
              accessibilityState={{ selected }}
            >
              <Text style={[s.catLabel, selected && s.catLabelSelected]}>
                {t(`chat.math_converter_cat_${id}`)}
              </Text>
            </Pressable>
          );
        })}
      </ScrollView>
      <ScrollView
        style={s.list}
        testID="math-converter-picker"
        keyboardShouldPersistTaps="handled"
      >
        {UNITS_BY_CATEGORY[category].map((unit) => {
          const selected = unit.id === selectedId;
          return (
            <Pressable
              key={unit.id}
              onPress={() => onPickUnit(unit.id)}
              style={s.unitRow}
              testID={`math-converter-unit-${unit.id}`}
              accessibilityRole="radio"
              accessibilityState={{ checked: selected }}
            >
              <Text style={[s.unitName, selected && s.unitNameSelected]}>
                {unit.name} ({unit.symbol})
              </Text>
              <View style={[s.radio, selected && s.radioOn]} />
            </Pressable>
          );
        })}
      </ScrollView>
    </Sheet>
  );
}

const makeStyles = (theme: Theme) =>
  StyleSheet.create({
    sheet: {
      backgroundColor: theme.surface,
      paddingHorizontal: Space.md,
      paddingTop: Space.xs,
      paddingBottom: Space.xs,
      height: UNIT_PICKER_SHEET_HEIGHT,
    },
    header: {
      flexDirection: "row",
      alignItems: "center",
      justifyContent: "space-between",
      marginBottom: Space.xs,
    },
    title: { ...Type.navTitle, color: theme.text },
    close: {
      minWidth: Space.minTouch,
      minHeight: Space.minTouch,
      alignItems: "center",
      justifyContent: "center",
    },
    cats: { gap: Space.xs, paddingBottom: Space.sm },
    cat: {
      paddingHorizontal: Space.sm,
      minHeight: Space.minTouch,
      justifyContent: "center",
      borderRadius: Radius.xl,
      backgroundColor: theme.surfaceAlt,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: theme.border,
    },
    catSelected: { backgroundColor: theme.primaryLight, borderColor: theme.primary },
    catLabel: { ...Type.label, color: theme.textSecondary },
    catLabelSelected: { color: theme.primary },
    list: { height: UNIT_PICKER_LIST_HEIGHT },
    unitRow: {
      flexDirection: "row",
      alignItems: "center",
      justifyContent: "space-between",
      paddingVertical: Space.sm,
      borderBottomWidth: StyleSheet.hairlineWidth,
      borderBottomColor: theme.border,
    },
    unitName: { ...Type.body, color: theme.text },
    unitNameSelected: { color: theme.primary, ...Weight.bold },
    radio: {
      width: 18,
      height: 18,
      borderRadius: Radius.full,
      borderWidth: 1.5,
      borderColor: theme.border,
    },
    radioOn: { borderColor: theme.primary, backgroundColor: theme.primary },
  });
