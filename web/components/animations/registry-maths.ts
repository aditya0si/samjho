/**
 * Mathematics concept-animation registry.
 *
 * CONTRACTS.md §6: the web builder imports this array and renders each `Component` on the chapter
 * page, so the export shape is frozen:
 *   { conceptId, title, chapterRef: { subject, chapter, section? }, Component }[]
 *
 * `subject` is the syllabus subject id from data/syllabus/class10.json ("maths"), `chapter` is the
 * chapter number in that book, and `section` is the section the concept maps to.
 */

import type { ComponentType } from 'react';

import CircleTangents from './circle-tangents';
import ProbabilitySim from './probability-sim';
import QuadraticExplorer from './quadratic-explorer';
import SimilarTriangles from './similar-triangles';
import TrigUnitCircle from './trig-unit-circle';

export type MathsAnimationEntry = {
  conceptId: string;
  title: string;
  chapterRef: { subject: string; chapter: number; section?: string };
  Component: ComponentType<{ className?: string }>;
};

export const mathsAnimations: MathsAnimationEntry[] = [
  {
    conceptId: 'quadratic-explorer',
    title: 'Quadratic polynomials — roots and vertex',
    chapterRef: { subject: 'maths', chapter: 2, section: '2.2' },
    Component: QuadraticExplorer,
  },
  {
    conceptId: 'similar-triangles',
    title: 'Similar triangles and the Basic Proportionality Theorem',
    chapterRef: { subject: 'maths', chapter: 6, section: '6.3' },
    Component: SimilarTriangles,
  },
  {
    conceptId: 'trig-unit-circle',
    title: 'Trigonometric ratios on the unit circle',
    chapterRef: { subject: 'maths', chapter: 8, section: '8.2' },
    Component: TrigUnitCircle,
  },
  {
    conceptId: 'circle-tangents',
    title: 'Circles and tangents — tangent length from an external point',
    chapterRef: { subject: 'maths', chapter: 10, section: '10.2' },
    Component: CircleTangents,
  },
  {
    conceptId: 'probability-sim',
    title: 'Probability — relative frequency converging to the theoretical value',
    chapterRef: { subject: 'maths', chapter: 14, section: '14.1' },
    Component: ProbabilitySim,
  },
];
