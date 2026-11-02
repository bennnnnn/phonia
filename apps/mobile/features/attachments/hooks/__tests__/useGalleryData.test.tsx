import React from "react";
import { Text } from "react-native";
import { act, render, waitFor } from "@testing-library/react-native";

import { useGalleryData } from "@/features/attachments/hooks/useGalleryData";
import type { AttachmentListItem } from "@/lib/api";
import type { GalleryFilter } from "@/features/attachments/model/gallery";

import { api } from "@/lib/api";
import { invalidateGalleryCache, setGalleryPage } from "@/features/attachments/model/galleryListCache";
jest.mock("@/lib/auth", () => ({
  getSessionGeneration: () => 0,
  requireTokenSession: jest.fn(),
  SessionChangedError: class SessionChangedError extends Error {},
}));

jest.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ token: "tok" }),
}));

jest.mock("expo-router", () => {
  const { useEffect } = jest.requireActual<typeof import("react")>("react");
  return {
    useFocusEffect: (callback: () => void) => {
      useEffect(callback, [callback]);
    },
  };
});

jest.mock("@/lib/api", () => ({
  api: {
    listAttachments: jest.fn(),
  },
}));

function item(id: string): AttachmentListItem {
  return {
    id,
    content_type: "image/png",
    size_bytes: 12,
    download_url: `/attachments/${id}/file`,
    source: "upload",
    created_at: "2026-01-01T00:00:00.000Z",
  };
}

let latest: ReturnType<typeof useGalleryData> | null = null;
let setProbeFilter: ((next: GalleryFilter) => void) | null = null;

function Probe({ filter = "all" }: { filter?: GalleryFilter }) {
  const result = useGalleryData(filter, "");
  React.useLayoutEffect(() => {
    latest = result;
  }, [result]);
  return <Text>{result.items.map((row) => row.id).join(",")}</Text>;
}

function FilterSwitchProbe() {
  const [filter, setFilter] = React.useState<GalleryFilter>("files");
  const result = useGalleryData(filter, "");
  React.useLayoutEffect(() => {
    setProbeFilter = setFilter;
    latest = result;
  }, [result]);
  return <Text>{result.items.map((row) => row.id).join(",")}</Text>;
}

describe("useGalleryData", () => {
  beforeEach(() => {
    latest = null;
    setProbeFilter = null;
    jest.clearAllMocks();
    invalidateGalleryCache();
    (api.listAttachments as jest.Mock).mockReset();
  });

  it("skips a second silent reset while the list is still fresh", async () => {
    const list = api.listAttachments as jest.Mock;
    list.mockResolvedValue({ items: [item("a")], next_cursor: null });

    await act(async () => {
      render(<Probe />);
    });
    await waitFor(() => {
      expect(latest?.items.map((row) => row.id)).toEqual(["a"]);
    });
    expect(list).toHaveBeenCalledTimes(1);

    await act(async () => {
      await latest?.retry();
    });
    expect(list).toHaveBeenCalledTimes(1);
  });

  it("keeps the grid when a later page fails", async () => {
    const list = api.listAttachments as jest.Mock;
    list
      .mockResolvedValueOnce({ items: [item("a"), item("b")], next_cursor: "next" })
      .mockRejectedValueOnce(new Error("network"));

    await act(async () => {
      render(<Probe />);
    });
    await waitFor(() => {
      expect(latest?.items.map((row) => row.id)).toEqual(["a", "b"]);
    });

    await act(async () => {
      latest?.loadMore();
    });
    await waitFor(() => {
      expect(list).toHaveBeenCalledTimes(2);
    });
    expect(latest?.items.map((row) => row.id)).toEqual(["a", "b"]);
    expect(latest?.error).toBe(false);
  });

  it("refetches when the visible filter changes even if another tab is fresh", async () => {
    const list = api.listAttachments as jest.Mock;
    list
      .mockResolvedValueOnce({ items: [item("pdf-1")], next_cursor: null })
      .mockResolvedValueOnce({ items: [item("img-1")], next_cursor: null });

    await act(async () => {
      render(<FilterSwitchProbe />);
    });
    await waitFor(() => {
      expect(latest?.items.map((row) => row.id)).toEqual(["pdf-1"]);
    });

    await act(async () => {
      setProbeFilter?.("all");
    });
    await waitFor(() => {
      expect(latest?.items.map((row) => row.id)).toEqual(["img-1"]);
    });
    expect(list).toHaveBeenCalledTimes(2);
  });

  it("hydrates from cache without refetching while fresh", async () => {
    const list = api.listAttachments as jest.Mock;
    setGalleryPage("all", "", { items: [item("cached")], hasMore: false });

    await act(async () => {
      render(<Probe />);
    });
    await waitFor(() => {
      expect(latest?.items.map((row) => row.id)).toEqual(["cached"]);
    });
    expect(list).not.toHaveBeenCalled();
  });

  it("restores a fresh tab snapshot without refetching", async () => {
    const list = api.listAttachments as jest.Mock;
    list
      .mockResolvedValueOnce({ items: [item("pdf-1")], next_cursor: null })
      .mockResolvedValueOnce({ items: [item("img-1")], next_cursor: null });

    await act(async () => {
      render(<FilterSwitchProbe />);
    });
    await waitFor(() => {
      expect(latest?.items.map((row) => row.id)).toEqual(["pdf-1"]);
    });

    await act(async () => {
      setProbeFilter?.("all");
    });
    await waitFor(() => {
      expect(latest?.items.map((row) => row.id)).toEqual(["img-1"]);
    });

    await act(async () => {
      setProbeFilter?.("files");
    });
    await waitFor(() => {
      expect(latest?.items.map((row) => row.id)).toEqual(["pdf-1"]);
    });
    expect(list).toHaveBeenCalledTimes(2);
  });

  it("drops a missing attachment from the grid", async () => {
    const list = api.listAttachments as jest.Mock;
    list.mockResolvedValue({ items: [item("a"), item("b")], next_cursor: null });

    await act(async () => {
      render(<Probe />);
    });
    await waitFor(() => {
      expect(latest?.items.map((row) => row.id)).toEqual(["a", "b"]);
    });

    await act(async () => {
      latest?.removeItem("a");
    });
    expect(latest?.items.map((row) => row.id)).toEqual(["b"]);
  });

  it("appends the next page after loadMore", async () => {
    const list = api.listAttachments as jest.Mock;
    list
      .mockResolvedValueOnce({ items: [item("a")], next_cursor: "next" })
      .mockResolvedValueOnce({ items: [item("b")], next_cursor: null });

    await act(async () => {
      render(<Probe />);
    });
    await waitFor(() => {
      expect(latest?.items.map((row) => row.id)).toEqual(["a"]);
    });

    await act(async () => {
      latest?.loadMore();
    });
    await waitFor(() => {
      expect(latest?.items.map((row) => row.id)).toEqual(["a", "b"]);
    });
  });
});


it("ignores a slow tab request after switching to a fresh cached tab", async () => {
  invalidateGalleryCache();
  setGalleryPage("files", "", { items: [item("cached-file")], hasMore: false });
  let finish!: (value: unknown) => void;
  (api.listAttachments as jest.Mock).mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
  const view = await render(<Probe filter="all" />);
  await view.rerender(<Probe filter="files" />);
  await act(async () => { finish({ items: [item("old-image")], next_cursor: null }); });
  expect(latest?.items.map((row) => row.id)).toEqual(["cached-file"]);
});

it("offers an explicit next-page retry without discarding existing rows", async () => {
  invalidateGalleryCache();
  (api.listAttachments as jest.Mock)
    .mockResolvedValueOnce({ items: [item("a")], next_cursor: "next" })
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValueOnce({ items: [item("b")], next_cursor: null });
  await render(<Probe />);
  await act(async () => { latest?.loadMore(); });
  expect(latest?.items.map((row) => row.id)).toEqual(["a"]);
  expect(latest?.pageError).toBe(true);
  await act(async () => { await latest?.retryPage(); });
  expect(latest?.items.map((row) => row.id)).toEqual(["a", "b"]);
  expect(latest?.pageError).toBe(false);
});

describe("pull to refresh", () => {
  beforeEach(() => {
    latest = null;
    jest.clearAllMocks();
    invalidateGalleryCache();
    (api.listAttachments as jest.Mock).mockReset();
  });

  it("reports a failure while it keeps the items on screen", async () => {
    const list = api.listAttachments as jest.Mock;
    list
      .mockResolvedValueOnce({ items: [item("a")], next_cursor: null })
      .mockRejectedValueOnce(new Error("offline"));

    await act(async () => {
      render(<Probe />);
    });
    await waitFor(() => {
      expect(latest?.items.map((row) => row.id)).toEqual(["a"]);
    });

    let ok: boolean | undefined;
    await act(async () => {
      ok = await latest?.refresh();
    });
    expect(ok).toBe(false);
    expect(latest?.items.map((row) => row.id)).toEqual(["a"]);
    expect(latest?.pullRefreshing).toBe(false);
  });

  it("reports a success", async () => {
    const list = api.listAttachments as jest.Mock;
    list
      .mockResolvedValueOnce({ items: [item("a")], next_cursor: null })
      .mockResolvedValueOnce({ items: [item("a"), item("b")], next_cursor: null });

    await act(async () => {
      render(<Probe />);
    });
    await waitFor(() => {
      expect(latest?.items.map((row) => row.id)).toEqual(["a"]);
    });
    let ok: boolean | undefined;
    await act(async () => {
      ok = await latest?.refresh();
    });
    expect(ok).toBe(true);
    expect(latest?.items.map((row) => row.id)).toEqual(["a", "b"]);
  });
});
