import { useMemo } from "react";
import { StyleSheet, Text, View } from "react-native";

import { Space } from "@/lib/space";
import { Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";

/** Caption line under the header of a molecule card (formula, name, molar mass). */
export function MoleculeCaption({ text }: { text: string }) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  return (
    <View style={s.caption}>
      <Text style={s.captionText}>{text}</Text>
    </View>
  );
}

/** A quiet centred note in place of a drawing that could not be made. */
export function MoleculeNote({ text }: { text: string }) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  return (
    <View style={s.note}>
      <Text style={s.noteText}>{text}</Text>
    </View>
  );
}

function makeStyles(t: Theme) {
  return StyleSheet.create({
    caption: {
      paddingHorizontal: Space.sm + 2,
      paddingTop: Space.xs,
      backgroundColor: t.bg,
    },
    captionText: { ...Type.compact, ...Weight.semibold, color: t.textSecondary },
    note: {
      paddingHorizontal: Space.sm + 2,
      paddingVertical: Space.lg,
      backgroundColor: t.contentSurface,
      alignItems: "center",
    },
    noteText: { ...Type.compact, color: t.textTertiary, textAlign: "center" },
  });
}
