'use client';

import { useEffect, useRef, useState } from 'react';

export type ConceptAnimationProps = { className?: string };

const W = 760;
const H = 470;

/** μ0 / 2π in T·m/A — the only physical constant this component needs. */
const MU0_OVER_2PI = 2e-7;
/** Earth's surface field, quoted as a scale reference (25–65 µT at the surface). */
const EARTH_FIELD_UT = 50;
/** Pixels per centimetre in the plan view; the probe and the field circles share it. */
const PX_PER_CM = 22;
/** Field lines are drawn at radii that step by a constant ratio (equal flux between them). */
const R0_CM = 0.5;
const RATIO = 1.57;

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

/** B in tesla for a long straight conductor, from the current and the distance in metres. */
function fieldTesla(currentA: number, rMetres: number) {
  if (rMetres <= 0) return 0;
  return (MU0_OVER_2PI * currentA) / rMetres;
}

export default function MagneticField({ className }: ConceptAnimationProps) {
  const [currentA, setCurrentA] = useState(5);
  const [probeCm, setProbeCm] = useState(2);
  const [outOfPage, setOutOfPage] = useState(true);
  const [playing, setPlaying] = useState(true);

  const reduced = useReducedMotion();
  const animating = playing && !reduced;
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const tRef = useRef(0);
  const drawRef = useRef<() => void>(() => {});

  // --- computed field quantities ---------------------------------------------
  const probeB = fieldTesla(currentA, probeCm / 100); // tesla at the probe
  const probeUT = probeB * 1e6;
  const atHalfCm = fieldTesla(currentA, 0.005) * 1e6;
  const circleRadiiCm = (() => {
    const out: number[] = [];
    let r = R0_CM;
    while (r <= 8 && out.length < 12) {
      out.push(r);
      r *= RATIO;
    }
    return out;
  })();
  const bMaxUT = atHalfCm;
  const sign = outOfPage ? 1 : -1; // screen sense of circulation: out of page → anticlockwise (right-hand thumb rule)

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

    const cx = 250;
    const cy = 250;
    const cmToPx = (cm: number) => cm * PX_PER_CM;

    text(ctx, 'Plan view of a straight conductor', 24, 26, '#94a3b8', 14);
    text(
      ctx,
      outOfPage ? 'current out of the page (⊙) — field circles anticlockwise' : 'current into the page (⊗) — field circles clockwise',
      24,
      46,
      '#64748b',
      12,
    );

    // field circles: equal-ratio radii, drawn with a marching dash whose speed ∝ I
    const dashOffset = sign * tRef.current * (6 + 9 * currentA);
    circleRadiiCm.forEach((rcm) => {
      const rpx = cmToPx(rcm);
      const rel = atHalfCm > 0 ? fieldTesla(currentA, rcm / 100) * 1e6 / atHalfCm : 0; // ∝ 1/r
      const alpha = Math.max(0.12, Math.min(0.95, rel));
      ctx.save();
      ctx.setLineDash([11, 9]);
      ctx.lineDashOffset = dashOffset;
      ctx.strokeStyle = `rgba(56,189,248,${alpha.toFixed(3)})`;
      ctx.lineWidth = 1 + 1.7 * alpha;
      ctx.beginPath();
      ctx.arc(cx, cy, rpx, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();

      // tangent arrowheads show the sense of the field
      [0.6, 2.7, 4.8].forEach((a0) => {
        const a = a0;
        const px = cx + rpx * Math.cos(a);
        const py = cy - rpx * Math.sin(a);
        const tx = -Math.sin(a) * sign;
        const ty = -Math.cos(a) * sign; // canvas y grows downward
        const ang = Math.atan2(ty, tx);
        const head = 9;
        ctx.fillStyle = `rgba(125,211,252,${Math.max(0.25, alpha).toFixed(3)})`;
        ctx.beginPath();
        ctx.moveTo(px + head * 0.6 * Math.cos(ang), py + head * 0.6 * Math.sin(ang));
        ctx.lineTo(px - head * 0.6 * Math.cos(ang) + head * 0.5 * Math.cos(ang + Math.PI / 2), py - head * 0.6 * Math.sin(ang) + head * 0.5 * Math.sin(ang + Math.PI / 2));
        ctx.lineTo(px - head * 0.6 * Math.cos(ang) + head * 0.5 * Math.cos(ang - Math.PI / 2), py - head * 0.6 * Math.sin(ang) + head * 0.5 * Math.sin(ang - Math.PI / 2));
        ctx.closePath();
        ctx.fill();
      });
    });

    // the conductor itself
    ctx.fillStyle = '#0b1220';
    ctx.strokeStyle = '#fbbf24';
    ctx.lineWidth = 2.6;
    ctx.beginPath();
    ctx.arc(cx, cy, 9, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    if (outOfPage) {
      ctx.fillStyle = '#fbbf24';
      ctx.beginPath();
      ctx.arc(cx, cy, 3.2, 0, Math.PI * 2);
      ctx.fill();
    } else {
      line(ctx, cx - 6, cy - 6, cx + 6, cy + 6, '#fbbf24', 2.6);
      line(ctx, cx - 6, cy + 6, cx + 6, cy - 6, '#fbbf24', 2.6);
    }
    text(ctx, `I = ${currentA.toFixed(1)} A`, cx, cy + 26, '#fbbf24', 13, 'center');

    // probe: distance from the wire, and the field there (needle follows the same sense)
    const probePx = cmToPx(probeCm);
    const pa = Math.PI / 3.1; // 58° above the horizontal, so it does not sit under the readouts
    const px = cx + probePx * Math.cos(pa);
    const py = cy - probePx * Math.sin(pa);
    ctx.save();
    ctx.setLineDash([5, 5]);
    line(ctx, cx, cy, px, py, '#a78bfa', 1.6);
    ctx.restore();
    text(ctx, `r = ${probeCm.toFixed(1)} cm`, (cx + px) / 2 + 4, (cy + py) / 2 - 10, '#a78bfa', 12);
    ctx.fillStyle = '#a78bfa';
    ctx.beginPath();
    ctx.arc(px, py, 4.5, 0, Math.PI * 2);
    ctx.fill();

    // a compass needle at the probe aligns with B (tangent to the circle)
    const tang = Math.atan2(-Math.cos(pa) * sign, -Math.sin(pa) * sign);
    const nl = 17;
    line(ctx, px - nl * Math.cos(tang), py - nl * Math.sin(tang), px + nl * Math.cos(tang), py + nl * Math.sin(tang), '#f87171', 2.4);
    line(ctx, px, py, px + nl * Math.cos(tang), py + nl * Math.sin(tang), '#e2e8f0', 2.4);
    text(ctx, 'compass needle points along B', px + 12, py + 18, '#f87171', 11);
    text(ctx, `B = ${probeUT.toFixed(1)} µT here`, px + 12, py + 34, '#a78bfa', 12);

    // ================= B against distance =================
    const gx0 = 452;
    const gy0 = 386;
    const gx1 = 736;
    const gy1 = 92;
    text(ctx, 'Field against distance', gx0, 26, '#94a3b8', 14);
    text(ctx, 'B ∝ 1/r for a long straight wire', gx0, 46, '#64748b', 12);
    line(ctx, gx0, gy0, gx1, gy0, '#64748b', 2);
    line(ctx, gx0, gy0, gx0, gy1, '#64748b', 2);
    text(ctx, 'r (cm)', gx1, gy0 + 18, '#64748b', 12, 'right');
    text(ctx, 'B (µT)', gx0 - 6, gy1 - 2, '#64748b', 12, 'right');

    const rMin = 0.5;
    const rMax = 8;
    const toX = (r: number) => gx0 + ((gx1 - gx0 - 8) * (r - rMin)) / (rMax - rMin);
    const toY = (b: number) => gy0 - ((gy0 - gy1) * b) / Math.max(bMaxUT, 1e-6);

    for (let k = 0; k <= 5; k += 1) {
      const r = rMin + ((rMax - rMin) * k) / 5;
      line(ctx, toX(r), gy0, toX(r), gy0 + 5, '#475569', 1.4);
      text(ctx, r.toFixed(1), toX(r), gy0 + 18, '#475569', 11, 'center');
    }
    const bTicks = 4;
    for (let k = 0; k <= bTicks; k += 1) {
      const b = (bMaxUT * k) / bTicks;
      line(ctx, gx0 - 5, toY(b), gx0, toY(b), '#475569', 1.4);
      text(ctx, b.toFixed(bMaxUT < 20 ? 1 : 0), gx0 - 8, toY(b), '#475569', 11, 'right');
    }

    ctx.strokeStyle = '#38bdf8';
    ctx.lineWidth = 2.4;
    ctx.beginPath();
    for (let k = 0; k <= 120; k += 1) {
      const r = rMin + ((rMax - rMin) * k) / 120;
      const b = fieldTesla(currentA, r / 100) * 1e6;
      const x = toX(r);
      const y = toY(b);
      if (k === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();

    // reference: the Earth's field, so the numbers have a scale
    if (EARTH_FIELD_UT <= bMaxUT) {
      ctx.save();
      ctx.setLineDash([4, 6]);
      line(ctx, gx0, toY(EARTH_FIELD_UT), gx1, toY(EARTH_FIELD_UT), '#475569', 1.4);
      ctx.restore();
      text(ctx, `Earth's field ≈ ${EARTH_FIELD_UT} µT (reference)`, gx1, toY(EARTH_FIELD_UT) - 12, '#64748b', 11, 'right');
    }

    // the probe marker on the curve
    ctx.fillStyle = '#a78bfa';
    ctx.beginPath();
    ctx.arc(toX(probeCm), toY(probeUT), 5, 0, Math.PI * 2);
    ctx.fill();
    text(ctx, `${probeUT.toFixed(1)} µT`, toX(probeCm) + 8, toY(probeUT) - 10, '#a78bfa', 12);

    // live arithmetic, computed from the same state
    text(ctx, `B = μ₀I / (2πr) = (2×10⁻⁷ × ${currentA.toFixed(1)}) / ${(probeCm / 100).toFixed(3)} m`, 24, 430, '#e2e8f0', 13);
    text(ctx, `= ${probeB.toExponential(2)} T = ${probeUT.toFixed(1)} µT at r = ${probeCm.toFixed(1)} cm`, 24, 450, '#e2e8f0', 13);
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

  return (
    <figure className={className} style={{ margin: 0, font: 'inherit' }}>
      <canvas
        ref={canvasRef}
        data-testid="mag-canvas"
        role="img"
        aria-label="Field lines circling a straight current-carrying conductor, with a graph of field strength against distance"
        style={{ width: '100%', height: 'auto', display: 'block', borderRadius: 10 }}
      />
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem 1.5rem', marginTop: '0.75rem', alignItems: 'center' }}>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 13 }}>
          <span>
            current I: <strong data-testid="mag-i">{currentA.toFixed(1)} A</strong>
          </span>
          <input
            type="range"
            min={0}
            max={10}
            step={0.5}
            value={currentA}
            aria-label="Current in amperes"
            onChange={(e) => setCurrentA(Number(e.target.value))}
            style={{ width: 200 }}
          />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 13 }}>
          <span>
            probe distance r: <strong data-testid="mag-r">{probeCm.toFixed(1)} cm</strong>
          </span>
          <input
            type="range"
            min={0.5}
            max={8}
            step={0.1}
            value={probeCm}
            aria-label="Distance from the conductor in centimetres"
            onChange={(e) => setProbeCm(Number(e.target.value))}
            style={{ width: 200 }}
          />
        </label>
        <button
          type="button"
          onClick={() => setOutOfPage((d) => !d)}
          aria-label="Reverse the direction of the current"
          style={{ padding: '5px 12px', cursor: 'pointer' }}
        >
          {outOfPage ? 'Current: out of page ⊙' : 'Current: into page ⊗'}
        </button>
        <button
          type="button"
          onClick={() => setPlaying((p) => !p)}
          disabled={reduced}
          aria-label={playing ? 'Pause the field animation' : 'Play the field animation'}
          style={{ padding: '5px 12px', cursor: reduced ? 'not-allowed' : 'pointer' }}
        >
          {playing ? 'Pause' : 'Play'}
        </button>
      </div>
      <p style={{ fontSize: 13, margin: '0.6rem 0 0.2rem' }} data-testid="mag-readout">
        <strong>What to notice:</strong> the field circles the wire with B = μ₀I/(2πr) — at {probeCm.toFixed(1)} cm it is{' '}
        {probeUT.toFixed(1)} µT, and moving the probe out to {Math.min(8, probeCm * 2).toFixed(1)} cm halves it, because
        doubling r halves B.
      </p>
      <p style={{ fontSize: 13, margin: '0 0 0.2rem', color: '#475569' }}>
        <strong>Try this:</strong> set I = 4 A and r = 2 cm, note the field, then double r to 4 cm and double I back to
        8 A — you get the same number twice, because B depends on I/r. Field lines are drawn at radii stepping by a
        constant ratio (×{RATIO}) so equal flux passes between neighbours; the drawing is a cross-section of an ideal
        infinitely long straight wire and does not model the field of the connecting leads.
      </p>
      <p style={{ fontSize: 12, margin: 0, color: '#64748b' }}>
        computed field at the probe: <span data-testid="mag-readout-b">{probeUT.toFixed(2)}</span> µT from{' '}
        <span data-testid="mag-readout-i">{currentA.toFixed(1)}</span> A at{' '}
        <span data-testid="mag-readout-r">{probeCm.toFixed(1)}</span> cm
      </p>
    </figure>
  );
}
