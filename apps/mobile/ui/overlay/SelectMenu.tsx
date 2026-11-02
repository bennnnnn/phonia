import type { RefObject } from "react";
import type { View } from "react-native";

import type { IconName } from "../icons/names";
import { Menu } from "./Menu";

export type SelectOption = {
  key: string;
  label: string;
  icon?: IconName;
  /** A color dot in place of an icon. */
  swatch?: string;
  disabled?: boolean;
  /** Short note shown on the right (e.g. "Pro" on a locked choice). */
  note?: string;
};

type Props = {
  visible: boolean;
  options: SelectOption[];
  selectedKey: string;
  onSelect: (key: string) => void;
  onClose: () => void;
  /** The row that opened the choices. Without one the menu centers. */
  anchorRef?: RefObject<View | null>;
  title?: string;
  /** Locks every choice (e.g. while the last pick saves). */
  disabled?: boolean;
  testID?: string;
};

/**
 * Pick one of a few: appearance, tone, language, reminder lead, repeat…
 * The popover opens from the row, checks the current choice, and closes on
 * pick. Picking the current choice again just closes.
 */
export function SelectMenu({
  visible,
  options,
  selectedKey,
  onSelect,
  onClose,
  anchorRef,
  title,
  disabled = false,
  testID,
}: Props) {
  return (
    <Menu
      visible={visible}
      onClose={onClose}
      anchorRef={anchorRef}
      title={title}
      selectable
      testID={testID ?? "select-menu"}
      items={options.map((option) => ({
        key: option.key,
        label: option.label,
        icon: option.icon,
        swatch: option.swatch,
        disabled: disabled || option.disabled,
        selected: option.key === selectedKey,
        trailing: option.key === selectedKey ? undefined : option.note,
        onPress: () => {
          if (option.key !== selectedKey) onSelect(option.key);
        },
      }))}
    />
  );
}
