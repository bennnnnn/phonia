import { request } from "@/lib/api/client";

export const pushApi = {
  registerPushToken: (
    token: string,
    body: {
      expo_push_token: string;
      platform: string;
      device_id?: string;
      android_channels?: "split" | "tone";
    },
  ) =>
    request<void>("/users/push-token", token, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  unregisterPushToken: (token: string, body: { expo_push_token: string }) =>
    request<void>("/users/push-token", token, {
      method: "DELETE",
      body: JSON.stringify(body),
    }),
};
