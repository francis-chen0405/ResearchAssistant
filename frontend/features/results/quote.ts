// Quotes are exact stored passages. These helpers only decide how to present a
// passage; they never trim, pad or repair its text.

function completeSentencePrefix(text: string): { text: string; omittedTail: boolean } {
  const sentences = typeof Intl.Segmenter === "function"
    ? [...new Intl.Segmenter(undefined, { granularity: "sentence" }).segment(text)].map(
        (part) => part.segment.trim(),
      )
    : (() => {
        const parts = text.split(/([.!?]["'”’)}\]]*\s+)/u);
        const fallback: string[] = [];
        for (let index = 0; index < parts.length; index += 2) {
          fallback.push(`${parts[index] ?? ""}${parts[index + 1] ?? ""}`.trim());
        }
        return fallback;
      })();
  const complete: string[] = [];
  for (const sentence of sentences) {
    if (/[.!?]["'”’)}\]]*$/u.test(sentence)) {
      complete.push(sentence);
    } else if (sentence) {
      return { text: complete.join(" "), omittedTail: true };
    }
  }
  return { text: complete.join(" "), omittedTail: complete.length !== sentences.length };
}

export function completeQuote(passage: string): { text: string; omittedTail: boolean } | null {
  const match = passage.match(/^\[[\s\S]*?\]\s+"([\s\S]+)"\s+\[[\s\S]*\]$/);
  const quotedText = (match?.[1] ?? passage).trim();
  const sourceSegments = quotedText.split(/\s+\.\.\.\s+/);
  const completeSegments: string[] = [];
  let omittedTail = false;
  for (const segment of sourceSegments) {
    const complete = completeSentencePrefix(segment);
    if (complete.text) completeSegments.push(complete.text);
    if (complete.omittedTail) {
      omittedTail = true;
      break;
    }
  }
  // A trailing fragment can contain a qualification to the preceding sentence.
  // Do not silently discard it and present the remainder as a complete quote.
  if (!completeSegments.length || omittedTail || completeSegments.length !== sourceSegments.length) return null;
  return {
    // Preserve the admitted text, including its original omission markers and spacing.
    text: quotedText,
    omittedTail: false,
  };
}
