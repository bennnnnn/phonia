import { useTranslation } from "react-i18next";

import { StateView } from "@/ui/feedback/StateView";

type Props = {
  error: boolean;
  onRetry: () => void;
  showEmpty: boolean;
};

/** Compact list state; the To-do page intentionally has no calendar wall. */
export function TodosListHeader({
  error,
  onRetry,
  showEmpty,
}: Props) {
  const { t } = useTranslation();

  return (
    <>
      {error ? (
        <StateView
          variant="error"
          title={t("common.error")}
          onRetry={onRetry}
          retryLabel={t("common.retry")}
        />
      ) : showEmpty ? (
        <StateView
          variant="empty"
          icon="check-circle"
          title={t("todos.empty_title")}
        />
      ) : null}
    </>
  );
}
