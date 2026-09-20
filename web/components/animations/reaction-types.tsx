'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';

export type ConceptAnimationProps = { className?: string };

const W = 760;
const H = 470;

type Ctx = CanvasRenderingContext2D;

function useReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    setReduced(mq.matches);
    const onChange = (e: MediaQueryListEvent) => setReduced(e.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);
  return reduced;
}

function line(ctx: Ctx, x1: number, y1: number, x2: number, y2: number, color: string, width = 2.5) {
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(x2, y2);
  ctx.stroke();
}

function text(ctx: Ctx, s: string, x: number, y: number, color: string, size = 13, align: CanvasTextAlign = 'left') {
  ctx.fillStyle = color;
  ctx.font = `${size}px ui-sans-serif, system-ui, sans-serif`;
  ctx.textAlign = align;
  ctx.textBaseline = 'middle';
  ctx.fillText(s, x, y);
}

/**
 * Counts the atoms in a formula. Handles element symbols, subscripts and one
 * level of brackets with a multiplier, so Ca(OH)2 and Pb(NO3)2 work.
 */
function parseFormula(formula: string): Record<string, number> {
  const stack: Record<string, number>[] = [{}];
  let i = 0;
  while (i < formula.length) {
    const ch = formula[i]!;
    if (ch === '(') {
      stack.push({});
      i += 1;
    } else if (ch === ')') {
      i += 1;
      let num = '';
      while (i < formula.length && /[0-9]/.test(formula[i]!)) {
        num += formula[i]!;
        i += 1;
      }
      const mult = num ? parseInt(num, 10) : 1;
      const top = stack.pop() ?? {};
      const target = stack[stack.length - 1]!;
      Object.keys(top).forEach((k) => {
        target[k] = (target[k] ?? 0) + (top[k] ?? 0) * mult;
      });
    } else if (/[A-Z]/.test(ch)) {
      let sym = ch;
      i += 1;
      while (i < formula.length && /[a-z]/.test(formula[i]!)) {
        sym += formula[i]!;
        i += 1;
      }
      let num = '';
      while (i < formula.length && /[0-9]/.test(formula[i]!)) {
        num += formula[i]!;
        i += 1;
      }
      const target = stack[stack.length - 1]!;
      target[sym] = (target[sym] ?? 0) + (num ? parseInt(num, 10) : 1);
    } else {
      i += 1;
    }
  }
  while (stack.length > 1) {
    const top = stack.pop() ?? {};
    const target = stack[stack.length - 1]!;
    Object.keys(top).forEach((k) => {
      target[k] = (target[k] ?? 0) + (top[k] ?? 0);
    });
  }
  return stack[0]!;
}

type Species = { formula: string; state: 's' | 'l' | 'g' | 'aq'; name: string };
type Reaction = {
  id: string;
  label: string;
  type: string;
  energy: string;
  lhs: Species[];
  rhs: Species[];
  balanced: number[];
  note: string;
};

const REACTIONS: Reaction[] = [
  {
    id: 'mg-o2',
    label: 'Magnesium burning in air',
    type: 'Combination reaction',
    energy: 'exothermic (heat and light are given out)',
    lhs: [
      { formula: 'Mg', state: 's', name: 'magnesium' },
      { formula: 'O2', state: 'g', name: 'oxygen' },
    ],
    rhs: [{ formula: 'MgO', state: 's', name: 'magnesium oxide' }],
    balanced: [2, 1, 2],
    note: 'two atoms of magnesium and one molecule of oxygen give two formula units of magnesium oxide',
  },
  {
    id: 'cao-h2o',
    label: 'Quicklime in water',
    type: 'Combination reaction',
    energy: 'exothermic (the mixture gets hot)',
    lhs: [
      { formula: 'CaO', state: 's', name: 'calcium oxide' },
      { formula: 'H2O', state: 'l', name: 'water' },
    ],
    rhs: [{ formula: 'Ca(OH)2', state: 'aq', name: 'calcium hydroxide' }],
    balanced: [1, 1, 1],
    note: 'already balanced with every coefficient 1 — count the bracketed OH group as two O and two H',
  },
  {
    id: 'caco3',
    label: 'Limestone heated',
    type: 'Decomposition reaction (thermal)',
    energy: 'endothermic (heat must be supplied)',
    lhs: [{ formula: 'CaCO3', state: 's', name: 'calcium carbonate' }],
    rhs: [
      { formula: 'CaO', state: 's', name: 'calcium oxide' },
      { formula: 'CO2', state: 'g', name: 'carbon dioxide' },
    ],
    balanced: [1, 1, 1],
    note: 'one compound splitting into two — the atom counts already match',
  },
  {
    id: 'h2o-electrolysis',
    label: 'Water decomposed by electricity',
    type: 'Decomposition reaction (electrical)',
    energy: 'endothermic (electrical energy is supplied)',
    lhs: [{ formula: 'H2O', state: 'l', name: 'water' }],
    rhs: [
      { formula: 'H2', state: 'g', name: 'hydrogen' },
      { formula: 'O2', state: 'g', name: 'oxygen' },
    ],
    balanced: [2, 2, 1],
    note: 'you cannot balance this with whole molecules unless you take two waters at a time',
  },
  {
    id: 'fe-cuso4',
    label: 'Iron in copper sulphate solution',
    type: 'Displacement reaction',
    energy: 'heat change not stated in the chapter',
    lhs: [
      { formula: 'Fe', state: 's', name: 'iron' },
      { formula: 'CuSO4', state: 'aq', name: 'copper sulphate' },
    ],
    rhs: [
      { formula: 'FeSO4', state: 'aq', name: 'iron sulphate' },
      { formula: 'Cu', state: 's', name: 'copper' },
    ],
    balanced: [1, 1, 1, 1],
    note: 'the more reactive metal takes the sulphate over — the atom counts need no adjusting',
  },
  {
    id: 'pbno3-ki',
    label: 'Lead nitrate and potassium iodide',
    type: 'Double displacement reaction (precipitation)',
    energy: 'heat change not stated in the chapter',
    lhs: [
      { formula: 'Pb(NO3)2', state: 'aq', name: 'lead nitrate' },
      { formula: 'KI', state: 'aq', name: 'potassium iodide' },
    ],
    rhs: [
      { formula: 'PbI2', state: 's', name: 'lead iodide' },
      { formula: 'KNO3', state: 'aq', name: 'potassium nitrate' },
    ],
    balanced: [1, 2, 1, 2],
    note: 'ions swap partners; the yellow lead iodide leaves the solution as a solid',
  },
  {
    id: 'naoh-hcl',
    label: 'Hydrochloric acid and sodium hydroxide',
    type: 'Double displacement reaction (neutralisation)',
    energy: 'exothermic (the solution warms up)',
    lhs: [
      { formula: 'NaOH', state: 'aq', name: 'sodium hydroxide' },
      { formula: 'HCl', state: 'aq', name: 'hydrochloric acid' },
    ],
    rhs: [
      { formula: 'NaCl', state: 'aq', name: 'sodium chloride' },
      { formula: 'H2O', state: 'l', name: 'water' },
    ],
    balanced: [1, 1, 1, 1],
    note: 'an acid and a base giving a salt and water',
  },
  {
    id: 'ch4-o2',
    label: 'Methane burning',
    type: 'Combustion (an oxidation reaction)',
    energy: 'exothermic (heat and light are given out)',
    lhs: [
      { formula: 'CH4', state: 'g', name: 'methane' },
      { formula: 'O2', state: 'g', name: 'oxygen' },
    ],
    rhs: [
      { formula: 'CO2', state: 'g', name: 'carbon dioxide' },
      { formula: 'H2O', state: 'g', name: 'water vapour' },
    ],
    balanced: [1, 2, 1, 2],
    note: 'carbon and hydrogen are both oxidised — count the oxygens carefully',
  },
];

const ELEMENT_ORDER = ['C', 'H', 'O', 'N', 'Cl', 'Na', 'K', 'Ca', 'Mg', 'Fe', 'Cu', 'Pb', 'I', 'S'];

/** Reads a coefficient so a possibly-undefined index can never leak into the drawing. */
const at = (list: number[], i: number) => list[i] ?? 1;

function elementOrder(keys: string[]) {
  return [...keys].sort((a, b) => {
    const ia = ELEMENT_ORDER.indexOf(a);
    const ib = ELEMENT_ORDER.indexOf(b);
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib) || a.localeCompare(b);
  });
}

function sideTotals(species: Species[], coefficients: number[]) {
  const totals: Record<string, number> = {};
  species.forEach((sp, i) => {
    const atoms = parseFormula(sp.formula);
    Object.keys(atoms).forEach((el) => {
      totals[el] = (totals[el] ?? 0) + (atoms[el] ?? 0) * (coefficients[i] ?? 1);
    });
  });
  return totals;
}

function FormulaText({ formula }: { formula: string }) {
  const nodes: ReactNode[] = [];
  let buf = '';
  let k = 0;
  const flush = () => {
    if (buf) {
      nodes.push(<span key={`t${k}`}>{buf}</span>);
      k += 1;
      buf = '';
    }
  };
  for (const ch of formula) {
    if (/[0-9]/.test(ch)) {
      flush();
      nodes.push(<sub key={`s${k}`}>{ch}</sub>);
      k += 1;
    } else {
      buf += ch;
    }
  }
  flush();
  return <>{nodes}</>;
}

export default function ReactionTypes({ className }: ConceptAnimationProps) {
  const [id, setId] = useState(REACTIONS[0]!.id);
  const [playing, setPlaying] = useState(true);
  const reaction = useMemo(() => REACTIONS.find((r) => r.id === id) ?? REACTIONS[0]!, [id]);
  const species = useMemo(() => [...reaction.lhs, ...reaction.rhs], [reaction]);
  const [coeffs, setCoeffs] = useState<number[]>(() => reaction.lhs.concat(reaction.rhs).map(() => 1));

  const reduced = useReducedMotion();
  const animating = playing && !reduced;
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const tRef = useRef(0);
  const drawRef = useRef<() => void>(() => {});

  // choosing another reaction resets the coefficients
  const chooseReaction = (nextId: string) => {
    const next = REACTIONS.find((r) => r.id === nextId) ?? REACTIONS[0]!;
    setId(next.id);
    setCoeffs(next.lhs.concat(next.rhs).map(() => 1));
  };

  const lhsCoeffs = coeffs.slice(0, reaction.lhs.length);
  const rhsCoeffs = coeffs.slice(reaction.lhs.length);
  const lhsTotals = sideTotals(reaction.lhs, lhsCoeffs);
  const rhsTotals = sideTotals(reaction.rhs, rhsCoeffs);
  // de-duplicated: an element that appears on both sides must still get one row
  const elements = elementOrder(Array.from(new Set([...Object.keys(lhsTotals), ...Object.keys(rhsTotals)])));
  const mismatches = elements.filter((el) => (lhsTotals[el] ?? 0) !== (rhsTotals[el] ?? 0));
  const balanced = mismatches.length === 0;
  const totalLhs = Object.values(lhsTotals).reduce((a, b) => a + b, 0);
  const totalRhs = Object.values(rhsTotals).reduce((a, b) => a + b, 0);

  // the equation as plain text, for the canvas description
  const equationText = [
    reaction.lhs
      .map((sp, i) => `${at(lhsCoeffs, i) > 1 ? at(lhsCoeffs, i) : ''}${sp.formula}${sp.state ? `(${sp.state})` : ''}`)
      .join(' + '),
    reaction.rhs
      .map((sp, i) => `${at(rhsCoeffs, i) > 1 ? at(rhsCoeffs, i) : ''}${sp.formula}${sp.state ? `(${sp.state})` : ''}`)
      .join(' + '),
  ].join(' → ');

  const draw = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    ctx.fillStyle = '#0b1220';
    ctx.fillRect(0, 0, W, H);
    ctx.strokeStyle = '#1e293b';
    ctx.lineWidth = 1;
    ctx.strokeRect(0.5, 0.5, W - 1, H - 1);

    text(ctx, 'Atom tally — count the atoms on both sides', 24, 26, '#94a3b8', 14);
    text(ctx, `${reaction.label} · ${reaction.type}`, 24, 46, '#64748b', 12);

    const dotR = 7;
    const dotGap = 17;
    const cap = 12;
    const rowTop = 96;
    const rowH = Math.min(56, (H - 150) / Math.max(elements.length, 1));
    const scan = animating ? (tRef.current * 0.5) % 1 : 0;

    // a moving highlight that shows the rows are being scanned for a match
    if (animating && elements.length > 0) {
      const y = rowTop + scan * rowH * elements.length;
      ctx.fillStyle = 'rgba(56,189,248,0.06)';
      ctx.fillRect(20, y - rowH / 2, W - 40, rowH);
    }

    text(ctx, 'reactants', 120, rowTop - 24, '#fbbf24', 13);
    text(ctx, 'products', 420, rowTop - 24, '#34d399', 13);
    text(ctx, 'atom count on each side', 340, rowTop - 24, '#94a3b8', 12, 'center');

    elements.forEach((el, k) => {
      const y = rowTop + rowH * k;
      const left = lhsTotals[el] ?? 0;
      const right = rhsTotals[el] ?? 0;
      const match = left === right;

      text(ctx, el, 60, y, '#e2e8f0', 17, 'center');
      text(ctx, String(left), 96, y - 20, '#fbbf24', 12, 'center');
      for (let d = 0; d < Math.min(left, cap); d += 1) {
        ctx.fillStyle = match ? '#fbbf24' : '#f97316';
        ctx.beginPath();
        ctx.arc(108 + d * dotGap, y, dotR, 0, Math.PI * 2);
        ctx.fill();
      }
      if (left > cap) text(ctx, `+${left - cap}`, 108 + cap * dotGap, y, '#fbbf24', 12);

      text(ctx, match ? '=' : '≠', 330, y, match ? '#34d399' : '#f87171', 20, 'center');

      text(ctx, String(right), 400, y - 20, '#34d399', 12, 'center');
      for (let d = 0; d < Math.min(right, cap); d += 1) {
        ctx.fillStyle = match ? '#34d399' : '#f87171';
        ctx.beginPath();
        ctx.arc(412 + d * dotGap, y, dotR, 0, Math.PI * 2);
        ctx.fill();
      }
      if (right > cap) text(ctx, `+${right - cap}`, 412 + cap * dotGap, y, '#34d399', 12);
    });

    // coefficients in play, and the verdict, both from the live state
    text(
      ctx,
      `coefficients: ${coeffs.map((c, i) => `${c} ${species[i]?.formula ?? '?'}`).join(', ')}`,
      24,
      H - 58,
      '#94a3b8',
      12,
    );
    text(
      ctx,
      balanced
        ? `balanced — ${totalLhs} atoms on each side`
        : `not balanced — ${mismatches.length} element${mismatches.length === 1 ? '' : 's'} differ (${mismatches.join(', ')})`,
      24,
      H - 38,
      balanced ? '#34d399' : '#f87171',
      14,
    );
    text(
      ctx,
      `type: ${reaction.type} · energy: ${reaction.energy} (given for this reaction, not computed)`,
      24,
      H - 18,
      '#64748b',
      11,
    );
  };

  useEffect(() => {
    drawRef.current = draw;
    draw();
  });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = Math.min(2, typeof window !== 'undefined' ? window.devicePixelRatio || 1 : 1);
    canvas.width = Math.round(W * dpr);
    canvas.height = Math.round(H * dpr);
    const ctx = canvas.getContext('2d');
    if (ctx) ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    drawRef.current();
  }, []);

  useEffect(() => {
    if (!animating) return;
    let raf = 0;
    let last = performance.now();
    const step = (now: number) => {
      tRef.current += Math.min(0.05, (now - last) / 1000);
      last = now;
      drawRef.current();
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [animating]);

  const bump = (index: number, delta: number) => {
    setCoeffs((cs) => cs.map((c, i) => (i === index ? Math.max(1, Math.min(20, c + delta)) : c)));
  };

  return (
    <figure className={className} style={{ margin: 0, font: 'inherit' }}>
      <canvas
        ref={canvasRef}
        data-testid="rx-canvas"
        role="img"
        aria-label={`Atom tally for ${reaction.label}: ${equationText}, counting each element on both sides`}
        style={{ width: '100%', height: 'auto', display: 'block', borderRadius: 10 }}
      />
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem 1.5rem', marginTop: '0.75rem', alignItems: 'center' }}>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 13 }}>
          <span>reaction</span>
          <select
            value={id}
            aria-label="Choose a reaction"
            onChange={(e) => chooseReaction(e.target.value)}
            style={{ padding: '3px 6px', maxWidth: 320 }}
          >
            {REACTIONS.map((r) => (
              <option key={r.id} value={r.id}>
                {r.label}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={() => setCoeffs([...reaction.balanced])}
          aria-label="Fill in the balanced set of coefficients"
          style={{ padding: '5px 12px', cursor: 'pointer' }}
        >
          Show the balanced set
        </button>
        <button
          type="button"
          onClick={() => setCoeffs(coeffs.map(() => 1))}
          aria-label="Reset every coefficient to one"
          style={{ padding: '5px 12px', cursor: 'pointer' }}
        >
          Reset to 1
        </button>
        <button
          type="button"
          onClick={() => setPlaying((p) => !p)}
          disabled={reduced}
          aria-label={playing ? 'Pause the scan animation' : 'Play the scan animation'}
          style={{ padding: '5px 12px', cursor: reduced ? 'not-allowed' : 'pointer' }}
        >
          {playing ? 'Pause' : 'Play'}
        </button>
      </div>

      <div style={{ marginTop: '0.5rem', fontSize: 15 }} data-testid="rx-equation">
        {reaction.lhs.map((sp, i) => (
          <span key={`l${sp.formula}`}>
            {i > 0 ? ' + ' : ''}
            {at(lhsCoeffs, i) > 1 ? <strong>{at(lhsCoeffs, i)}</strong> : null}
            <FormulaText formula={sp.formula} />
            {sp.state ? `(${sp.state})` : ''}
          </span>
        ))}
        {' → '}
        {reaction.rhs.map((sp, i) => (
          <span key={`r${sp.formula}`}>
            {i > 0 ? ' + ' : ''}
            {at(rhsCoeffs, i) > 1 ? <strong>{at(rhsCoeffs, i)}</strong> : null}
            <FormulaText formula={sp.formula} />
            {sp.state ? `(${sp.state})` : ''}
          </span>
        ))}
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem 1rem', marginTop: '0.5rem', fontSize: 13 }}>
        {species.map((sp, i) => (
          <span key={`c${sp.name}`} style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
            <span style={{ color: '#64748b' }}>{sp.name}</span>
            <button
              type="button"
              onClick={() => bump(i, -1)}
              aria-label={`Decrease the coefficient of ${sp.name}`}
              style={{ width: 26, cursor: 'pointer' }}
            >
              −
            </button>
            <strong data-testid={`rx-coeff-${i}`}>{at(coeffs, i)}</strong>
            <button
              type="button"
              onClick={() => bump(i, 1)}
              aria-label={`Increase the coefficient of ${sp.name}`}
              style={{ width: 26, cursor: 'pointer' }}
            >
              +
            </button>
          </span>
        ))}
      </div>

      <p style={{ fontSize: 13, margin: '0.6rem 0 0.2rem' }} data-testid="rx-readout">
        <strong>What to notice:</strong>{' '}
        {balanced ? (
          <>
            the equation is balanced — {elements.map((el) => `${el} ${lhsTotals[el] ?? 0}`).join(', ')} on the left and the
            same on the right, so no atom was created or destroyed.
          </>
        ) : (
          <>
            the two sides disagree on {mismatches.join(', ')} — atoms are only moved around in a chemical reaction, never
            made or lost, so the coefficients have to be chosen to even them up.
          </>
        )}
      </p>
      <p style={{ fontSize: 13, margin: '0 0 0.2rem', color: '#475569' }}>
        <strong>Try this:</strong> pick <em>Water decomposed by electricity</em> and raise the water coefficient to 2 —
        the hydrogens now match but the oxygens do not until the oxygen molecule also gets a 2. Model note: only atom
        counts are computed here; reaction rates, energy barriers and the physical states drawn as (s)/(l)/(g)/(aq)
        labels are given, not simulated.
      </p>
      <p style={{ fontSize: 12, margin: 0, color: '#64748b' }}>
        live count — <span data-testid="rx-balanced">{balanced ? 'balanced' : 'not balanced'}</span>:{' '}
        <span data-testid="rx-atoms">
          {elements.map((el) => `${el} ${lhsTotals[el] ?? 0}=${rhsTotals[el] ?? 0}`).join(', ')}
        </span>
        ; totals {totalLhs} = {totalRhs} atoms
      </p>
    </figure>
  );
}
