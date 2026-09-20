import { splitParagraphs, tokenizeAnswer } from "@/lib/citations";
import { citationHref } from "@/lib/links";

/**
 * Renders an answer's prose with its inline citations turned into chips that link to the section
 * they came from — `/subject/[subject]/chapter/[no]#section-[section_no]` (CONTRACTS §5).
 *
 * A citation with no chapter number of its own (`[§4.2 p.57]`) falls back to the chapter the
 * student is currently reading, which is the only chapter an answer in this panel can be about.
 */
export default function AnswerBody({
  text,
  subject,
  chapterNo,
}: {
  text: string;
  subject: string;
  chapterNo: number;
}) {
  const paragraphs = splitParagraphs(text);

  return (
    <div className="chat__answer">
      {paragraphs.map((paragraph, index) => (
        <p key={index}>
          {tokenizeAnswer(paragraph).map((token, tokenIndex) => {
            if (token.kind === "text") {
              const lines = token.text.split("\n");
              return (
                <span key={tokenIndex}>
                  {lines.map((line, lineIndex) => (
                    <span key={lineIndex}>
                      {line}
                      {lineIndex < lines.length - 1 ? <br /> : null}
                    </span>
                  ))}
                </span>
              );
            }
            return (
              <a
                key={tokenIndex}
                className="chip"
                href={citationHref({
                  subject,
                  chapter_no: token.chapterNo ?? chapterNo,
                  section_no: token.sectionNo,
                })}
                title={`Jump to §${token.sectionNo}${token.chapterNo !== null && token.chapterNo !== chapterNo ? ` of chapter ${token.chapterNo}` : ""}`}
              >
                {token.label}
              </a>
            );
          })}
        </p>
      ))}
    </div>
  );
}
