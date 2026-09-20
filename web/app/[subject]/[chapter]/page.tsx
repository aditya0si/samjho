import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import AnimationHost from "@/components/AnimationHost";
import Breadcrumbs from "@/components/Breadcrumbs";
import ChapterStatusNotice from "@/components/ChapterStatusNotice";
import CorpusNotice from "@/components/CorpusNotice";
import SectionList from "@/components/SectionList";
import { getChapterCorpus, getHealthResult } from "@/lib/corpus";
import { quizHref, studyHref } from "@/lib/links";
import { findChapter, findSubject, loadSyllabusCached } from "@/lib/syllabus";

export const dynamic = "force-dynamic";

type PageProps = { params: Promise<{ subject: string; chapter: string }> };

async function resolve(params: PageProps["params"]) {
  const { subject: subjectSlug, chapter: chapterSlug } = await params;
  const load = await loadSyllabusCached();
  if (!load.syllabus) return { load, subject: null, chapter: null };
  const subject = findSubject(load.syllabus, subjectSlug);
  if (!subject) return { load, subject: null, chapter: null };
  const chapter = findChapter(subject, chapterSlug);
  return { load, subject, chapter };
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { subject, chapter } = await resolve(params);
  if (!subject || !chapter) return { title: "Chapter" };
  return { title: `${subject.name} ch ${chapter.no}: ${chapter.title}` };
}

export default async function ChapterPage({ params }: PageProps) {
  const { load, subject, chapter } = await resolve(params);
  if (!load.syllabus || !subject || !chapter) notFound();

  const health = await getHealthResult();
  const detail = await getChapterCorpus(subject.id, chapter.no, chapter, health);
  const sections = detail.sections ?? chapter.sections;

  return (
    <>
      <Breadcrumbs
        crumbs={[
          { label: "Home", href: "/" },
          { label: subject.name, href: `/${subject.id}` },
          { label: `Chapter ${chapter.no}` },
        ]}
      />

      <h1>
        Chapter {chapter.no}. {chapter.title}
      </h1>
      <p className="lede">
        {sections.length} section{sections.length === 1 ? "" : "s"}
        {chapter.pages ? ` · about ${chapter.pages} pages` : ""} in the {subject.name} book
        {chapter.pdf ? (
          <>
            {" "}
            (<code>{chapter.pdf}</code>)
          </>
        ) : null}
        . Section anchors below are the targets of the citation chips you get back from an answer.
      </p>

      {/* The global corpus banner is only informative here when the API itself is unreachable;
          otherwise the chapter-level notice below already says exactly what is known. */}
      {!health.ok ? (
        <CorpusNotice health={health} syllabusSource={load.source} syllabusPath={load.filePath} />
      ) : null}

      <ChapterStatusNotice status={detail.status} chapterNo={chapter.no} variant="chapter" />

      <section aria-labelledby="sections-heading">
        <h2 id="sections-heading">Sections</h2>
        <SectionList sections={sections} />
      </section>

      <p className="row">
        <Link className="button" href={studyHref(subject.id, chapter.no)}>
          Study this chapter — ask questions and take the quiz
        </Link>
        <Link className="button button--secondary" href={quizHref(subject.id, chapter.no)}>
          Go straight to the quiz
        </Link>
      </p>

      <AnimationHost
        subject={subject.id}
        subjectName={subject.name}
        chapterNo={chapter.no}
        chapterTitle={chapter.title}
      />
    </>
  );
}
