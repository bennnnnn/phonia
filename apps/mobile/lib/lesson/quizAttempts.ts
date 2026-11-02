/** What the user picked on a quiz card, and whether they checked it. */
export type QuizAttempt = { picked: number | null; checked: boolean };

// The answer stays picked when the list recycles the message off screen and back.
const attempts = new Map<string, QuizAttempt>();
/** Attempts kept; the least recently answered goes first (code-health audit LEAK-07). */
const MAX_ATTEMPTS = 200;

export function quizAttempt(content: string): QuizAttempt | undefined {
  return attempts.get(content);
}

export function saveQuizAttempt(content: string, attempt: QuizAttempt): void {
  attempts.delete(content);
  attempts.set(content, attempt);
  while (attempts.size > MAX_ATTEMPTS) attempts.delete(attempts.keys().next().value as string);
}

/** Sign-out: the next account starts with every quiz unanswered. */
export function clearQuizAttempts(): void {
  attempts.clear();
}
