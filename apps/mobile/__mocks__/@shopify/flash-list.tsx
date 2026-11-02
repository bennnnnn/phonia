// Manual mock for @shopify/flash-list in Jest. The real package ships
// untranspiled ESM and pulls native layout code that cannot load in this
// environment, so rendering tests mount this synchronous fragment version.
// Explicit jest.mock("@shopify/flash-list", ...) in a test file still wins.
import React from "react";

type MockProps = {
  data?: unknown[] | null;
  renderItem?: (args: { item: unknown; index: number }) => React.ReactNode;
  keyExtractor?: (item: unknown, index: number) => string;
  ListHeaderComponent?: React.ReactNode;
  ListFooterComponent?: React.ReactNode;
  ListEmptyComponent?: React.ReactNode;
};

export function FlashList({
  data,
  renderItem,
  keyExtractor,
  ListHeaderComponent,
  ListFooterComponent,
  ListEmptyComponent,
}: MockProps) {
  const items = (data ?? []).map((item, index) =>
    React.createElement(
      React.Fragment,
      { key: keyExtractor?.(item, index) ?? String(index) },
      renderItem?.({ item, index }),
    ),
  );
  return React.createElement(
    React.Fragment,
    null,
    ListHeaderComponent ?? null,
    ...items,
    (data?.length ?? 0) > 0 ? null : (ListEmptyComponent ?? null),
    ListFooterComponent ?? null,
  );
}
