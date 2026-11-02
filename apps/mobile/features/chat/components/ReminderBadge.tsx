import { type StyleProp, type ViewStyle } from "react-native";

import { CountBadge } from "@/ui/feedback/CountBadge";

type Props = {
  count: number;
  style?: StyleProp<ViewStyle>;
};

export function ReminderBadge({ count, style }: Props) {
  return (
    <CountBadge
      count={count}
      max={99}
      tone="danger"
      bordered
      style={style}
    />
  );
}
