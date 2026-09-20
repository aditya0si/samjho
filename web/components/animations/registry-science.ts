import type * as React from 'react';

import ReflectionRefraction from './reflection-refraction';
import OhmLaw from './ohm-law';
import MagneticField from './magnetic-field';
import CarbonCompounds from './carbon-compounds';
import HumanEye from './human-eye';
import ReactionTypes from './reaction-types';

/**
 * Science concept animations for CBSE Class 10 (NCERT Science, book code jesc1).
 *
 * `chapterRef.subject` is the syllabus subject id ("science") and `chapterRef.chapter` is the
 * chapter number in data/syllabus/class10.json; `chapterRef.section` repeats a section title from
 * that file verbatim when a single section covers the animation.
 *
 * Sections are omitted where no single, cleanly extracted section title fits:
 *  - reflection-refraction spans §9.1 (reflection) and §9.3 (refraction);
 *  - reaction-types spans §1.2.1–§1.2.4, and the parent heading §1.2 is one of the titles the PDF's
 *    duplicate text layer still mangles ("TYPES OF CHEMICAL REA AL REACTIONS"), so it is not quoted.
 */
export const scienceAnimations: {
  conceptId: string;
  title: string;
  chapterRef: { subject: string; chapter: number; section?: string };
  Component: React.ComponentType<{ className?: string }>;
}[] = [
  {
    conceptId: 'reflection-refraction',
    title: 'Reflection at a plane mirror and refraction at a flat interface',
    chapterRef: { subject: 'science', chapter: 9 },
    Component: ReflectionRefraction,
  },
  {
    conceptId: 'ohm-law',
    title: 'Ohm\u2019s law: current from voltage and resistance, and the V\u2013I graph',
    chapterRef: { subject: 'science', chapter: 11, section: '11.4 OHM\u2019S LAW' },
    Component: OhmLaw,
  },
  {
    conceptId: 'magnetic-field-lines',
    title: 'Magnetic field lines around a straight current-carrying conductor',
    chapterRef: { subject: 'science', chapter: 12, section: '12.1 MAGNETIC FIELD AND FIELD LINES' },
    Component: MagneticField,
  },
  {
    conceptId: 'carbon-compounds',
    title: 'Carbon compounds: ball-and-stick models and the homologous series',
    chapterRef: { subject: 'science', chapter: 4, section: '4.2.1 Saturated and Unsaturated Carbon Compounds' },
    Component: CarbonCompounds,
  },
  {
    conceptId: 'human-eye',
    title: 'The human eye: accommodation, myopia and hypermetropia',
    chapterRef: { subject: 'science', chapter: 10, section: '10.1 THE HUMAN EYE' },
    Component: HumanEye,
  },
  {
    conceptId: 'reaction-types',
    title: 'Types of chemical reactions: balance the equation and watch the atom count',
    chapterRef: { subject: 'science', chapter: 1 },
    Component: ReactionTypes,
  },
];

export default scienceAnimations;
