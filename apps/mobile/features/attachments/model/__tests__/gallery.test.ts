import {
  COLUMN_THUMB_SIZE,
  GENERATED_FILE_STEM_MAX,
  contentTypeForFileName,
  extensionForContentType,
  galleryDisplayName,
  galleryEmptyKey,
  galleryFileName,
  galleryGridLayout,
  galleryImageIndex,
  galleryItemActions,
  galleryNeighborImageId,
  galleryImageItems,
  galleryListCacheKey,
  galleryListParams,
  galleryPressAction,
  galleryThumbSize,
  isGalleryImage,
  isReadableTextContentType,
  libraryOpenChatHref,
  mergeGalleryItems,
} from "@/features/attachments/model/gallery";

describe("gallery helpers", () => {
  it("opens images in the viewer and files for reading", () => {
    expect(isGalleryImage("image/png")).toBe(true);
    expect(isGalleryImage("application/pdf")).toBe(false);
    expect(galleryPressAction("image/jpeg")).toBe("view-image");
    expect(galleryPressAction("application/pdf")).toBe("open-file");
    expect(galleryPressAction("text/plain")).toBe("open-file");
  });

  it("pages Library photos without including files", () => {
    const items = [
      { id: "doc", content_type: "application/pdf" },
      { id: "one", content_type: "image/png" },
      { id: "two", content_type: "image/jpeg" },
    ] as never;
    const images = galleryImageItems(items);
    expect(images.map((item) => item.id)).toEqual(["one", "two"]);
    expect(galleryImageIndex(images, "two")).toBe(1);
    expect(isReadableTextContentType("text/plain")).toBe(true);
    expect(isReadableTextContentType("application/json")).toBe(true);
    expect(isReadableTextContentType("application/pdf")).toBe(false);
  });

  it("pushes the main chat route with returnTo=gallery so Back returns to Library", () => {
    expect(libraryOpenChatHref({ chat_id: null, message_id: "m1" })).toBeNull();
    expect(libraryOpenChatHref({ chat_id: "c1", message_id: "m1" })).toEqual({
      pathname: "/",
      params: { chatId: "c1", returnTo: "gallery", highlightMessage: "m1" },
    });
    expect(libraryOpenChatHref({ chat_id: "c1", message_id: null })).toEqual({
      pathname: "/",
      params: { chatId: "c1", returnTo: "gallery" },
    });
  });

  it("uses file empty copy on the files tab", () => {
    expect(galleryEmptyKey("files")).toBe("gallery.empty_files");
    expect(galleryEmptyKey("all")).toBe("gallery.empty");
    expect(galleryEmptyKey("generated")).toBe("gallery.empty_generated");
    expect(galleryEmptyKey("uploaded")).toBe("gallery.empty_uploaded");
    expect(galleryEmptyKey("all", "cat")).toBe("gallery.empty_search");
    expect(galleryEmptyKey("files", "  ")).toBe("gallery.empty_files");
  });

  it("maps tabs to category and source query params", () => {
    expect(galleryListParams("all")).toEqual({});
    expect(galleryListParams("generated")).toEqual({
      category: "images",
      source: "generated",
    });
    expect(galleryListParams("uploaded")).toEqual({
      category: "images",
      source: "upload",
    });
    expect(galleryListParams("files")).toEqual({ category: "files" });
  });

  it("derives a share filename from the content type", () => {
    expect(galleryFileName("application/pdf")).toBe("attachment.pdf");
    expect(galleryFileName("image/png")).toBe("attachment.png");
    expect(galleryFileName("application/pdf", "notes.pdf")).toBe("notes.pdf");
    expect(galleryFileName("application/pdf", "folder/notes.pdf")).toBe("notes.pdf");
    expect(galleryFileName("image/png", "orange")).toBe("orange.png");
    expect(galleryFileName("application/vnd.openxmlformats-officedocument.wordprocessingml.document")).toBe(
      "attachment.docx",
    );
    expect(galleryFileName("image/jpeg", "IMG_0042")).toBe("IMG_0042.jpg");
  });

  it("keeps the type's extension when an uploaded name has a dot that is not one", () => {
    expect(galleryFileName("image/png", "Screenshot 2026.10.14 at 3")).toBe("Screenshot 2026.10.14 at 3.png");
    expect(galleryFileName("image/png", "chart.v2.png")).toBe("chart.v2.png");
  });

  it.each([
    ["A cat in a hat", "image/png", "a-cat-in-a-hat.png"],
    // A slash used to cut the name to its last part, and a dot to drop the extension.
    ["Draw a cat w/ a hat. Make it blue.", "image/png", "draw-a-cat-w-a-hat-make-it-blue.png"],
    ["Ein Café am Fluss", "image/jpeg", "ein-cafe-am-fluss.jpg"],
    ["Кот в шляпе", "image/webp", "image.webp"],
    [null, "image/png", "image.png"],
  ])("names generated image %p as a safe file", (prompt, type, expected) => {
    expect(galleryFileName(type, prompt, "generated")).toBe(expected);
  });

  it("cuts a long prompt at a word, at most 40 characters before the extension", () => {
    const name = galleryFileName(
      "image/png",
      "A car accelerates on a straight road from rest to 75 km/h in 5 s. What is its acceleration?",
      "generated",
    );
    expect(name).toBe("a-car-accelerates-on-a-straight-road.png");
    expect(name.length - ".png".length).toBeLessThanOrEqual(GENERATED_FILE_STEM_MAX);
  });

  it("shows a generated image by its prompt and a file by its name", () => {
    expect(galleryDisplayName({ content_type: "image/png", original_filename: " A cat\nin a hat ", source: "generated" }))
      .toBe("A cat in a hat");
    expect(galleryDisplayName({ content_type: "application/pdf", original_filename: "notes", source: "upload" }))
      .toBe("notes.pdf");
  });

  it("maps content types and file names both ways", () => {
    expect(extensionForContentType("image/jpeg")).toBe("jpg");
    expect(extensionForContentType("text/plain; charset=utf-8")).toBe("txt");
    expect(extensionForContentType("image/avif")).toBe("avif");
    expect(extensionForContentType("garbage")).toBeNull();
    expect(contentTypeForFileName("cat.JPG")).toBe("image/jpeg");
    expect(contentTypeForFileName("notes.pdf")).toBe("application/pdf");
    expect(contentTypeForFileName("noext")).toBeNull();
  });

  it("lays the grid out with one gap across, down and at both edges", () => {
    const layout = galleryGridLayout(390, 16, 8);
    expect(layout).toEqual({ thumbSize: 114, cellPadding: 4, listPadding: 12 });
    // Three cells of (tile + 2 * cellPadding) fill the width inside the list padding.
    const cell = (390 - 2 * layout.listPadding) / 3;
    expect(cell - layout.thumbSize - 2 * layout.cellPadding).toBeLessThan(1);
    // Tile edge to screen edge equals the gutter on both sides.
    expect(layout.listPadding + layout.cellPadding).toBe(16);
  });

  it("shows the next photo after a delete, else the one before", () => {
    const images = [{ id: "a" }, { id: "b" }, { id: "c" }];
    expect(galleryNeighborImageId(images, "b")).toBe("c");
    expect(galleryNeighborImageId(images, "c")).toBe("b");
    expect(galleryNeighborImageId([{ id: "a" }], "a")).toBeNull();
    expect(galleryNeighborImageId(images, "missing")).toBeNull();
  });

  it("offers the long-press actions in menu order, open chat only when linked", () => {
    expect(galleryItemActions({ chat_id: "c1" })).toEqual(["use", "open_chat", "share", "delete"]);
    expect(galleryItemActions({ chat_id: null })).toEqual(["use", "share", "delete"]);
  });

  it("fills the row across three columns", () => {
    expect(galleryThumbSize(390 - 32, 3, 12)).toBe(111);
    expect(galleryThumbSize(0, 3, 12)).toBe(1);
    expect(COLUMN_THUMB_SIZE).toBe(64);
  });

  it("dedupes ids when appending a gallery page", () => {
    const current = [{ id: "a" }, { id: "b" }] as never;
    const incoming = [{ id: "b" }, { id: "c" }] as never;
    expect(mergeGalleryItems(current, incoming, false).map((item) => item.id)).toEqual([
      "a",
      "b",
      "c",
    ]);
    expect(mergeGalleryItems(current, incoming, true).map((item) => item.id)).toEqual([
      "b",
      "c",
    ]);
  });

  it("keys the gallery cache by filter and trimmed query", () => {
    expect(galleryListCacheKey("all", "  cat ")).toBe("all:cat");
  });
});
