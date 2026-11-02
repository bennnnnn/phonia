import { StyleSheet } from "react-native";

import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import type { Theme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";

export function makeTodosStyles(C: Theme) {
  return StyleSheet.create({
    root: { flex: 1, backgroundColor: C.bg },
    dayHeading: {
      ...Type.body,
      ...Weight.bold,
      color: C.text,
    },
    list: { flex: 1 },
    listEmpty: { flexGrow: 1 },
    // paddingBottom comes from addFabClearance, which knows the safe area.
    listContent: { paddingTop: Space.xs },
    sectionHeader: {
      paddingHorizontal: Space.md,
      paddingTop: Space.sm,
      paddingBottom: Space.xs,
    },
    sectionHeaderFirst: {
      paddingTop: Space.lg,
    },
    sectionHeading: {
      ...Type.label,
      color: C.textSecondary,
    },
    daySheet: {
      marginHorizontal: Space.md,
      marginBottom: Space.sm,
      borderRadius: Radius.xl,
      backgroundColor: C.surface,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: C.border,
      overflow: "hidden",
    },
    dayClash: {
      paddingLeft: Space.lg + Space.xl,
      paddingRight: Space.md,
      paddingTop: Space.sm,
      paddingBottom: Space.xxs,
      gap: Space.xxs,
    },
    dayClashText: { ...Type.secondary, color: C.textSecondary },
    sheetRule: {
      height: StyleSheet.hairlineWidth,
      marginLeft: Space.sm + Space.minTouch,
      marginRight: Space.md,
      backgroundColor: C.border,
    },
    todoRow: {
      flexDirection: "row",
      alignItems: "center",
      paddingLeft: Space.sm,
      paddingRight: Space.md,
      paddingVertical: Space.xs,
    },
    todoRowHighlighted: {
      backgroundColor: C.primaryLight,
    },
    swipeContainer: {
      overflow: "hidden",
    },
    swipeDeleteAction: {
      width: 80,
      backgroundColor: C.danger,
      alignItems: "center",
      justifyContent: "center",
      gap: 2,
    },
    swipeDeleteText: {
      ...Type.caption,
      ...Weight.semibold,
      color: C.onPrimary,
    },
    checkbox: {
      width: Space.minTouch,
      minHeight: Space.minTouch,
      alignItems: "center",
      justifyContent: "center",
    },
    todoMain: { flex: 1, gap: Space.xxs },
    todoText: { ...Type.navTitle, color: C.text },
    todoMeta: { ...Type.meta, color: C.textSecondary },
    todoTimeWrap: {
      flexDirection: "row",
      alignItems: "center",
      gap: Space.xxs,
      marginLeft: Space.sm,
    },
    todoTime: {
      ...Type.label,
      fontVariant: ["tabular-nums"],
    },
    todoTimeToday: { color: C.primary },
    todoTimeOverdue: { color: C.danger },
    /**
     * Grey and danger ink on a lit row's primaryLight, which carries text and primary ink
     * (accent.test): textSecondary is under 4.5:1 there in dark sapphire, orchid, berry and
     * graphite. An overdue time keeps the danger mark beside it.
     */
    todoInkLit: { color: C.text },
    todoTimeLater: { color: C.textSecondary },
    overlapNote: {
      flexDirection: "row",
      alignItems: "flex-start",
      gap: Space.xxs,
      marginTop: Space.sm,
      padding: Space.sm,
      borderRadius: Radius.sm,
      backgroundColor: C.dangerLight,
    },
    overlapNoteText: { flex: 1, ...Type.caption, ...Weight.regular, color: C.danger },
    detailPage: { flex: 1, zIndex: 0, backgroundColor: C.surface },
    reviewTitle: {
      ...Type.display,
      color: C.text,
      backgroundColor: "transparent",
      borderWidth: 0,
      paddingVertical: Space.xs,
      marginTop: Space.sm,
    },
    reviewChip: {
      alignSelf: "flex-start",
      flexDirection: "row",
      alignItems: "center",
      gap: Space.xxs,
      paddingHorizontal: Space.sm,
      paddingVertical: Space.xs,
      borderRadius: Radius.full,
      backgroundColor: C.bg,
    },
    reviewChipText: { ...Type.secondary, color: C.text },
    reviewList: { marginTop: Space.lg, gap: Space.xxs },
    todoDone: {
      ...Type.body,
      color: C.textSecondary,
      textDecorationLine: "line-through",
    },
    formLabel: { ...Type.label, color: C.textSecondary },
    fieldGap: { marginTop: Space.md },
    dateRow: {
      flexDirection: "row",
      alignItems: "center",
      gap: Space.xs,
    },
    fieldGrow: { flex: 1 },
    todoRowSelected: { backgroundColor: C.primaryLight },
    filterEmpty: {
      ...Type.body,
      color: C.textSecondary,
      textAlign: "center",
      padding: Space.lg,
    },
    olderFooter: {
      alignItems: "center",
      paddingVertical: Space.md,
    },
    selectionBar: {
      position: "absolute",
      left: Space.md,
      right: Space.md,
      flexDirection: "row",
      alignItems: "center",
      gap: Space.sm,
      minHeight: Space.minTouch,
      paddingHorizontal: Space.md,
      paddingVertical: Space.xs,
      borderRadius: Radius.lg,
      backgroundColor: C.bg,
    },
    selectionCount: { flex: 1, ...Type.secondary, color: C.textSecondary },
    selectionAction: { ...Type.secondary, ...Weight.semibold, color: C.primary },
    selectionDelete: { ...Type.secondary, ...Weight.semibold, color: C.danger },
    selectionDisabled: { color: C.textDisabled },
    removeDateButton: {
      minWidth: Space.minTouch,
      minHeight: Space.minTouch,
      alignItems: "center",
      justifyContent: "center",
    },
    repeatField: {
      flexDirection: "row",
      alignItems: "center",
      justifyContent: "space-between",
      gap: Space.xs,
      minHeight: Space.minTouch,
      backgroundColor: C.surface,
      borderRadius: Radius.md,
      paddingHorizontal: Space.md,
      paddingVertical: Space.sm,
      borderWidth: 1,
      borderColor: C.border,
    },
    repeatFieldText: {
      flex: 1,
      ...Type.navTitle,
      color: C.text,
    },
    sheet: {
      backgroundColor: C.surface,
      borderTopLeftRadius: Radius.sheet,
      borderTopRightRadius: Radius.sheet,
    },
    sheetBody: { padding: Space.md, paddingBottom: Space.xl, gap: Space.xs },
  });
}
