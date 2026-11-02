import { useMemo } from "react";
import { StyleSheet } from "react-native";
import { useTranslation } from "react-i18next";

import { ListRow } from "@/ui/list/ListRow";
import { Sheet } from "@/ui/overlay/Sheet";
import { selection } from "@/lib/haptics";
import { Space } from "@/lib/space";
import { type Theme, useTheme } from "@/lib/theme";

export type AttachmentSource =
  | "camera"
  | "photo"
  | "file"
  | "solve_math_camera";

type Props = {
  visible: boolean;
  onClose: () => void;
  onSelect: (source: AttachmentSource) => void;
};

/** Attach / math-scan source picker — same floating Sheet chrome as chat actions. */
export function AttachmentSourceSheet({ visible, onClose, onSelect }: Props) {
  const theme = useTheme();
  const { t } = useTranslation();
  const s = useMemo(() => makeStyles(theme), [theme]);

  const pick = (source: AttachmentSource) => {
    selection();
    onSelect(source);
  };

  return (
    <Sheet
      visible={visible}
      onClose={onClose}
      variant="bottom"
      withHandle
      floating
      embedded
      minBottomPadding={12}
      contentContainerStyle={s.panel}
    >
      <ListRow
        appearance="plain"
        icon="scan"
        title={t("chat.attach_solve_math_camera")}
        onPress={() => pick("solve_math_camera")}
        style={s.row}
      />
      <ListRow
        appearance="plain"
        icon="camera"
        title={t("chat.attach_camera")}
        onPress={() => pick("camera")}
        style={s.row}
      />
      <ListRow
        appearance="plain"
        icon="image"
        title={t("chat.attach_photo")}
        onPress={() => pick("photo")}
        style={s.row}
      />
      <ListRow
        appearance="plain"
        icon="file"
        title={t("chat.attach_file")}
        onPress={() => pick("file")}
        style={s.row}
      />
    </Sheet>
  );
}

function makeStyles(theme: Theme) {
  return StyleSheet.create({
    panel: { backgroundColor: theme.elevated },
    row: { minHeight: Space.xl + Space.gutter, paddingHorizontal: Space.gutter },
  });
}
