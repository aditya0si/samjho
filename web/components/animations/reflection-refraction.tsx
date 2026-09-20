'use client';

import { useEffect, useRef, useState } from 'react';

export type ConceptAnimationProps = { className?: string };

const W = 760;
const H = 470;
const DEG = 180 / Math.PI;

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

function dashed(ctx: Ctx, x1: number, y1: number, x2: number, y2: number, color: string, width = 1.5) {
  ctx.save();
  ctx.setLineDash([7, 7]);
  line(ctx, x1, y1, x2, y2, color, width);
  ctx.restore();
}

function arrow(ctx: Ctx, x1: number, y1: number, x2: number, y2: number, color: string, width = 2.5) {
  const a = Math.atan2(y2 - y1, x2 - x1);
  const head = 12;
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.lineWidth = width;
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(x2, y2);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(x2, y2);
  ctx.lineTo(x2 - head * Math.cos(a - 0.42), y2 - head * Math.sin(a - 0.42));
  ctx.lineTo(x2 - head * Math.cos(a + 0.42), y2 - head * Math.sin(a + 0.42));
  ctx.closePath();
  ctx.fill();
}

function text(ctx: Ctx, s: string, x: number, y: number, color: string, size = 13, align: CanvasTextAlign = 'left') {
  ctx.fillStyle = color;
  ctx.font = `${size}px ui-sans-serif, system-ui, sans-serif`;
  ctx.textAlign = align;
  ctx.textBaseline = 'middle';
  ctx.fillText(s, x, y);
}

/** Travelling light dots along a segment, phase in [0,1). */
function pulse(
  ctx: Ctx,
  x1: number,
  y1: number,
  x2: number,
  y2: number,
  phase: number,
  count: number,
  color: string,
  offset = 0,
) {
  for (let k = 0; k < count; k += 1) {
    const p = (((phase + k / count + offset) % 1) + 1) % 1;
    const x = x1 + (x2 - x1) * p;
    const y = y1 + (y2 - y1) * p;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(x, y, 3.4, 0, Math.PI * 2);
    ctx.fill();
  }
}

function angleArc(
  ctx: Ctx,
  cx: number,
  cy: number,
  r: number,
  a0: number,
  a1: number,
  color: string,
  label: string,
) {
  ctx.strokeStyle = color;
  ctx.lineWidth = 1.8;
  ctx.beginPath();
  ctx.arc(cx, cy, r, a0, a1);
  ctx.stroke();
  const mid = (a0 + a1) / 2;
  text(ctx, label, cx + (r + 22) * Math.cos(mid), cy + (r + 22) * Math.sin(mid), color, 13, 'center');
}

export default function ReflectionRefraction({ className }: ConceptAnimationProps) {
  const [angleDeg, setAngleDeg] = useState(45);
  const [indexN, setIndexN] = useState(1.5);
  const [mode, setMode] = useState<'air-glass' | 'glass-air'>('air-glass');
  const [playing, setPlaying] = useState(true);

  const reduced = useReducedMotion();
  const animating = playing && !reduced;
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const tRef = useRef(0);
  const drawRef = useRef<() => void>(() => {});

  // --- physics, all derived from the two sliders -----------------------------
  const theta = (angleDeg * Math.PI) / 180; // angle of incidence, radians
  const n1 = mode === 'air-glass' ? 1 : indexN; // incident medium
  const n2 = mode === 'air-glass' ? indexN : 1; // second medium
  const sinI = Math.sin(theta);
  const sinT = (n1 / n2) * sinI;
  const totalInternalReflection = sinT > 1;
  const thetaT = totalInternalReflection ? NaN : Math.asin(sinT);
  const criticalAngle = n1 > n2 ? Math.asin(n2 / n1) : NaN;
  const ratio = totalInternalReflection ? NaN : sinI / Math.sin(thetaT);

  const draw = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const phase = (tRef.current * 0.32) % 1;

    ctx.fillStyle = '#0b1220';
    ctx.fillRect(0, 0, W, H);
    ctx.strokeStyle = '#1e293b';
    ctx.lineWidth = 1;
    ctx.strokeRect(0.5, 0.5, W - 1, H - 1);

    // ================= left panel: plane mirror =================
    const mx = 190;
    const my = 340;
    text(ctx, 'Plane mirror — reflection', 26, 26, '#94a3b8', 14);
    text(ctx, 'i = r, and the reflected ray stays on the other side of the normal', 26, 46, '#64748b', 12);

    // mirror surface with silvered hatching behind
    line(ctx, 24, my, 356, my, '#94a3b8', 4);
    for (let x = 34; x < 356; x += 15) {
      line(ctx, x, my, x - 10, my + 13, '#475569', 2);
    }

    dashed(ctx, mx, my, mx, my - 230, '#64748b', 1.4);
    text(ctx, 'normal', mx + 6, my - 236, '#64748b', 12);

    const L = 205;
    const ix = mx - L * Math.sin(theta);
    const iy = my - L * Math.cos(theta);
    const rx = mx + L * Math.sin(theta);
    const ry = my - L * Math.cos(theta);

    arrow(ctx, ix, iy, mx, my, '#fbbf24', 2.6);
    arrow(ctx, mx, my, rx, ry, '#38bdf8', 2.6);
    pulse(ctx, ix, iy, mx, my, phase, 6, '#fde68a');
    pulse(ctx, mx, my, rx, ry, phase, 6, '#bae6fd', 0.5);

    angleArc(ctx, mx, my, 66, -Math.PI / 2 - theta, -Math.PI / 2, '#fbbf24', `i = ${angleDeg.toFixed(1)}°`);
    angleArc(ctx, mx, my, 88, -Math.PI / 2, -Math.PI / 2 + theta, '#38bdf8', `r = ${angleDeg.toFixed(1)}°`);
    text(ctx, 'incident ray', ix - 4, iy - 14, '#fbbf24', 12);
    text(ctx, 'reflected ray', rx + 4, ry - 14, '#38bdf8', 12, 'left');
    ctx.fillStyle = '#fbbf24';
    ctx.beginPath();
    ctx.arc(mx, my, 4, 0, Math.PI * 2);
    ctx.fill();

    // ================= right panel: refraction at a flat interface ============
    const px = 570;
    const py = 300;
    const upperIsGlass = mode === 'glass-air';
    text(ctx, 'Flat interface — refraction', 410, 26, '#94a3b8', 14);
    text(
      ctx,
      upperIsGlass ? `glass (n = ${indexN.toFixed(2)}) above → air below` : `air above → glass (n = ${indexN.toFixed(2)}) below`,
      410,
      46,
      '#64748b',
      12,
    );

    // media
    ctx.fillStyle = upperIsGlass ? 'rgba(14,165,233,0.10)' : 'rgba(148,163,184,0.05)';
    ctx.fillRect(400, 60, 344, py - 60);
    ctx.fillStyle = upperIsGlass ? 'rgba(148,163,184,0.05)' : 'rgba(14,165,233,0.10)';
    ctx.fillRect(400, py, 344, H - 40 - py);
    line(ctx, 400, py, 744, py, '#0ea5e9', 2.4);
    text(ctx, 'interface', 744, py - 14, '#0ea5e9', 12, 'right');

    dashed(ctx, px, py, px, py - 220, '#64748b', 1.4);
    dashed(ctx, px, py, px, py + 150, '#64748b', 1.4);

    const hit = { x: px, y: py };
    const upLeft = { x: px - L * Math.sin(theta), y: py - L * Math.cos(theta) };
    const downLeft = { x: px - L * Math.sin(theta), y: py + L * Math.cos(theta) };

    if (!upperIsGlass) {
      // light enters from air above, bends toward the normal in the glass
      arrow(ctx, upLeft.x, upLeft.y, hit.x, hit.y, '#fbbf24', 2.6);
      pulse(ctx, upLeft.x, upLeft.y, hit.x, hit.y, phase, 6, '#fde68a');
      angleArc(ctx, px, py, 66, -Math.PI / 2 - theta, -Math.PI / 2, '#fbbf24', `i = ${angleDeg.toFixed(1)}°`);
      if (!totalInternalReflection) {
        const tx = px + L * Math.sin(thetaT);
        const ty = py + L * Math.cos(thetaT);
        arrow(ctx, hit.x, hit.y, tx, ty, '#34d399', 2.6);
        pulse(ctx, hit.x, hit.y, tx, ty, phase, 6, '#a7f3d0', 0.5);
        angleArc(ctx, px, py, 66, Math.PI / 2 - thetaT, Math.PI / 2, '#34d399', `r = ${(thetaT * DEG).toFixed(1)}°`);
        text(ctx, 'refracted ray', tx + 6, ty + 12, '#34d399', 12, 'left');
      }
      // weak partial reflection always exists
      arrow(ctx, hit.x, hit.y, px + L * Math.sin(theta), py - L * Math.cos(theta), 'rgba(148,163,184,0.75)', 1.4);
      text(ctx, 'weak reflection (~4%)', px + 96, py - 128, '#94a3b8', 11);
    } else {
      // light travels inside the glass and meets the air below: critical angle
      arrow(ctx, downLeft.x, downLeft.y, hit.x, hit.y, '#fbbf24', 2.6);
      pulse(ctx, downLeft.x, downLeft.y, hit.x, hit.y, phase, 6, '#fde68a');
      angleArc(ctx, px, py, 66, Math.PI / 2, Math.PI / 2 + theta, '#fbbf24', `i = ${angleDeg.toFixed(1)}°`);
      arrow(ctx, hit.x, hit.y, px + L * Math.sin(theta), py + L * Math.cos(theta), 'rgba(148,163,184,0.75)', 1.4);
      if (totalInternalReflection) {
        text(ctx, 'no refracted ray — total internal reflection', px, py + 26, '#f87171', 13, 'center');
      } else {
        const tx = px + L * Math.sin(thetaT);
        const ty = py - L * Math.cos(thetaT);
        arrow(ctx, hit.x, hit.y, tx, ty, '#34d399', 2.6);
        pulse(ctx, hit.x, hit.y, tx, ty, phase, 6, '#a7f3d0', 0.5);
        angleArc(ctx, px, py, 66, -Math.PI / 2, -Math.PI / 2 + thetaT, '#34d399', `r = ${(thetaT * DEG).toFixed(1)}°`);
        text(ctx, 'refracted ray (bends away from normal)', tx + 6, ty - 12, '#34d399', 12, 'left');
      }
      if (Number.isFinite(criticalAngle)) {
        const cDeg = criticalAngle * DEG;
        const crossed = angleDeg > cDeg;
        text(
          ctx,
          `critical angle = ${cDeg.toFixed(1)}°${crossed ? '  ← exceeded' : ''}`,
          570,
          458,
          crossed ? '#f87171' : '#94a3b8',
          12,
          'center',
        );
        const ca = Math.PI / 2 + criticalAngle;
        dashed(ctx, px, py, px + 150 * Math.cos(ca), py + 150 * Math.sin(ca), crossed ? '#f87171' : '#334155', 1.2);
      }
    }

    ctx.fillStyle = '#fbbf24';
    ctx.beginPath();
    ctx.arc(hit.x, hit.y, 4, 0, Math.PI * 2);
    ctx.fill();

    // ---- readouts drawn from the same state the DOM shows ----
    text(ctx, `sin i = ${sinI.toFixed(3)}`, 26, 414, '#e2e8f0', 13);
    text(
      ctx,
      totalInternalReflection ? 'sin r = — (no refracted ray)' : `sin r = ${Math.sin(thetaT).toFixed(3)}`,
      26,
      434,
      '#e2e8f0',
      13,
    );
    text(
      ctx,
      totalInternalReflection ? 'sin i / sin r = —' : `sin i / sin r = ${ratio.toFixed(2)} = n`,
      26,
      454,
      '#e2e8f0',
      13,
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

  return (
    <figure className={className} style={{ margin: 0, font: 'inherit' }}>
      <canvas
        ref={canvasRef}
        data-testid="rr-canvas"
        role="img"
        aria-label="Ray diagram: reflection at a plane mirror on the left, refraction at a flat interface on the right"
        style={{ width: '100%', height: 'auto', display: 'block', borderRadius: 10 }}
      />
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem 1.5rem', marginTop: '0.75rem', alignItems: 'center' }}>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 13 }}>
          <span>
            angle of incidence: <strong data-testid="rr-angle">{angleDeg.toFixed(1)}°</strong>
          </span>
          <input
            type="range"
            min={0}
            max={85}
            step={1}
            value={angleDeg}
            aria-label="Angle of incidence in degrees"
            onChange={(e) => setAngleDeg(Number(e.target.value))}
            style={{ width: 210 }}
          />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 13 }}>
          <span>
            refractive index n: <strong data-testid="rr-n">{indexN.toFixed(2)}</strong>
          </span>
          <input
            type="range"
            min={1}
            max={2.42}
            step={0.01}
            value={indexN}
            aria-label="Refractive index of the glass"
            onChange={(e) => setIndexN(Number(e.target.value))}
            style={{ width: 210 }}
          />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 13 }}>
          <span>direction</span>
          <select
            value={mode}
            aria-label="Direction of travel through the interface"
            onChange={(e) => setMode(e.target.value === 'glass-air' ? 'glass-air' : 'air-glass')}
            style={{ padding: '3px 6px' }}
          >
            <option value="air-glass">air → glass</option>
            <option value="glass-air">glass → air</option>
          </select>
        </label>
        <button
          type="button"
          onClick={() => setPlaying((p) => !p)}
          disabled={reduced}
          aria-label={playing ? 'Pause the light pulses' : 'Play the light pulses'}
          style={{ padding: '5px 12px', cursor: reduced ? 'not-allowed' : 'pointer' }}
        >
          {playing ? 'Pause' : 'Play'}
        </button>
      </div>
      <p style={{ fontSize: 13, margin: '0.6rem 0 0.2rem' }} data-testid="rr-readout">
        <strong>What to notice:</strong> the reflected ray always leaves at the same angle it arrived (i = r), while the
        refracted ray bends toward the normal on entering the denser medium and away from it on leaving — and{' '}
        {totalInternalReflection ? (
          <>past the critical angle it never leaves at all.</>
        ) : (
          <>
            sin i / sin r = {ratio.toFixed(2)} stays equal to the refractive index whatever the angle.
          </>
        )}
      </p>
      <p style={{ fontSize: 13, margin: '0 0 0.2rem', color: '#475569' }}>
        <strong>Try this:</strong> switch to <em>glass → air</em>, set n = 1.50 (critical angle 41.8°) and drag the
        angle past it — the refracted ray vanishes. Model note: the weak reflected beam is drawn at a fixed 4% of the
        incident light; reflectances are not computed from Fresnel&rsquo;s equations.
      </p>
    </figure>
  );
}
