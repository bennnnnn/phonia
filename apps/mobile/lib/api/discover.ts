import { request } from "@/lib/api/client";
import type { ModelInfo, Usage } from "@/lib/api/types";

export const discoverApi = {
  todayUsage: (token: string) => request<Usage>("/chats/usage/today", token),
  listModels: (token: string) => request<ModelInfo[]>("/models", token),
};
