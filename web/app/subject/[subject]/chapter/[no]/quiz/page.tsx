import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import Breadcrumbs from "@/components/Breadcrumbs";
import ChapterStatusNotice from "@/components/ChapterStatusNotice";
import CorpusNotice from "@/components/CorpusNotice";
import QuizRunner from "@/components/QuizRunner";
import { getChapterCorpus, getHealthResult } from "@/lib/corpus";
import { chapterHref, studyHref } from "@/lib/links";
import { findChapter, findSubject, loadSyllabusCached } from "@/lib/syllabus";

export const dynamic = "force-dynamic";

type PageProps = { params: Promise<{ subject: string; no: string }> };

async function resolve(params: PageProps["params"]) {
  const { subject: subjectSlug, no } = await params;
  const load = await loadSyllabusCached();
  if (!load.syllabus) return { load, subject: null, chapter: null };
  const subject = findSubject(load.syllabus, subjectSlug);
  if (!subject) return { load, subject: null, chapter: null };
  return { load, subject, chapter: findChapter(subject, no) };
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { subject, chapter } = await resolve(params);
  if (!subject || !chapter) return { title: "Quiz" };
  return { title: `Quiz: ${chapter.title} (${subject.name})` };
}

export default async function QuizPage({ params }: PageProps) {
  const { load, subject, chapter } = await resolve(params);
  if (!subject || !chapter) notFound();

  const health = await getHealthResult();
  const detail = await getChapterCorpus(subject.id, chapter.no, chapter, health);
  const sections = (detail.sections ?? chapter.sections).map((section) => ({
    no: section.no,
    title: section.title,
  }));

  return (
    <>
      <Breadcrumbs
        crumbs={[
          { label: "Home", href: "/" },
          { label: subject.name, href: `/${subject.id}` },
          { label: `Chapter ${chapter.no}`, href: chapterHref(subject.id, chapter.no) },
          { label: "Quiz" },
        ]}
      />

      <h1>
        Quiz · {chapter.title}
      </h1>
      <p className="lede">
        Questions are written from the passages ingested for this chapter and are marked against the
        marking key the API sends with each one. What you miss is mapped back to the section it came
        from, so the result tells you where to read next rather than just a number.
      </p>

      {/* Generating a quiz needs the API, so say so up front when it is unreachable. */}
      {!health.ok ? (
        <CorpusNotice
          health={health}
          syllabusSource={load.source}
          syllabusPath={load.filePath}
        />
      ) : null}

      <ChapterStatusNotice status={detail.status} chapterNo={chapter.no} variant="chapter" />

      <QuizRunner
        subject={subject.id}
        chapterNo={chapter.no}
        chapterTitle={chapter.title}
        sections={sections}
        corpusKnownEmpty={detail.status.ingested === false}
      />

      <p className="row">
        <Link className="button button--secondary" href={studyHref(subject.id, chapter.no)}>
          Back to studying chapter {chapter.no}
        </Link>
      </p>
    </>
  );
}
