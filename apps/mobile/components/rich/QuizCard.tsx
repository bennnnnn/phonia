import { useMemo, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { CodeBlock } from "@/components/CodeBlock";
import { ChipText } from "@/components/rich/ChipText";
import { useFenceRefused } from "@/components/rich/useFenceRefused";
import {
  inlineCodeTextStyle,
  PARAGRAPH_GAP,
} from "@/components/markdown/markdownContentStyles";
import { notifySuccess, notifyWarning, selection } from "@/lib/haptics";
import i18n from "@/lib/i18n";
import { quizBody } from "@/lib/lesson/cardBody";
import { explanationParts, type LooseQuiz, optionLetter } from "@/lib/lesson/lessonFences";
import { type QuizAttempt, quizAttempt, saveQuizAttempt } from "@/lib/lesson/quizAttempts";
import { Radius } from "@/lib/radius";
import { Space } from "@/lib/space";
import { type Theme, useTheme } from "@/lib/theme";
import { Type, Weight } from "@/lib/type";
import { Button } from "@/ui/controls/Button";
import { useLiveAnnouncement } from "@/ui/hooks/useLiveAnnouncement";

type Props = { content: string };

/** A quiz is JSON: text in its place, or JSON the card cannot read, is a refused fence. */
const QUIZ_BODY = { json: true };

/** "Exercise 1": the code, pick an option, check it, see why. Nothing is sent to the chat. */
export function QuizCard({ content }: Props) {
  const theme = useTheme();
  const s = useMemo(() => makeStyles(theme), [theme]);
  const body = useMemo(() => quizBody(content), [content]);
  const quiz = body?.kind === "card" ? body.card : null;
  useFenceRefused("quiz", content, body !== null && quiz === null, QUIZ_BODY);
  const [attempt, setAttempt] = useState<QuizAttempt>(
    () => quizAttempt(content) ?? { picked: null, checked: false },
  );
  // The verdict of a check made here, not one restored when the card scrolls back in.
  const [verdict, setVerdict] = useState<string | null>(null);
  useLiveAnnouncement(verdict);

  if (!quiz) {
    if (body?.kind === "plain") {
      return (
        <ChipText style={[s.explanation, s.plain]} chip={s.chip}>
          {body.text}
        </ChipText>
      );
    }
    return body?.kind === "loose" ? <LooseQuizCard quiz={body.loose} s={s} /> : null;
  }

  const save = (next: QuizAttempt) => {
    saveQuizAttempt(content, next);
    setAttempt(next);
  };
  const pick = (index: number) => {
    selection();
    save({ picked: index, checked: false });
  };
  const check = () => {
    if (attempt.picked === null) return;
    if (attempt.picked === quiz.answer) notifySuccess();
    else notifyWarning();
    save({ ...attempt, checked: true });
    setVerdict(i18n.t(attempt.picked === quiz.answer ? "rich.quiz_correct" : "rich.quiz_wrong"));
  };
  const correct = attempt.picked === quiz.answer;

  return (
    <View style={s.card} testID="quiz-card">
      <QuizHeader quiz={quiz} s={s} />
      <View accessibilityRole="radiogroup">
        {quiz.options.map((option, index) => {
          const picked = attempt.picked === index;
          return (
            <Pressable
              key={`${index}:${option}`}
              onPress={() => pick(index)}
              accessibilityRole="radio"
              accessibilityState={{ checked: picked }}
              style={({ pressed }) => [s.option, pressed && s.pressed]}
            >
              <View style={[s.radio, picked && s.radioPicked]}>
                {picked ? <View style={s.radioDot} /> : null}
              </View>
              <ChipText style={s.optionText} chip={s.chip}>
                {option}
              </ChipText>
            </Pressable>
          );
        })}
      </View>
      <Button
        title={i18n.t("rich.quiz_check")}
        onPress={check}
        disabled={attempt.picked === null || attempt.checked}
      />
      {attempt.checked ? (
        <View style={s.result} accessibilityLiveRegion="polite">
          <Text style={s.verdict}>
            {correct ? i18n.t("rich.quiz_correct") : i18n.t("rich.quiz_wrong")}
          </Text>
          <Explanation text={quiz.explanation} s={s} />
        </View>
      ) : null}
    </View>
  );
}

/**
 * A quiz whose fence did not parse: the question and lettered options as text,
 * and the explanation behind "Show answer" so the exercise still works.
 */
function LooseQuizCard({ quiz, s }: { quiz: LooseQuiz; s: Styles }) {
  const [shown, setShown] = useState(false);
  return (
    <View style={s.card} testID="quiz-card-text">
      <QuizHeader quiz={quiz} s={s} />
      {quiz.options.map((option, index) => (
        <ChipText key={`${index}:${option}`} style={s.optionText} chip={s.chip}>
          {`${optionLetter(index)} ${option}`}
        </ChipText>
      ))}
      {quiz.explanation && !shown ? (
        <Button
          title={i18n.t("rich.quiz_show_answer")}
          variant="secondary"
          onPress={() => setShown(true)}
        />
      ) : null}
      {quiz.explanation && shown ? (
        <View style={s.result} accessibilityLiveRegion="polite">
          <Explanation text={quiz.explanation} s={s} />
        </View>
      ) : null}
    </View>
  );
}

/** The "Exercise 1" badge, the question and the code it asks about. */
function QuizHeader({
  quiz,
  s,
}: {
  quiz: Pick<LooseQuiz, "label" | "question" | "code" | "codeLang">;
  s: Styles;
}) {
  return (
    <>
      {quiz.label ? (
        <View style={s.badge}>
          <Text style={s.badgeText}>{quiz.label}</Text>
        </View>
      ) : null}
      {quiz.question ? (
        <ChipText style={s.question} chip={s.chip}>
          {quiz.question}
        </ChipText>
      ) : null}
      {quiz.code ? <CodeBlock code={quiz.code} lang={quiz.codeLang} /> : null}
    </>
  );
}

/** Prose with any fenced code drawn as a code block. */
function Explanation({ text, s }: { text: string; s: Styles }) {
  return (
    <>
      {explanationParts(text).map((part, index) =>
        part.kind === "code" ? (
          <CodeBlock key={index} code={part.code} lang={part.lang} />
        ) : (
          <ChipText key={index} style={s.explanation} chip={s.chip}>
            {part.text}
          </ChipText>
        ),
      )}
    </>
  );
}

type Styles = ReturnType<typeof makeStyles>;

function makeStyles(t: Theme) {
  return StyleSheet.create({
    card: {
      marginBottom: PARAGRAPH_GAP,
      paddingHorizontal: Space.md,
      paddingTop: Space.md,
      paddingBottom: Space.lg,
      gap: Space.sm,
      borderRadius: Radius.menu,
      borderWidth: StyleSheet.hairlineWidth,
      borderColor: t.border,
      backgroundColor: t.bg,
    },
    // "Exercise 1", a soft pill in the brand tint.
    badge: {
      alignSelf: "flex-start",
      paddingHorizontal: Space.sm,
      paddingVertical: Space.xxs,
      borderRadius: Radius.full,
      backgroundColor: t.accentLight,
    },
    badgeText: { ...Type.secondary, ...Weight.semibold, color: t.accentDark },
    question: { ...Type.body, ...Weight.semibold, color: t.text },
    option: {
      flexDirection: "row",
      alignItems: "center",
      gap: Space.sm,
      minHeight: 44,
      paddingVertical: Space.xxs,
    },
    pressed: { opacity: 0.6 },
    radio: {
      width: 22,
      height: 22,
      borderRadius: Radius.full,
      borderWidth: 1.5,
      borderColor: t.textSecondary,
      alignItems: "center",
      justifyContent: "center",
    },
    radioPicked: { borderColor: t.text, backgroundColor: t.text },
    radioDot: {
      width: 8,
      height: 8,
      borderRadius: Radius.full,
      backgroundColor: t.bg,
    },
    optionText: { flex: 1, ...Type.body, color: t.text },
    // The same pill as inline code in replies.
    chip: inlineCodeTextStyle(t),
    // The verdict and why, in a gray panel under the button.
    result: {
      gap: Space.sm,
      padding: Space.md,
      borderRadius: Radius.xl,
      backgroundColor: t.surface,
    },
    verdict: { ...Type.body, ...Weight.bold, color: t.text },
    explanation: { ...Type.body, color: t.text },
    plain: { marginBottom: PARAGRAPH_GAP },
  });
}
