import { chatsApi } from "@/features/chat/api";
import { request, requestRevalidated } from "@/lib/api/client";

jest.mock("@/lib/api/client", () => ({ request: jest.fn(), requestRevalidated: jest.fn() }));
let mockZone = "Asia/Kathmandu";
jest.mock("@/lib/deviceTimezone", () => ({ getDeviceTimezone: () => mockZone }));
beforeEach(() => {
  jest.resetAllMocks();
  mockZone = "Asia/Kathmandu";
});

// The server groups the drawer's days in the phone's zone, the one the phone files its own
// inserts in, not the profile's copy, which lags a flight (apps/api test_chat_list_zone.py).
it("reads the drawer's list in the phone's zone", async () => {
  await chatsApi.listChats("token");
  expect(requestRevalidated).toHaveBeenCalledWith("/chats?client_timezone=Asia%2FKathmandu", "token");
});

it("reads the older pages in the same zone, so they join the same headings", async () => {
  await chatsApi.listOlderChats("token", "2026-10-24T18:20:00+00:00|a b");
  expect(request).toHaveBeenCalledWith(
    "/chats?cursor=2026-10-24T18%3A20%3A00%2B00%3A00%7Ca+b&client_timezone=Asia%2FKathmandu",
    "token",
  );
});

it("reads a new zone at a new path: a list kept for the old one is never revalidated for it", async () => {
  await chatsApi.listChats("token");
  mockZone = "Pacific/Kiritimati";
  await chatsApi.listChats("token");
  const paths = jest.mocked(requestRevalidated).mock.calls.map(([path]) => path);
  expect(paths).toEqual(["/chats?client_timezone=Asia%2FKathmandu", "/chats?client_timezone=Pacific%2FKiritimati"]);
});
