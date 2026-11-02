import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { ScrollView, StyleSheet, type View } from "react-native";
import { type Href, Redirect, router } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTranslation } from "react-i18next";

import { useAuth } from "@/contexts/AuthContext";
import { useActionFeedbackOptional } from "@/contexts/actionFeedbackCore";
import { reportRecoverableError } from "@/lib/reportRecoverableError";
import { Space } from "@/lib/space";
import { useTheme } from "@/lib/theme";
import type { IconName } from "@/ui/icons/names";
import { ListGroup } from "@/ui/list/ListGroup";
import { ListRow } from "@/ui/list/ListRow";
import { confirmDialog, type ConfirmOptions } from "@/ui/overlay/dialogs";
import { SelectMenu, type SelectOption } from "@/ui/overlay/SelectMenu";

/**
 * The Settings kit: one page layout, one group and four rows, all drawn by
 * the app's ListRow and ListGroup. Every Settings screen builds from these.
 */

const layout = StyleSheet.create({
  section: { marginTop: Space.lg },
  content: { paddingHorizontal: Space.md, paddingTop: Space.xs },
});

/** Padding for a Settings list; FlashList pages pass it as contentContainerStyle. */
export function useSettingsContentStyle(options?: { underStatusBar?: boolean }) {
  const insets = useSafeAreaInsets();
  return [
    layout.content,
    options?.underStatusBar ? { paddingTop: insets.top + Space.md } : null,
    { paddingBottom: insets.bottom + Space.lg },
  ];
}

/**
 * A Settings page: sends a signed-out visitor to login, then scrolls its
 * groups with the shared padding. `underStatusBar` is for the page without
 * a header (Settings home).
 */
export function SettingsPage({
  children,
  underStatusBar,
}: {
  children: ReactNode;
  underStatusBar?: boolean;
}) {
  const { token } = useAuth();
  const theme = useTheme();
  const contentStyle = useSettingsContentStyle({ underStatusBar });
  if (!token) return <Redirect href="/login" />;
  return (
    <ScrollView style={{ flex: 1, backgroundColor: theme.bg }} contentContainerStyle={contentStyle}>
      {children}
    </ScrollView>
  );
}

/** Rows under an optional heading, a thin gap between each. */
export function SettingsGroup({ label, children }: { label?: string; children: ReactNode }) {
  return (
    <ListGroup label={label} spaced style={layout.section}>
      {children}
    </ListGroup>
  );
}

type RowBase = {
  title: string;
  subtitle?: string;
  value?: string;
  icon?: IconName;
  leading?: ReactNode;
  disabled?: boolean;
  busy?: boolean;
  accessibilityHint?: string;
};

function rowLabel(title: string, value?: string): string {
  return value ? `${title}, ${value}` : title;
}

/**
 * A row you tap. With `href` it opens that page and shows a chevron;
 * `onPress` still runs first (to prefetch, say). A row that navigates in
 * its own `onPress` passes `chevron`.
 */
export function SettingsLinkRow({
  href,
  chevron,
  onPress,
  danger,
  accent,
  ...row
}: RowBase & {
  href?: Href;
  chevron?: boolean;
  onPress?: () => void;
  danger?: boolean;
  accent?: boolean;
}) {
  return (
    <ListRow
      {...row}
      danger={danger}
      accent={accent}
      accessory={href || chevron ? "chevron" : undefined}
      accessibilityLabel={rowLabel(row.title, row.value)}
      onPress={() => {
        onPress?.();
        if (href) router.push(href);
      }}
    />
  );
}

/** A row that only shows a value. */
export function SettingsValueRow(row: Omit<RowBase, "disabled" | "busy" | "accessibilityHint">) {
  return <ListRow {...row} />;
}

export function SettingsSwitchRow({
  value,
  onValueChange,
  ...row
}: Omit<RowBase, "value"> & { value: boolean; onValueChange: (next: boolean) => void }) {
  return <ListRow {...row} switchValue={value} onSwitchChange={onValueChange} />;
}

/**
 * A row that opens its choices in a popover anchored to it (never inline;
 * see chat-ux-bans §13). It owns the open state.
 */
export function SettingsMenuRow<K extends string>({
  options,
  selectedKey,
  onSelect,
  ...row
}: RowBase & {
  options: readonly (SelectOption & { key: K })[];
  selectedKey: K;
  onSelect: (key: K) => void;
}) {
  const [open, setOpen] = useState(false);
  const rowRef = useRef<View>(null);
  return (
    <>
      <ListRow
        {...row}
        ref={rowRef}
        expanded={open}
        accessibilityLabel={rowLabel(row.title, row.value)}
        onPress={() => setOpen(true)}
      />
      <SelectMenu
        visible={open}
        anchorRef={rowRef}
        options={[...options]}
        selectedKey={selectedKey}
        disabled={row.disabled || row.busy}
        onClose={() => setOpen(false)}
        onSelect={(key) => {
          const option = options.find((candidate) => candidate.key === key);
          if (option) onSelect(option.key);
        }}
      />
    </>
  );
}

/**
 * Runs one Settings action at a time: asks first when given `confirm`,
 * marks which action is busy, and reports a failure without throwing.
 * Resolves true when the action ran and succeeded.
 */
export function useSettingsAction() {
  const { t } = useTranslation();
  const feedback = useActionFeedbackOptional();
  const [busy, setBusy] = useState<string | null>(null);
  const running = useRef(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const run = useCallback(
    async (
      key: string,
      action: () => Promise<unknown>,
      options?: { confirm?: ConfirmOptions; errorKey?: string },
    ): Promise<boolean> => {
      if (running.current) return false;
      if (options?.confirm && !(await confirmDialog(options.confirm))) return false;
      if (running.current || !mounted.current) return false;
      running.current = true;
      setBusy(key);
      try {
        await action();
        return true;
      } catch {
        if (mounted.current) reportRecoverableError(feedback, t(options?.errorKey ?? "common.error"));
        return false;
      } finally {
        running.current = false;
        if (mounted.current) setBusy(null);
      }
    },
    [feedback, t],
  );

  return { busy, run };
}
