import { useEffect, useRef, useState } from "react";
import type { View } from "react-native";
import { useNavigation } from "expo-router";
import { useTranslation } from "react-i18next";

import { HeaderButton } from "@/ui/controls/HeaderButton";
import { plainHeaderItems } from "@/ui/controls/StackBackButton";
import { Menu, type MenuEntry } from "@/ui/overlay/Menu";

/** The ⋯ at a memory page's top right: its page actions, "Clear all memories" last. */
export function MemoryHeaderMenu({ items }: { items: MenuEntry[] }) {
  const navigation = useNavigation();
  const { t } = useTranslation();
  const anchorRef = useRef<View>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const button = (
      <HeaderButton
        ref={anchorRef}
        icon="more-horizontal"
        variant="plain"
        accessibilityLabel={t("memory.menu")}
        onPress={() => setOpen(true)}
        testID="memory-menu"
      />
    );
    navigation.setOptions({
      headerRight: () => button,
      unstable_headerRightItems: () => plainHeaderItems(button),
    });
  }, [navigation, t]);

  return (
    <Menu
      visible={open}
      onClose={() => setOpen(false)}
      anchorRef={anchorRef}
      items={items.map((item) =>
        item === "separator"
          ? item
          : {
              ...item,
              onPress: () => {
                setOpen(false);
                item.onPress();
              },
            },
      )}
    />
  );
}
