import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import AnimationCount from "@/components/AnimationCount";
import Breadcrumbs from "@/components/Breadcrumbs";
import CorpusNotice from "@/components/CorpusNotice";
import EmptyState from "@/components/EmptyState";
import RetryButton from "@/components/RetryButton";
import StatusBadge from "@/components/StatusBadge";
import { getSubjectCorpus } from "@/lib/corpus";
import { chapterHref } from "@/lib/links";
import { findSubject, loadSyllabusCached } from "@/lib/syllabus";

export const dynamic = "force-dynamic";

type PageProps = { params: Promise<{ subject: string }> };

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { subject } = await params;
  const load = await loadSyllabusCached();
  const found = load.syllabus ? findSubject(load.syllabus, subject) : null;
  return { title: found ? `${found.name} — Class 10 chapters` : "Subject" };
}

export default async function SubjectPage({ params }: PageProps) {
  const { subject: slug } = await params;
  const load = await loadSyllabusCached();

  if (!load.syllabus) {
    return (
      <>
        <Breadcrumbs crumbs={[{ label: "Home", href: "/" }, { label: decodeURIComponent(slug) }]} />
        <h1>This subject&apos;s chapter list could not be read</h1>
        <EmptyState
          title="No syllabus available"
          tone="warn"
          action={<RetryButton label="Check again" />}
        >
          <p>
            Neither the API nor the local syllabus file answered, so the chapters of this subject
            cannot be listed. API: {load.apiError?.message ?? "no attempt recorded"} Local file:{" "}
            {load.fileError ?? "read"} (<code>{load.filePath}</code>)
          </p>
        </EmptyState>
      </>
    );
  }

  const subject = findSubject(load.syllabus, slug);
  if (!subject) notFound();

  const corpus = await getSubjectCorpus(subject);

  return (
    <>
      <Breadcrumbs crumbs={[{ label: "Home", href: "/" }, { label: subject.name }]} />
      <h1>
        {subject.name} <span className="subtle">· CBSE Class 10</span>
      </h1>
      <p className="lede">
        {subject.chapters.length} chapters
        {subject.book_code ? (
          <>
            {" "}
            · book code <code>{subject.book_code}</code>
          </>
        ) : null}
        . Chapter and section headings with page anchors come from the syllabus structure; the book
        text itself is never part of this site.
      </p>

      <CorpusNotice
        health={corpus.health}
        syllabusSource={load.source}
        syllabusPath={load.filePath}
        subject={{
          name: subject.name,
          ingestedChapters: corpus.ingestedChapters,
          totalChapters: corpus.totalChapters,
        }}
        detail={corpus.detail}
      />

      <h2>Chapters</h2>
      <ul className="link-list">
        {subject.chapters.map((chapter) => {
          const status = corpus.statuses.get(chapter.no);
          return (
            <li key={chapter.no}>
              <Link href={chapterHref(subject.id, chapter.no)}>
                Chapter {chapter.no}. {chapter.title}
                <span className="link-list__meta">
                  {chapter.sections.length} section{chapter.sections.length === 1 ? "" : "s"}
                  {chapter.pages ? ` · ${chapter.pages} pages` : ""} ·{" "}
                  <StatusBadge ingested={status?.ingested ?? null} /> ·{" "}
                  <AnimationCount subject={subject.id} chapterNo={chapter.no} />
                </span>
              </Link>
            </li>
          );
        })}
      </ul>

      <p className="subtle">
        &ldquo;Text ingested&rdquo; means the text of that chapter has been extracted from your own
        copy of the book on this machine and is available for answering. &ldquo;Text not
        ingested&rdquo; means samjho will refuse questions about it rather than answer from nothing.
      </p>
    </>
  );
}
