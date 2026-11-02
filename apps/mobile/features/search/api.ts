import { request } from "@/lib/api/client";
import type { Page, SearchResult } from "@/lib/api/types";

export const searchApi = {
  search: (
    token: string,
    q: string,
    limit = 20,
    init?: Pick<RequestInit, "signal">,
    cursor?: string,
  ) => {
    const params = new URLSearchParams({ q, limit: String(limit) });
    if (cursor) params.set("cursor", cursor);
    return request<Page<SearchResult>>(`/search?${params}`, token, init);
  },
};
