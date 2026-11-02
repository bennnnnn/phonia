import { useTranslation } from "react-i18next";

import { SkeletonList } from "@/ui/feedback/SkeletonLoader";
import { StateView } from "@/ui/feedback/StateView";
import { DrawerSearchResultsChrome } from "@/features/search/components/DrawerSearchResults";

type Props = {
  loading: boolean;
  error: boolean;
  activeChatCount: number;
  searchOpen: boolean;
  onRetry: () => void;
  onRetrySearch: () => void;
  hasSearchQuery: boolean;
  searchLoading: boolean;
  searchError: boolean;
  searchResultCount: number;
};

export function DrawerListHeader({
  loading,
  error,
  activeChatCount,
  searchOpen,
  onRetry,
  onRetrySearch,
  hasSearchQuery,
  searchLoading,
  searchError,
  searchResultCount,
}: Props) {
  const { t } = useTranslation();

  return (
    <>
      {loading && activeChatCount === 0 && !searchOpen ? (
        <SkeletonList count={4} />
      ) : error && activeChatCount === 0 && !searchOpen ? (
        <StateView
          variant="error"
          compact
          icon="cloud-off"
          message={t("drawer.cant_reach")}
          onRetry={onRetry}
          retryLabel={t("common.retry")}
        />
      ) : null}
      {searchOpen ? (
        <DrawerSearchResultsChrome
          hasSearchQuery={hasSearchQuery}
          searchLoading={searchLoading}
          searchError={searchError}
          resultCount={searchResultCount}
          onRetry={onRetrySearch}
        />
      ) : null}
    </>
  );
}
