'use client';

/**
 * Concept animation — CBSE Class 10 Mathematics, Ch 14 "Probability" (§14.1 Probability — A
 * Theoretical Approach).
 *
 * Every trial is a real random draw (Math.random). The relative frequency on screen is the recorded
 * hit count divided by the trial count — the animation never displays a number it did not measure.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

export type ConceptAnimationProps = { className?: string };

const W = 680;
const H = 360;
const CAP = 20000;

type Experiment = 'coin' | 'die-six' | 'die-even';

/* the theoretical probabilities are written as the counting that produces them */
const EXPERIMENTS: Record<Experiment, { label: string; p: number; note: string }> = {
  coin: { label: 'Coin toss — a head', p: 1 / 2, note: '1 favourable face out of 2' },
  'die-six': { label: 'Die roll — a six', p: 1 / 6, note: '1 favourable face out of 6' },
  'die-even': {
    label: 'Die roll — an even number',
    p: 3 / 6,
    note: '3 favourable faces out of 6',
  },
};

const EXPERIMENT_IDS: Experiment[] = ['coin', 'die-six', 'die-even'];

function drawOutcome(exp: Experiment): boolean {
  if (exp === 'coin') return Math.random() < 0.5;
  const face = Math.floor(Math.random() * 6) + 1;
  if (exp === 'die-six') return face === 6;
  return face % 2 === 0;
}

type SimState = { n: number; hits: number; history: number[]; last: boolean[] };

const EMPTY: SimState = { n: 0, hits: 0, history: [], last: [] };

const C = {
  bg: '#0b1020',
  grid: '#17233d',
  axis: '#6b7fa8',
  freq: '#60a5fa',
  theory: '#fbbf24',
  bar: '#34d399',
  ink: '#e5e7eb',
  dim: '#94a3b8',
  miss: '#1e293b',
};

function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    const apply = () => setReduced(mq.matches);
    apply();
    if (typeof mq.addEventListener === 'function') {
      mq.addEventListener('change', apply);
      return () => mq.removeEventListener('change', apply);
    }
    mq.addListener(apply);
    return () => mq.removeListener(apply);
  }, []);
  return reduced;
}

function prepare(canvas: HTMLCanvasElement): CanvasRenderingContext2D | null {
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;
  const dpr = typeof window === 'undefined' ? 1 : Math.min(window.devicePixelRatio || 1, 2);
  const w = Math.round(W * dpr);
  const h = Math.round(H * dpr);
  if (canvas.width !== w || canvas.height !== h) {
    canvas.width = w;
    canvas.height = h;
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);
  return ctx;
}

export default function ProbabilitySim({ className }: ConceptAnimationProps) {
  const [experiment, setExperiment] = useState<Experiment>('coin');
  const [sim, setSim] = useState<SimState>(EMPTY);
  const [auto, setAuto] = useState(false);
  const reduced = useReducedMotion();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  const active = EXPERIMENTS[experiment];
  const p = active.p;
  const freq = sim.n > 0 ? sim.hits / sim.n : 0;
  const gap = sim.n > 0 ? Math.abs(freq - p) : 0;
  const frequency = sim.history.length > 0 ? sim.history[sim.history.length - 1] : 0;
  /* ---- trials: a pure advance, so the button and the auto-runner share one implementation ---- */
  const advance = (prev: SimState, k: number, exp: Experiment): SimState => {
    const room = CAP - prev.n;
    const n = Math.max(0, Math.min(k, room));
    if (n === 0) return prev;
    let hits = prev.hits;
    const history = prev.history.slice();
    const last = prev.last.slice();
    for (let i = 0; i < n; i++) {
      const ok = drawOutcome(exp);
      if (ok) hits++;
      history.push(hits / (prev.n + i + 1));
      last.push(ok);
    }
    return {
      n: prev.n + n,
      hits,
      history,
      last: last.length > 120 ? last.slice(last.length - 120) : last,
    };
  };

  const run = useCallback(
    (k: number) => setSim((prev) => advance(prev, k, experiment)),
    [experiment],
  );

  const reset = useCallback(() => {
    setAuto(false);
    setSim(EMPTY);
  }, []);

  useEffect(() => {
    if (!auto || reduced) return;
    const id = window.setInterval(() => {
      setSim((prev) => advance(prev, 25, experiment));
    }, 120);
    return () => window.clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auto, reduced, experiment]);

  useEffect(() => {
    if (auto && (reduced || sim.n >= CAP)) setAuto(false);
  }, [auto, reduced, sim.n]);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = prepare(canvas);
    if (!ctx) return;

    ctx.fillStyle = C.bg;
    ctx.fillRect(0, 0, W, H);
    ctx.font = '12px ui-sans-serif, system-ui, sans-serif';
    ctx.textBaseline = 'middle';

    const L = 58;
    const R = 428;
    const T = 30;
    const B = 306;
    const py = (v: number) => B - v * (B - T);
    const maxN = Math.max(sim.n, 1);
    const px = (i: number) => L + (i / maxN) * (R - L);

    /* grid + y labels, 0 … 1 */
    ctx.strokeStyle = C.grid;
    ctx.lineWidth = 1;
    ctx.fillStyle = C.dim;
    for (let v = 0; v <= 1.0001; v += 0.25) {
      ctx.beginPath();
      ctx.moveTo(L, py(v));
      ctx.lineTo(R, py(v));
      ctx.stroke();
      ctx.fillText(v.toFixed(2), 12, py(v));
    }
    ctx.strokeStyle = C.axis;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(L, T);
    ctx.lineTo(L, B);
    ctx.lineTo(R, B);
    ctx.stroke();
    ctx.fillStyle = C.dim;
    ctx.fillText('relative frequency', 12, T - 12);
    ctx.fillText(`trials →  ${sim.n}`, R - 90, B + 18);

    /* the theoretical probability */
    ctx.setLineDash([6, 5]);
    ctx.strokeStyle = C.theory;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(L, py(p));
    ctx.lineTo(R, py(p));
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = C.theory;
    ctx.fillText(`theoretical p = ${p.toFixed(4)}`, L + 8, py(p) - 12);

    /* the measured relative frequency, decimated to fit the width */
    if (sim.n > 0) {
      const hist = sim.history;
      const step = Math.max(1, Math.ceil(hist.length / 420));
      const lastFreq = hist[hist.length - 1] ?? 0;
      ctx.strokeStyle = C.freq;
      ctx.lineWidth = 2;
      ctx.beginPath();
      for (let i = 0; i < hist.length; i += step) {
        const x = px(i + 1);
        const y = py(hist[i] ?? 0);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.lineTo(px(hist.length), py(lastFreq));
      ctx.stroke();

      ctx.fillStyle = C.freq;
      ctx.beginPath();
      ctx.arc(px(sim.n), py(lastFreq), 4.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillText(
        `observed ${lastFreq.toFixed(4)}`,
        Math.min(R - 110, px(sim.n) + 10),
        py(lastFreq) - 14,
      );
    } else {
      ctx.fillStyle = C.dim;
      ctx.fillText('Run some trials and the running frequency is plotted here.', L + 20, py(0.5));
    }

    /* right panel: the last 120 outcomes, then observed vs expected */
    ctx.fillStyle = C.dim;
    ctx.fillText('last 120 outcomes', 452, T - 12);
    const cols = 12;
    const cell = 15;
    for (let i = 0; i < sim.last.length; i++) {
      const cx = 452 + (i % cols) * cell;
      const cy = T + Math.floor(i / cols) * cell;
      ctx.fillStyle = sim.last[i] ? C.bar : C.miss;
      ctx.fillRect(cx, cy, cell - 4, cell - 4);
    }

    const base = B;
    const barH = 200;
    for (const [x, value, colour, label] of [
      [486, freq, C.freq, 'observed'],
      [586, p, C.theory, 'expected'],
    ] as const) {
      ctx.fillStyle = C.grid;
      ctx.fillRect(x - 30, base - barH, 60, barH);
      ctx.fillStyle = colour;
      const h = Math.max(0, Math.min(1, value)) * barH;
      ctx.fillRect(x - 30, base - h, 60, h);
      ctx.strokeStyle = C.axis;
      ctx.lineWidth = 1;
      ctx.strokeRect(x - 30, base - barH, 60, barH);
      ctx.fillStyle = colour;
      ctx.fillText(value.toFixed(4), x - 22, base - h - 12);
      ctx.fillStyle = C.dim;
      ctx.fillText(label, x - 26, base + 18);
    }
    ctx.fillStyle = C.dim;
    ctx.fillText(`hits ${sim.hits} / ${sim.n}`, 486, base + 40);
  }, [sim, p, freq]);
  useEffect(() => {
    draw();
  }, [draw]);

  const btn = {
    fontSize: 13,
    padding: '6px 12px',
    borderRadius: 8,
    border: '1px solid #5b6f96',
    background: '#111a2e',
    color: C.ink,
    cursor: 'pointer',
  } as const;

  return (
    <section
      className={className}
      data-testid="probability-sim"
      data-experiment={experiment}
      data-p={String(p)}
      data-trials={String(sim.n)}
      data-hits={String(sim.hits)}
      data-frequency={String(freq)}
      data-last-history={sim.history.length > 0 ? String(frequency) : 'none'}
      data-gap={String(gap)}
      data-cap={String(CAP)}
      data-reduced-motion={reduced ? 'true' : 'false'}
      style={{
        background: C.bg,
        color: C.ink,
        border: '1px solid #1f2a44',
        borderRadius: 12,
        padding: 16,
        fontFamily: 'ui-sans-serif, system-ui, sans-serif',
        maxWidth: W + 34,
      }}
    >
      <h3 style={{ margin: '0 0 4px', fontSize: 16 }}>Probability: watch the frequency settle</h3>
      <p style={{ margin: '0 0 12px', fontSize: 13, color: C.dim }}>
        CBSE Class 10 Mathematics · Ch 14 §14.1 — theoretical probability is what the relative
        frequency approaches as the number of trials grows.
      </p>

      <canvas
        ref={canvasRef}
        data-testid="prob-canvas"
        width={W}
        height={H}
        role="img"
        aria-label={`${sim.n} trials of ${active.label}; relative frequency ${freq.toFixed(4)} against theoretical ${p.toFixed(4)}`}
        style={{ width: '100%', maxWidth: W, height: 'auto', display: 'block', borderRadius: 8 }}
      />

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center', marginTop: 14 }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
          <span>Experiment</span>
          <select
            value={experiment}
            data-testid="prob-experiment"
            aria-label="Which random experiment to run"
            onChange={(e) => {
              setExperiment(e.target.value as Experiment);
              setAuto(false);
              setSim(EMPTY);
            }}
            style={{
              fontSize: 13,
              padding: '5px 8px',
              borderRadius: 8,
              background: '#111a2e',
              color: C.ink,
              border: '1px solid #5b6f96',
            }}
          >
            {EXPERIMENT_IDS.map((id) => (
              <option key={id} value={id}>
                {EXPERIMENTS[id].label}
              </option>
            ))}
          </select>
        </label>
        <span style={{ fontSize: 12, color: C.dim }}>{active.note}</span>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center', marginTop: 12 }}>
        {[1, 10, 100, 1000].map((k) => (
          <button
            key={k}
            type="button"
            data-testid={`prob-run-${k}`}
            onClick={() => run(k)}
            disabled={sim.n >= CAP}
            style={{ ...btn, opacity: sim.n >= CAP ? 0.5 : 1 }}
          >
            Run {k}
          </button>
        ))}
        <button
          type="button"
          data-testid="prob-auto"
          aria-pressed={auto}
          onClick={() => setAuto((a) => !a)}
          disabled={reduced}
          style={{
            ...btn,
            background: auto ? '#1d4ed8' : '#111a2e',
            cursor: reduced ? 'not-allowed' : 'pointer',
          }}
        >
          {auto ? 'Pause auto-run' : 'Auto-run'}
        </button>
        <button type="button" data-testid="prob-reset" onClick={reset} style={btn}>
          Reset
        </button>
      </div>

      {reduced ? (
        <p data-testid="prob-reduced-note" style={{ fontSize: 12, color: C.dim, margin: '10px 0 0' }}>
          Reduced motion is on, so the auto-runner is disabled — use the Run buttons, which update the
          graph instantly.
        </p>
      ) : null}

      <dl
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
          gap: 8,
          margin: '14px 0 0',
          fontSize: 13,
        }}
      >
        <div>
          <dt style={{ color: C.dim }}>trials run</dt>
          <dd data-testid="prob-trials" style={{ margin: 0 }}>
            {sim.n}
          </dd>
        </div>
        <div>
          <dt style={{ color: C.dim }}>successes</dt>
          <dd data-testid="prob-hits" style={{ margin: 0 }}>
            {sim.hits}
          </dd>
        </div>
        <div>
          <dt style={{ color: C.dim }}>relative frequency</dt>
          <dd data-testid="prob-freq" style={{ margin: 0, color: C.freq }}>
            {sim.n > 0 ? freq.toFixed(4) : '—'}
          </dd>
        </div>
        <div>
          <dt style={{ color: C.dim }}>theoretical probability</dt>
          <dd data-testid="prob-p" style={{ margin: 0, color: C.theory }}>
            {p.toFixed(4)}
          </dd>
        </div>
        <div>
          <dt style={{ color: C.dim }}>|observed − theoretical|</dt>
          <dd data-testid="prob-gap" style={{ margin: 0 }}>
            {sim.n > 0 ? gap.toFixed(4) : '—'}
          </dd>
        </div>
        <div>
          <dt style={{ color: C.dim }}>trials left before the {CAP.toLocaleString()} cap</dt>
          <dd data-testid="prob-room" style={{ margin: 0 }}>
            {CAP - sim.n}
          </dd>
        </div>
      </dl>

      <p data-testid="prob-what-to-notice" style={{ fontSize: 13, margin: '14px 0 0' }}>
        <strong>What to notice:</strong> a single toss is unpredictable, but the running relative
        frequency (blue) swings wildly for a few trials and then hugs the theoretical line (amber) more
        and more tightly — that is the empirical meaning of probability.
      </p>
      <p data-testid="prob-try-this" style={{ fontSize: 13, margin: '6px 0 0', color: C.dim }}>
        <strong>Try this:</strong> run 10 trials and note the gap, then run 1000 and compare the two
        gaps. Switch to the die and watch the same machinery converge on 1/6 instead of 1/2.
      </p>
    </section>
  );
}
