'use client';

/**
 * Concept animation — CBSE Class 10 Mathematics, Ch 2 "Polynomials" (§2.2 Geometrical Meaning of
 * the Zeroes of a Polynomial).
 *
 * a, b, c are state. The roots, the discriminant, the vertex and the plotted curve are all computed
 * from them on every render — no stored display values.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

export type ConceptAnimationProps = { className?: string };

const W = 680;
const H = 360;
const PAD = { l: 46, r: 22, t: 22, b: 34 };

const C = {
  bg: '#0b1020',
  grid: '#17233d',
  axis: '#6b7fa8',
  curve: '#60a5fa',
  root: '#fbbf24',
  vertex: '#34d399',
  ink: '#e5e7eb',
  dim: '#94a3b8',
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

/** "1x² − 2x + 3" — built from the live coefficients, not from a stored string. */
function polyText(a: number, b: number, c: number): string {
  const sgn = (v: number) => (v < 0 ? '−' : '+');
  const abs = (v: number) => Math.abs(v);
  const bTxt = `${abs(b) === 1 ? '' : abs(b).toFixed(2)}x`;
  const cTxt = abs(c).toFixed(2);
  return `f(x) = ${a.toFixed(2)}x² ${sgn(b)} ${bTxt} ${sgn(c)} ${cTxt}`;
}

export default function QuadraticExplorer({ className }: ConceptAnimationProps) {
  const [a, setA] = useState(1);
  const [b, setB] = useState(-1);
  const [c, setC] = useState(-2);
  const [showVertex, setShowVertex] = useState(true);
  const reduced = useReducedMotion();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  /* ---- mathematics straight from a, b, c ---- */
  const quadratic = Math.abs(a) > 1e-12;
  const disc = b * b - 4 * a * c;
  const hasRealRoots = quadratic && disc >= 0;
  const root1 = hasRealRoots ? (-b - Math.sqrt(disc)) / (2 * a) : NaN;
  const root2 = hasRealRoots ? (-b + Math.sqrt(disc)) / (2 * a) : NaN;
  const axisX = quadratic ? -b / (2 * a) : NaN;
  const vertexY = quadratic ? a * axisX * axisX + b * axisX + c : NaN;
  // residual of each root against the polynomial actually plotted
  const rootResidual1 = hasRealRoots ? a * root1 * root1 + b * root1 + c : NaN;
  const rootResidual2 = hasRealRoots ? a * root2 * root2 + b * root2 + c : NaN;
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = prepare(canvas);
    if (!ctx) return;

    ctx.fillStyle = C.bg;
    ctx.fillRect(0, 0, W, H);
    ctx.font = '12px ui-sans-serif, system-ui, sans-serif';
    ctx.textBaseline = 'middle';

    const plotW = W - PAD.l - PAD.r;
    const plotH = H - PAD.t - PAD.b;

    /* view window: wide enough to hold the interesting points, then clamped so the graph stays legible */
    const spread = quadratic
      ? Math.max(Math.abs(root1) || 0, Math.abs(root2) || 0, Math.abs(axisX) || 0, 1)
      : 1;
    const xHalf = Math.min(12, Math.max(3, spread + 1.5));

    const N = 400;
    let yMin = Infinity;
    let yMax = -Infinity;
    const xs: number[] = [];
    const ys: number[] = [];
    for (let i = 0; i <= N; i++) {
      const x = -xHalf + (2 * xHalf * i) / N;
      const y = a * x * x + b * x + c;
      xs.push(x);
      ys.push(y);
      if (Number.isFinite(y)) {
        if (y < yMin) yMin = y;
        if (y > yMax) yMax = y;
      }
    }
    if (!Number.isFinite(yMin) || !Number.isFinite(yMax)) {
      yMin = -1;
      yMax = 1;
    }
    const yHalf = Math.min(14, Math.max(3, Math.max(Math.abs(yMin), Math.abs(yMax)) + 0.5));

    const toX = (x: number) => PAD.l + ((x + xHalf) / (2 * xHalf)) * plotW;
    const toY = (y: number) => PAD.t + ((yHalf - y) / (2 * yHalf)) * plotH;

    /* grid */
    ctx.strokeStyle = C.grid;
    ctx.lineWidth = 1;
    for (let gx = Math.ceil(-xHalf); gx <= xHalf; gx++) {
      ctx.beginPath();
      ctx.moveTo(toX(gx), PAD.t);
      ctx.lineTo(toX(gx), PAD.t + plotH);
      ctx.stroke();
    }
    for (let gy = Math.ceil(-yHalf); gy <= yHalf; gy++) {
      ctx.beginPath();
      ctx.moveTo(PAD.l, toY(gy));
      ctx.lineTo(PAD.l + plotW, toY(gy));
      ctx.stroke();
    }

    /* axes */
    ctx.strokeStyle = C.axis;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(PAD.l, toY(0));
    ctx.lineTo(PAD.l + plotW, toY(0));
    ctx.moveTo(toX(0), PAD.t);
    ctx.lineTo(toX(0), PAD.t + plotH);
    ctx.stroke();

    ctx.fillStyle = C.dim;
    for (let gx = Math.ceil(-xHalf); gx <= xHalf; gx++) {
      if (gx === 0) continue;
      ctx.fillText(String(gx), toX(gx) - 4, toY(0) + 12);
    }
    for (let gy = Math.ceil(-yHalf); gy <= yHalf; gy++) {
      if (gy === 0) continue;
      ctx.fillText(String(gy), PAD.l - 26, toY(gy));
    }

    /* the curve, sampled from a x² + b x + c, clipped to the plot rectangle */
    ctx.save();
    ctx.beginPath();
    ctx.rect(PAD.l, PAD.t, plotW, plotH);
    ctx.clip();
    ctx.strokeStyle = C.curve;
    ctx.lineWidth = 2.5;
    ctx.beginPath();
    let started = false;
    for (let i = 0; i <= N; i++) {
      const y = ys[i]!;
      if (!Number.isFinite(y)) {
        started = false;
        continue;
      }
      const sx = toX(xs[i]!);
      const sy = toY(y);
      if (!started) {
        ctx.moveTo(sx, sy);
        started = true;
      } else {
        ctx.lineTo(sx, sy);
      }
    }
    ctx.stroke();

    /* axis of symmetry + vertex */
    if (showVertex && quadratic) {
      ctx.setLineDash([5, 5]);
      ctx.strokeStyle = C.vertex;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(toX(axisX), PAD.t);
      ctx.lineTo(toX(axisX), PAD.t + plotH);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = C.vertex;
      ctx.beginPath();
      ctx.arc(toX(axisX), toY(vertexY), 5, 0, Math.PI * 2);
      ctx.fill();
    }

    /* roots */
    if (hasRealRoots) {
      for (const r of [root1, root2]) {
        if (Math.abs(r) <= xHalf) {
          ctx.fillStyle = C.root;
          ctx.beginPath();
          ctx.arc(toX(r), toY(0), 5.5, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    }
    ctx.restore();

    ctx.fillStyle = C.dim;
    ctx.fillText('x', PAD.l + plotW - 4, toY(0) - 12);
    ctx.fillText('y', toX(0) + 8, PAD.t + 8);
    if (!quadratic) {
      ctx.fillStyle = C.root;
      ctx.fillText('a = 0: this is a straight line, not a quadratic — no vertex, no quadratic roots', PAD.l + 10, PAD.t + 12);
    }
  }, [a, b, c, quadratic, disc, hasRealRoots, root1, root2, axisX, vertexY, showVertex]);
  useEffect(() => {
    draw();
  }, [draw]);

  const fmt = (v: number, d = 3) => (Number.isFinite(v) ? v.toFixed(d) : '—');

  return (
    <section
      className={className}
      data-testid="quadratic-explorer"
      data-a={String(a)}
      data-b={String(b)}
      data-c={String(c)}
      data-quadratic={quadratic ? 'true' : 'false'}
      data-disc={String(disc)}
      data-root1={hasRealRoots ? String(root1) : 'none'}
      data-root2={hasRealRoots ? String(root2) : 'none'}
      data-vertex-x={quadratic ? String(axisX) : 'none'}
      data-vertex-y={quadratic ? String(vertexY) : 'none'}
      data-residual1={hasRealRoots ? String(rootResidual1) : 'none'}
      data-residual2={hasRealRoots ? String(rootResidual2) : 'none'}
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
      <h3 style={{ margin: '0 0 4px', fontSize: 16 }}>
        Quadratic polynomials: roots and vertex
      </h3>
      <p style={{ margin: '0 0 12px', fontSize: 13, color: C.dim }}>
        CBSE Class 10 Mathematics · Ch 2 §2.2 — the zeroes of a polynomial are exactly where its graph
        crosses the x-axis.
      </p>

      <canvas
        ref={canvasRef}
        data-testid="quadratic-canvas"
        width={W}
        height={H}
        role="img"
        aria-label={`Graph of ${polyText(a, b, c)}; discriminant ${fmt(disc, 2)}`}
        style={{ width: '100%', maxWidth: W, height: 'auto', display: 'block', borderRadius: 8 }}
      />

      <div style={{ display: 'grid', gap: 8, marginTop: 14 }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13 }}>
          <span style={{ width: 92 }}>a = {a.toFixed(1)}</span>
          <input
            type="range"
            min={-3}
            max={3}
            step={0.1}
            value={a}
            data-testid="quad-a"
            aria-label="Coefficient a"
            onChange={(e) => setA(Number(e.target.value))}
            style={{ flex: 1, maxWidth: 300 }}
          />
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13 }}>
          <span style={{ width: 92 }}>b = {b.toFixed(1)}</span>
          <input
            type="range"
            min={-6}
            max={6}
            step={0.1}
            value={b}
            data-testid="quad-b"
            aria-label="Coefficient b"
            onChange={(e) => setB(Number(e.target.value))}
            style={{ flex: 1, maxWidth: 300 }}
          />
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13 }}>
          <span style={{ width: 92 }}>c = {c.toFixed(1)}</span>
          <input
            type="range"
            min={-6}
            max={6}
            step={0.1}
            value={c}
            data-testid="quad-c"
            aria-label="Coefficient c"
            onChange={(e) => setC(Number(e.target.value))}
            style={{ flex: 1, maxWidth: 300 }}
          />
        </label>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'center', marginTop: 12 }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
          <input
            type="checkbox"
            checked={showVertex}
            data-testid="quad-vertex-toggle"
            onChange={(e) => setShowVertex(e.target.checked)}
          />
          <span>Show vertex &amp; axis of symmetry</span>
        </label>
        <button
          type="button"
          data-testid="quad-reset"
          onClick={() => {
            setA(1);
            setB(-1);
            setC(-2);
          }}
          style={{
            fontSize: 13,
            padding: '6px 12px',
            borderRadius: 8,
            border: '1px solid #5b6f96',
            background: '#111a2e',
            color: C.ink,
            cursor: 'pointer',
          }}
        >
          Reset to x² − x − 2
        </button>
      </div>

      <p
        data-testid="quad-polynomial"
        style={{ margin: '14px 0 0', fontSize: 14, fontVariantNumeric: 'tabular-nums' }}
      >
        {polyText(a, b, c)}
      </p>

      <dl
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
          gap: 8,
          margin: '8px 0 0',
          fontSize: 13,
        }}
      >
        <div>
          <dt style={{ color: C.dim }}>discriminant D = b² − 4ac</dt>
          <dd data-testid="quad-disc" style={{ margin: 0 }}>
            {fmt(disc, 2)}
          </dd>
        </div>
        <div>
          <dt style={{ color: C.dim }}>roots (real)</dt>
          <dd data-testid="quad-roots" style={{ margin: 0, color: C.root }}>
            {hasRealRoots ? `${fmt(root1, 3)} , ${fmt(root2, 3)}` : quadratic ? 'none — D < 0' : 'not a quadratic'}
          </dd>
        </div>
        <div>
          <dt style={{ color: C.dim }}>vertex</dt>
          <dd data-testid="quad-vertex" style={{ margin: 0, color: C.vertex }}>
            {quadratic ? `(${fmt(axisX, 3)}, ${fmt(vertexY, 3)})` : '—'}
          </dd>
        </div>
        <div>
          <dt style={{ color: C.dim }}>check f(root)</dt>
          <dd data-testid="quad-check" style={{ margin: 0 }}>
            {hasRealRoots ? `${fmt(rootResidual1, 6)} , ${fmt(rootResidual2, 6)}` : '—'}
          </dd>
        </div>
      </dl>

      <p data-testid="quad-what-to-notice" style={{ fontSize: 13, margin: '14px 0 0' }}>
        <strong>What to notice:</strong> the yellow dots are the zeroes — the curve meets the x-axis
        exactly there, and the check row shows f(root) = 0. Push c up until D turns negative and the
        curve lifts off the axis: no real zeroes left.
      </p>
      <p data-testid="quad-try-this" style={{ fontSize: 13, margin: '6px 0 0', color: C.dim }}>
        <strong>Try this:</strong> set b = 0 and c = −4 with a = 1 — the roots are exactly ±2, the
        vertex sits on the y-axis. Then set c = 0 and watch one root slide to the origin.
      </p>
    </section>
  );
}
