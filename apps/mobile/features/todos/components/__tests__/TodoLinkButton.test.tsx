import { fireEvent, render, waitFor } from "@testing-library/react-native";

import { TodoLinkButton } from "@/features/todos/components/TodoLinkButton";
import { tap } from "@/lib/haptics";

const mockPush = jest.fn();
jest.mock("expo-router", () => ({ router: { push: (path: string) => mockPush(path) } }));
jest.mock("@/lib/haptics", () => ({ tap: jest.fn() }));
jest.mock("@/ui/icons/Icon", () => ({ Icon: () => null }));

describe("TodoLinkButton", () => {
  it("opens To-do with one tap", async () => {
    const view = await render(<TodoLinkButton />);
    await fireEvent.press(view.getByText("todos.open_from_chat"));
    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/todos"));
    expect(tap).toHaveBeenCalledTimes(1);
  });
});
