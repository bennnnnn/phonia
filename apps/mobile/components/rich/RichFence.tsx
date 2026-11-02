import { ReactNode } from "react";

import i18n from "@/lib/i18n";

import { PlacesListBlock } from "@/components/rich/PlacesListBlock";
import { CalculatorBlock } from "@/components/rich/CalculatorBlock";
import { CalloutBlock } from "@/components/rich/CalloutBlock";
import { parsePlacesJson } from "@/lib/places/placesList";
import { AnswerBlock } from "@/components/rich/AnswerBlock";
import { ArrayBlock } from "@/components/rich/ArrayBlock";
import { ArithmeticWorkBlock } from "@/components/rich/ArithmeticWorkBlock";
import { ComparisonBlock } from "@/components/rich/ComparisonBlock";
import { EmailCard } from "@/features/drafts/components/EmailCard";
import { KeyValueBlock } from "@/components/rich/KeyValueBlock";
import {
  LazyChartBlock,
  LazyChemistryBlock,
  LazyCircularClockBlock,
  LazyFunctionGraphBlock,
  LazyGeometryBlock,
  LazyMermaidBlock,
  LazyMoleculeCard,
  LazySimulationBlock,
  LazyMolecule3DBlock,
} from "@/components/rich/LazyHeavyRich";
import { ChemistrySceneBlock } from "@/components/rich/ChemistrySceneBlock";
import { ClarifyCard } from "@/components/rich/ClarifyCard";
import { MathBlock } from "@/components/rich/MathView";
import { MessagePreview } from "@/components/rich/MessagePreview";
import { QuizCard } from "@/components/rich/QuizCard";
import { QuoteBlock } from "@/components/rich/QuoteBlock";
import { SocialPostCard } from "@/components/rich/SocialPostCard";
import { StepList } from "@/components/rich/StepList";
import type { FenceId } from "@/lib/fenceRegistry";
import {
  isMessageLang,
  parseCalloutKind,
  parseComparison,
  parseEmailDraft,
  parseKeyValue,
  parseQuoteAttribution,
  parseSocialPlatform,
  parseSteps,
} from "@/lib/richBlocks";

/** A display-math block's key: its source, and its token when the markdown AST gives one. */
export function mathFenceKey(content: string, tokenIndex?: number): string {
  return tokenIndex != null ? `math:${content}#${tokenIndex}` : `math:${content}`;
}

/**
 * An email card's key: its token when the markdown AST gives one, so a draft
 * the user is editing keeps its state while the reply re-parses.
 */
function emailFenceKey(key: string, tokenIndex?: number): string {
  return tokenIndex != null ? `email:${tokenIndex}` : key;
}

/** Render a registry fence by id — no lang-string soup, no content heuristics. */
export function renderRichFenceById(
  id: FenceId,
  lang: string,
  content: string,
  key: string,
  tokenIndex?: number,
): ReactNode | null {
  switch (id) {
    case "email": {
      const draft = parseEmailDraft(content) ?? { body: content };
      return <EmailCard key={emailFenceKey(key, tokenIndex)} draft={draft} />;
    }
    case "quote": {
      const { quote, author } = parseQuoteAttribution(content);
      if (!quote) return null;
      return <QuoteBlock key={key} quote={quote} author={author} />;
    }
    case "message":
      return <MessagePreview key={key} text={content} />;
    case "social": {
      const social = parseSocialPlatform(lang);
      if (!social) return null;
      return <SocialPostCard key={key} platform={social} text={content} />;
    }
    case "math":
      return <MathBlock key={mathFenceKey(content, tokenIndex)} latex={content} />;
    case "answer":
      return <AnswerBlock key={key} content={content} />;
    case "arithmetic":
      return <ArithmeticWorkBlock key={key} content={content} />;
    case "geometry":
      return <LazyGeometryBlock key={key} content={content} />;
    case "graph":
      return <LazyFunctionGraphBlock key={key} content={content} />;
    case "simulation":
      return <LazySimulationBlock key={key} content={content} />;
    case "places": {
      const places = parsePlacesJson(content);
      if (places.length > 0) return <PlacesListBlock key={key} places={places} />;
      return null;
    }
    case "clock":
      return <LazyCircularClockBlock key={key} content={content} />;
    case "callout":
      return <CalloutBlock key={key} kind={parseCalloutKind(lang)} content={content} />;
    case "comparison": {
      const data = parseComparison(content);
      if (data) return <ComparisonBlock key={key} data={data} />;
      return null;
    }
    case "keyvalue": {
      const rows = parseKeyValue(content);
      if (rows.length === 0) return null;
      return <KeyValueBlock key={key} rows={rows} />;
    }
    case "steps": {
      const steps = parseSteps(content);
      if (steps.length === 0) return null;
      return <StepList key={key} steps={steps} />;
    }
    case "quiz":
      return <QuizCard key={key} content={content} />;
    case "clarify":
      return <ClarifyCard key={key} content={content} />;
    case "array":
      return <ArrayBlock key={key} content={content} />;
    case "mermaid":
      return <LazyMermaidBlock key={key} content={content} />;
    case "calculator":
      return <CalculatorBlock key={key} content={content} />;
    case "chem_scene":
      return <ChemistrySceneBlock key={key} content={content} />;
    case "chemistry":
      return <LazyChemistryBlock key={key} content={content} />;
    case "molecule":
      return <LazyMoleculeCard key={key} content={content} />;
    case "molecule3d":
      return <LazyMolecule3DBlock key={key} content={content} />;
    case "chart":
      return <LazyChartBlock key={key} content={content} />;
    case "copy":
    case "sources":
      return null;
    default: {
      const _exhaustive: never = id;
      void _exhaustive;
      return null;
    }
  }
}

export function renderCopyStyleBlock(
  lang: string,
  content: string,
  key: string,
  tokenIndex?: number,
): ReactNode | null {
  const l = lang.trim().toLowerCase();
  const emailKey = emailFenceKey(key, tokenIndex);
  if (l === "email") {
    const draft = parseEmailDraft(content);
    if (draft) return <EmailCard key={emailKey} draft={draft} />;
  }
  if (isMessageLang(l)) {
    return (
      <MessagePreview
        key={key}
        text={content}
        label={l === "reply" ? i18n.t("rich.reply_draft") : i18n.t("rich.message_draft")}
      />
    );
  }
  const social = parseSocialPlatform(l);
  if (social) {
    return <SocialPostCard key={key} platform={social} text={content} />;
  }
  const draft = parseEmailDraft(content);
  if (draft) {
    return <EmailCard key={emailKey} draft={draft} />;
  }
  return null;
}
