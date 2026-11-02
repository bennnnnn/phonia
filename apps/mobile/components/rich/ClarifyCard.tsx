import { useMemo, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { useClarifyActions, useClarifyMessage } from "@/components/rich/clarifyContext";
import { useFenceRefused } from "@/components/rich/useFenceRefused";
import { PARAGRAPH_GAP } from "@/components/markdown/markdownContentStyles";
import { useReplyStreaming } from "@/components/markdown/ReplyStreaming";
import {
  answersFromMessage,
  clarifyMessage,
  initialClarifyAnswers,
  parseClarifyCard,
  type ClarifyAnswers,
  type ClarifyQuestion,
} from "@/lib/clarify/clarifyCard";
import { selection } from "@/lib/haptics";
import i18n from "@/lib/i18n";
import { isUnfinishedJson } from "@/lib/jsonFence";
import { plainFenceText } from "@/lib/lesson/lessonFences";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { type Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";
import { Button } from "@/ui/controls/Button";

type Props = { content: string };

const NONE: ClarifyAnswers = {};
/** A clarify card is JSON: text in its place, or JSON the card cannot read, is a refused fence. */
const CLARIFY_BODY = { json: true };

/**
 * A few questions under the start of an answer, each a list of choices with the likeliest
 * one picked (docs/clarify.md). The button sends the picks as the user's next message. The
 * card is live only on the newest reply while nothing is streaming; once answered it
 * stays, read-only, with the picks ticked and no button.
 */
export function ClarifyCard({ content }: Props) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const card = useMemo(() => parseClarifyCard(content), [content]);
  useFenceRefused("clarify", content, card === null && !isUnfinishedJson(content), CLARIFY_BODY);
  const actions = useClarifyActions();
  const message = useClarifyMessage();
  const streaming = useReplyStreaming();
  const [picks, setPicks] = useState<ClarifyAnswers>(NONE);
  const [sent, setSent] = useState(false);

  const nextUserText = message?.nextUserText ?? null;
  const sentAnswers = useMemo(
    () => (card && nextUserText ? answersFromMessage(card, nextUserText) : null),
    [card, nextUserText],
  );

  if (!card) {
    const plain = plainFenceText(content);
    return plain ? <Text style={[s.question, s.plain]}>{plain}</Text> : null;
  }

  const answered = sent || nextUserText != null;
  const asking = actions != null && message?.latest === true && !answered;
  const live = asking && !actions.busy && !streaming;
  const chosen = { ...initialClarifyAnswers(card), ...picks };
  // Typed instead of tapping: nothing on the card was picked.
  const shown = nextUserText != null ? (sentAnswers ?? NONE) : chosen;

  const pick = (question: ClarifyQuestion, index: number) => {
    // Tapping the choice already picked changes nothing: no tick.
    if (chosen[question.id] === index) return;
    selection();
    setPicks((prev) => ({ ...prev, [question.id]: index }));
  };
  const send = () => {
    if (!live || !actions) return;
    setSent(true);
    // Refused before it went out (offline): the card stays live to send again.
    void actions.send(clarifyMessage(card, chosen)).then((went) => {
      if (!went) setSent(false);
    });
  };

  return (
    <View style={s.card} testID="clarify-card">
      {card.questions.map((question) => (
        <QuestionBlock
          key={question.id}
          question={question}
          picked={shown[question.id]}
          live={live}
          onPick={(index) => pick(question, index)}
          s={s}
        />
      ))}
      {asking ? (
        <Button
          title={card.submit || i18n.t("clarify.submit")}
          variant="bubble"
          size="lg"
          onPress={send}
          disabled={!live}
          style={s.submit}
        />
      ) : null}
    </View>
  );
}

function QuestionBlock({
  question,
  picked,
  live,
  onPick,
  s,
}: {
  question: ClarifyQuestion;
  picked: number | undefined;
  live: boolean;
  onPick: (index: number) => void;
  s: Styles;
}) {
  return (
    <View style={s.question} accessibilityRole="radiogroup" accessibilityLabel={question.question}>
      <Text style={s.questionText}>{question.question}</Text>
      {question.options.map((option, index) => (
        <Choice
          key={option}
          label={option}
          checked={picked === index}
          live={live}
          onPress={() => onPick(index)}
          s={s}
        />
      ))}
    </View>
  );
}

function Choice({
  label,
  checked,
  live,
  onPress,
  s,
}: {
  label: string;
  checked: boolean;
  live: boolean;
  onPress: () => void;
  s: Styles;
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={!live}
      accessibilityRole="radio"
      accessibilityState={{ checked, disabled: !live }}
      style={({ pressed }) => [s.option, pressed && s.pressed, !live && !checked && s.faded]}
    >
      <View style={[s.radio, checked && s.marked]}>{checked ? <View style={s.radioDot} /> : null}</View>
      <Text style={s.optionText}>{label}</Text>
    </Pressable>
  );
}

type Styles = ReturnType<typeof makeStyles>;

function makeStyles(t: Theme) {
  return StyleSheet.create({
    card: {
      marginBottom: PARAGRAPH_GAP,
      padding: Space.md,
      gap: Space.lg,
      borderRadius: Radius.menu,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: t.border,
      backgroundColor: t.bg,
    },
    question: { gap: Space.xxs },
    questionText: { ...Type.body, ...Weight.bold, color: t.text, marginBottom: Space.xs },
    option: {
      flexDirection: "row",
      alignItems: "center",
      gap: Space.sm,
      minHeight: 44,
      paddingVertical: Space.xxs,
    },
    pressed: { opacity: 0.6 },
    faded: { opacity: 0.55 },
    radio: {
      width: 22,
      height: 22,
      borderRadius: Radius.full,
      borderWidth: 1.5,
      borderColor: t.textSecondary,
      alignItems: "center",
      justifyContent: "center",
    },
    marked: { borderColor: t.text, backgroundColor: t.text },
    radioDot: {
      width: 8,
      height: 8,
      borderRadius: Radius.full,
      backgroundColor: t.bg,
    },
    optionText: { flex: 1, ...Type.body, color: t.text },
    submit: { alignSelf: "stretch" },
    plain: { marginBottom: PARAGRAPH_GAP },
  });
}
