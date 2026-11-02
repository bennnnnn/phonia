/**
 * Size a photo to the stage without stretching it to a common frame.
 * Larger images scale down to fit; smaller ones keep their pixel size.
 */
export function fitImageToStage(
  imageWidth: number,
  imageHeight: number,
  stageWidth: number,
  stageHeight: number,
): { width: number; height: number } {
  if (imageWidth <= 0 || imageHeight <= 0 || stageWidth <= 0 || stageHeight <= 0) {
    return { width: Math.max(1, Math.round(stageWidth)), height: Math.max(1, Math.round(stageHeight)) };
  }
  const scale = Math.min(1, stageWidth / imageWidth, stageHeight / imageHeight);
  return {
    width: Math.max(1, Math.round(imageWidth * scale)),
    height: Math.max(1, Math.round(imageHeight * scale)),
  };
}
