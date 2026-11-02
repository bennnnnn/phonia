import { ReactNode } from "react";
import { Image } from "expo-image";
import { Text } from "react-native";

import { type AstNode, astText } from "@/components/markdown/markdownAstHelpers";
import type { MdImgStyles, StyleMap } from "@/components/markdown/markdownContentStyles";
import { TapToLoadImage } from "@/components/markdown/TapToLoadImage";
import { imageLoadPolicy } from "@/lib/images/imageUriPolicy";
import { openAllowedUrl } from "@/lib/linkSchemePolicy";
import { openPlaceLink } from "@/lib/places/openPlaceLink";
import { isGenericSearchUrl } from "@/lib/places/placesList";

export function linkRules(mdImg: MdImgStyles) {
  return {
    image: (node: { key: string; attributes: { src?: string; alt?: string } }) => {
      const src = node.attributes?.src;
      // A model-written image URL can carry the user's data (prompt
      // injection), so only the API's own and inline images load by
      // themselves; another https host waits for a tap; the rest never load.
      const policy = imageLoadPolicy(src);
      if (policy === "block" || !src) return null;
      const alt = node.attributes?.alt?.trim() ?? "";
      if (policy === "ask") {
        return <TapToLoadImage key={node.key} uri={src} alt={alt} imageStyle={mdImg.image} />;
      }
      return (
        <Image
          key={node.key}
          source={{ uri: src }}
          style={mdImg.image}
          contentFit="contain"
          cachePolicy="memory-disk"
          accessibilityRole="image"
          accessibilityLabel={alt || undefined}
          accessible={alt.length > 0}
        />
      );
    },
    link: (
      node: AstNode,
      children: ReactNode,
      _parent: unknown,
      styles: StyleMap,
    ) => {
      const href = node.attributes?.href ?? "";
      const label = astText(node);
      return (
        <Text
          key={node.key}
          style={styles.link}
          accessibilityRole="link"
          onPress={() => {
            // Reject javascript:/data:/file:/etc. before handing to the OS link
            // handler — model-emitted markdown can include arbitrary URLs and
            // Linking.openURL executes the payload on some platforms.
            if (isGenericSearchUrl(href)) {
              void openPlaceLink(href, label);
            } else {
              void openAllowedUrl(href);
            }
          }}
          suppressHighlighting
        >
          {children}
        </Text>
      );
    },
  };
}
