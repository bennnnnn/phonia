/**
 * An inline `data:` URL holding a raster image, drawn as pixels wherever it is
 * used. SVG is never one: an SVG document can carry script, which runs when it
 * is loaded as a document (`<iframe>`, `<object>`, `<embed>`, SVG `<use>`).
 * The chat's image policy and the HTML export's script strip share this list.
 */
const INLINE_RASTER = /data:image\/(?:png|jpe?g|gif|webp|avif|heic|bmp);/iy;

/** Whether `url`, read from index `at`, starts with an inline raster `data:` image. */
export function isInlineRasterDataUrl(url: string, at = 0): boolean {
  INLINE_RASTER.lastIndex = at;
  return INLINE_RASTER.test(url);
}
