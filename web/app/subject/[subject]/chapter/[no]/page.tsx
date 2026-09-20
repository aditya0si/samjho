import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import AnimationHost from "@/components/AnimationHost";
import Breadcrumbs from "@/components/Breadcrumbs";
import ChapterStatusNotice from "@/components/ChapterStatusNotice";
import ChatPanel from "@/components/ChatPanel";
import CorpusNotice from "@/components/CorpusNotice";
import ProgressPanel from "@/components/ProgressPanel";
import SectionList from "@/components/SectionList";
import { getChapterCorpus, getHealthResult } from "@/lib/corpus";
import { chapterHref, quizHref } from "@/lib/links";
import { findChapter, findSubject, loadSyllabusCached } from "@/lib/syllabus";

export const dynamic = "force-dynamic";

type PageProps = { params: Promise<{ subject: string; no: string }> };

async function resolve(params: PageProps["params"]) {
  const { subject: subjectSlug, no } = await params;
  const load = await loadSyllabusCached();
  if (!load.syllabus) return { load, subject: null, chapter: null };
  const subject = findSubject(load.syllabus, subjectSlug);
  if (!subject) return { load, subject: null, chapter: null };
  const chapter = findChapter(subject, no);
  return { load, subject, chapter };
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { subject, chapter } = await resolve(params);
  if (!subject || !chapter) return { title: "Study" };
  return { title: `${chapter.title} — study (${subject.name})` };
}

/** Up to three questions built from this chapter's own section headings — never invented topics. */
function suggestedQuestions(sections: { no: string; title: string }[]): string[] {
  return sections
    .filter((section) => section.title.trim().length > 3 && section.title.length <= 60)
    .slice(0, 3)
    .map((section) => `Explain ${section.title}`);
}

export default async function StudyPage({ params }: PageProps) {
  const { load, subject, chapter } = await resolve(params);
  if (!subject || !chapter) notFound();

  const health = await getHealthResult();
  const detail = await getChapterCorpus(subject.id, chapter.no, chapter, health);
  const sections = detail.sections ?? chapter.sections;
  const corpusKnownEmpty = detail.status.ingested === false;

  return (
    <>
      <Breadcrumbs
        crumbs={[
          { label: "Home", href: "/" },
          { label: subject.name, href: `/${subject.id}` },
          { label: `Chapter ${chapter.no}`, href: chapterHref(subject.id, chapter.no) },
          { label: "Study" },
        ]}
      />

      <h1>
        {chapter.title} <span className="subtle">· {subject.name}, chapter {chapter.no}</span>
      </h1>
      <p className="lede">
        Read the section map, ask questions about this chapter, run the concept animations, then
        take a quiz and see which sections to go back to.
      </p>

      {/* Asking questions needs the API, so the API-unreachable banner belongs on this page too. */}
      {!health.ok ? (
        <CorpusNotice health={health} syllabusSource={load.source} syllabusPath={load.filePath} />
      ) : null}

      <ChapterStatusNotice status={detail.status} chapterNo={chapter.no} variant="study" />

      <section aria-labelledby="sections-heading">
        <h2 id="sections-heading">Sections of this chapter</h2>
        <p className="subtle">
          Every anchor here is a citation target: a chip in an answer links straight to{" "}
          <code>#section-&lt;no&gt;</code>.
        </p>
        <SectionList sections={sections} />
      </section>

      <p className="row">
        <Link className="button" href={quizHref(subject.id, chapter.no)}>
          Take a quiz on this chapter
        </Link>
      </p>

      <ChatPanel
        subject={subject.id}
        subjectName={subject.name}
        chapterNo={chapter.no}
        chapterTitle={chapter.title}
        suggestedQuestions={suggestedQuestions(sections)}
        corpusKnownEmpty={corpusKnownEmpty}
      />

      <AnimationHost
        subject={subject.id}
        subjectName={subject.name}
        chapterNo={chapter.no}
        chapterTitle={chapter.title}
      />

      <ProgressPanel
        subject={subject.id}
        chapterNo={chapter.no}
        chapterTitle={chapter.title}
      />
    </>
  );
}
