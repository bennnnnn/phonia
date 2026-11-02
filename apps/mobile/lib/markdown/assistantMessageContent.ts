import type { SettingsProposal } from "@/lib/settingsProposal";
import { parseSettingsProposals, stripSettingsProposalFences } from "@/lib/settingsProposal";
import { stripReminderFences } from "@/features/todos/model/reminderFence";
import {
  parseReminderProposals,
  stripReminderProposalFences,
  type ReminderProposal,
} from "@/features/todos/model/reminderProposal";
import { hasTodoLink, stripTodoLinkFences } from "@/features/todos/model/todoLink";
import type { SearchSource } from "@/lib/api";

import { isLocationQuestion } from "@/lib/places/localPlacesQuery";
import { resolvePlaces, stripPlacesContent, type PlaceItem } from "@/lib/places/placesList";
import { resolveSearchSources, stripSearchSourcesFromContent } from "@/lib/searchSources";
import { parseMessageImages, stripLookupSourceCaption, type ParsedMessageImage } from "@/lib/messageAttachments";
import { parseFenceLang } from "@/lib/codeHighlight";
import { mapClosedFences } from "@/lib/mdFenceScan";
import {
  assistantReplyIsTimeAnswer,
  extractClockTimezone,
  stripTimeAnswerFences,
} from "@/lib/timeQuestion";

type AssistantMessageContentInput = {
  content: string;
  layoutFrozen: boolean;
  isUser: boolean;
  priorUserText: string | null;
  storedSearchSources?: SearchSource[];
  liveSearchSources?: SearchSource[];
  messageId: string;
  isGenerating: boolean;
  renderKey?: string;
};

export type AssistantMessageContent = {
  hasContent: boolean;
  showActionSlot: boolean;
  actionsReady: boolean;
  showLiveClock: boolean;
  clockTimezone: string;
  searchSources: SearchSource[];
  settingsProposals: SettingsProposal[];
  showSettingsProposals: boolean;
  reminderProposals: ReminderProposal[];
  showReminderProposals: boolean;
  /** A to-do change asked in another language: the Open To-do button (todoLink.ts). */
  showTodoLink: boolean;
  places: PlaceItem[];
  showPlaces: boolean;
  images: ParsedMessageImage[];
  showImages: boolean;
  markdownContent: string;
  hasMarkdown: boolean;
  showSearchSources: boolean;
  markdownStreamMode: boolean;
  markdownResetKey: string;
};

/**
 * Stored chats may still contain retired product fences (the language-learning
 * cards and the Google Calendar event proposal). Drop the JSON.
 */
const RETIRED_FENCE_LANGS: ReadonlySet<string> = new Set([
  "vocab_quiz",
  "vocab_card",
  "learning_launch",
  "job-results",
  "calendar_proposal",
]);

/** One empty list, so a frozen reply's sources keep their identity flush to flush. */
const NO_SOURCES: SearchSource[] = [];

const UNVERIFIED_RESULT_LINE =
  /[ \t]*\*?I couldn't automatically verify this result\.\*?[ \t]*/g;

function stripUnverifiedResultLine(text: string): string {
  if (!text.includes("automatically verify this result")) return text;
  return text.replace(UNVERIFIED_RESULT_LINE, "").replace(/\n{3,}/g, "\n\n").trim();
}

/** Any retired name in any case: a fence's language is read lower-cased. */
const RETIRED_FENCE_NAME = new RegExp([...RETIRED_FENCE_LANGS].join("|"), "i");

function stripRetiredFences(text: string): string {
  // Only old stored chats hold one; every other reply skips the line walk.
  if (!text.includes("```") || !RETIRED_FENCE_NAME.test(text)) return text;
  return mapClosedFences(text, (info, _body, original) =>
    RETIRED_FENCE_LANGS.has(parseFenceLang(info)) ? "" : original,
  );
}

function buildMarkdownContent(options: {
  content: string;
  showLiveClock: boolean;
  showPlaces: boolean;
  places: PlaceItem[];
}): string {
  const { content, showLiveClock, showPlaces, places } = options;

  // Fence-scoped strips — a reply with no fences skips the regex passes and
  // only normalizes whitespace.
  const hasFence = content.includes("```");
  if (!hasFence) {
    return content.replace(/\n{3,}/g, "\n\n").trim();
  }

  let text = stripRetiredFences(content);
  if (showLiveClock) text = stripTimeAnswerFences(text);
  text = stripSearchSourcesFromContent(text);
  text = stripReminderFences(text);
  text = stripSettingsProposalFences(text);
  text = stripReminderProposalFences(text);
  text = stripTodoLinkFences(text);
  if (showPlaces) text = stripPlacesContent(text, places);
  return text;
}

/** Pure assistant reply display model — fences stripped, rich blocks resolved. */
export function deriveAssistantMessageContent(
  input: AssistantMessageContentInput,
): AssistantMessageContent {
  const {
    content,
    layoutFrozen,
    isUser,
    priorUserText,
    storedSearchSources,
    liveSearchSources,
    messageId,
    isGenerating,
    renderKey,
  } = input;

  const hasContent = content.trim().length > 0;
  const showActionSlot = !isUser && hasContent;
  // Mount only after generation ends. While streaming, composer-gap pad holds
  // the same height so the prose does not move when icons appear (ChatGPT).
  const actionsReady = showActionSlot && !isGenerating;

  const showLiveClock =
    !isUser &&
    hasContent &&
    !layoutFrozen &&
    assistantReplyIsTimeAnswer(content);

  const clockTimezone = showLiveClock ? extractClockTimezone(content) : "";
  // While the layout is frozen the Sources row is hidden, and a reply's own
  // sources fence comes at its end: reading the fence waits until then.
  const attachedSources = liveSearchSources ?? storedSearchSources;
  const searchSources = layoutFrozen
    ? attachedSources ?? NO_SOURCES
    : resolveSearchSources(content, attachedSources);

  const settingsProposals =
    !isUser && hasContent && !layoutFrozen ? parseSettingsProposals(content) : [];
  const showSettingsProposals = settingsProposals.length > 0 && !layoutFrozen;

  const reminderProposals =
    !isUser && hasContent && !layoutFrozen ? parseReminderProposals(content) : [];
  const showReminderProposals = reminderProposals.length > 0;
  const showTodoLink = !isUser && hasContent && !layoutFrozen && hasTodoLink(content);

  const places =
    !isUser && hasContent && !layoutFrozen ? resolvePlaces(content) : [];
  const showPlaces = places.length > 0;

  // [Image: …] marker lines only appear in attachment/lookup replies — skip the
  // per-line split+regex scan for the common no-marker reply.
  const parsedImages =
    !isUser && hasContent && content.includes("[Image:")
      ? parseMessageImages(content)
      : { images: [], textWithoutImages: content };
  const showImages = parsedImages.images.length > 0 && !layoutFrozen;
  const proseWithoutImages =
    parsedImages.images.length > 0
      ? stripLookupSourceCaption(parsedImages.textWithoutImages)
      : parsedImages.textWithoutImages;

  const proseForMarkdown = isUser
    ? proseWithoutImages
    : stripUnverifiedResultLine(proseWithoutImages);

  const markdownContent = buildMarkdownContent({
    content: proseForMarkdown,
    showLiveClock,
    showPlaces,
    places,
  });

  const hasMarkdown = markdownContent.trim().length > 0;
  // Live clock and "where am I" are device-driven — a Sources chip would
  // imply the answer came from those links, which it didn't.
  const showSearchSources =
    searchSources.length > 0 &&
    !layoutFrozen &&
    !showLiveClock &&
    !(priorUserText != null && isLocationQuestion(priorUserText));

  return {
    hasContent,
    showActionSlot,
    actionsReady,
    showLiveClock,
    clockTimezone,
    searchSources,
    settingsProposals,
    showSettingsProposals,
    reminderProposals,
    showReminderProposals,
    showTodoLink,
    places,
    showPlaces,
    images: parsedImages.images,
    showImages,
    markdownContent,
    hasMarkdown,
    showSearchSources,
    markdownStreamMode: layoutFrozen || isGenerating,
    markdownResetKey: `${renderKey ?? messageId}:${markdownContent.length}`,
  };
}
