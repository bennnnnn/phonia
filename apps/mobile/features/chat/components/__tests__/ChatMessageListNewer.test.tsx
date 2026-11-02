import { fireEvent, render, screen } from "@testing-library/react-native";
import { Text } from "react-native";

import { ChatMessageList } from "@/features/chat/components/ChatMessageList";
import type { Message } from "@/lib/api";

jest.mock("@/features/home/components/HomeStarters", () => ({ HomeStarters: () => null }));

const message: Message = { id: "m1", role: "user", content: "hello", model: null, created_at: "t" };

function list(newerPage: { loading: boolean; load: () => Promise<void> } | null) {
  return (
    <ChatMessageList
      listRef={{ current: null }}
      messages={[message]}
      headerInset={0}
      listBottomPad={0}
      hasMoreOlder={false}
      loadingOlder={false}
      newerPage={newerPage}
      chatLoading={false}
      emptyHeight={100}
      renderItem={({ item }) => <Text>{item.content}</Text>}
      onLoadOlder={() => undefined}
      onScroll={() => undefined}
      onScrollEnd={() => undefined}
    />
  );
}

it("offers the next page below a window around a search hit (NET-18)", async () => {
  const load = jest.fn(async () => undefined);
  await render(list({ loading: false, load }));
  await fireEvent.press(screen.getByLabelText("chat.load_newer"));
  expect(load).toHaveBeenCalledTimes(1);
});

it("offers nothing below a thread that ends at the newest message", async () => {
  await render(list(null));
  expect(screen.queryByLabelText("chat.load_newer")).toBeNull();
});
