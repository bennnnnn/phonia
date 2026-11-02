import { useState } from "react";
import { ScrollView, StyleSheet, View, useWindowDimensions } from "react-native";

import { LazyAttachmentImageViewer } from "@/features/attachments/components/LazyAttachmentImageViewer";
import { ChatMessageImage } from "@/features/attachments/components/ChatMessageImage";
import { Space } from "@/lib/space";

/** Matches MessageBubble row `paddingHorizontal`. */
const CHAT_ROW_GUTTER = Space.md;

/** Visible sliver of the next photo so the row reads as swipeable. */
const IMAGE_STRIP_PEEK = 52;

const IMAGE_STRIP_GAP = Space.xs;

/** Landscape 4:3 card. Cover-crops the same thumbs; tap still opens full size. */
const STRIP_HEIGHT_RATIO = 3 / 4;

type ChatMessageImageStripItem = {
  attachmentId?: string | null;
  path?: string | null;
  localUri?: string | null;
  fileName?: string;
};

type Props = {
  images: ChatMessageImageStripItem[];
};

/**
 * One chat thumb stays the existing left-aligned size. Two or more sit in a
 * horizontal strip: one large tile plus a peek of the next, swipe for the rest.
 */
export function ChatMessageImageStrip({ images }: Props) {
  const { width: screenWidth } = useWindowDimensions();
  const [openIndex, setOpenIndex] = useState<number | null>(null);

  if (images.length === 0) {
    return null;
  }

  if (images.length === 1) {
    const image = images[0];
    return (
      <ChatMessageImage
        attachmentId={image.attachmentId}
        path={image.path}
        localUri={image.localUri}
        fileName={image.fileName}
      />
    );
  }

  const available = screenWidth - CHAT_ROW_GUTTER * 2;
  const tileWidth = Math.round(Math.max(0, available - IMAGE_STRIP_PEEK));
  const tileHeight = Math.round(tileWidth * STRIP_HEIGHT_RATIO);
  const snapInterval = tileWidth + IMAGE_STRIP_GAP;

  return (
    <>
      <ScrollView
        testID="chat-image-strip"
        horizontal
        nestedScrollEnabled
        directionalLockEnabled
        disableIntervalMomentum
        snapToInterval={snapInterval}
        snapToAlignment="start"
        decelerationRate="fast"
        showsHorizontalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={s.content}
        style={s.scroller}
      >
        {images.map((image, index) => (
          <View
            key={`${image.attachmentId ?? image.path ?? image.localUri}-${index}`}
            style={index === images.length - 1 ? undefined : s.tileGap}
          >
            <ChatMessageImage
              attachmentId={image.attachmentId}
              path={image.path}
              localUri={image.localUri}
              fileName={image.fileName}
              width={tileWidth}
              height={tileHeight}
              onOpen={() => setOpenIndex(index)}
            />
          </View>
        ))}
      </ScrollView>
      <LazyAttachmentImageViewer
        visible={openIndex !== null}
        onClose={() => setOpenIndex(null)}
        images={images}
        initialIndex={openIndex ?? 0}
      />
    </>
  );
}

const s = StyleSheet.create({
  scroller: {
    width: "100%",
    maxWidth: "100%",
  },
  content: {
    flexDirection: "row",
    alignItems: "flex-start",
  },
  tileGap: {
    marginRight: IMAGE_STRIP_GAP,
  },
});
