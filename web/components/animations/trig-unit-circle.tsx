'use client';

/**
 * Concept animation — CBSE Class 10 Mathematics, Ch 8 "Introduction to Trigonometry" (§8.2
 * Trigonometric Ratios).
 *
 * The unit circle drives everything: the angle is state, and sin/cos/tan are computed from it with
 * Math.sin / Math.cos at render time. Nothing on screen is a stored display value.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

export type ConceptAnimationProps = { className?: string };

const W = 680;
const H = 340;
const DEG = 180 / Math.PI;

/* circle panel */
const CX = 172;
const CY = 168;
const R = 112;
const AXIS = 142;

/* wave panel */
const WX0 = 372;
const WX1 = 660;
const WY = 168;
const AMP = 104;

const C = {
  bg: '#0b1020',
  grid: '#17233d',
  axis: '#6b7fa8',
  circle: '#60a5fa',
  radius: '#fbbf24',
  cosLeg: '#34d399',
  sinLeg: '#f87171',
  waveSin: '#f87171',
  waveCos: '#34d399',
  ink: '#e5e7eb',
  dim: '#94a3b8',
};

/** Shared per-file hook: React state only, no dependency outside React + the browser. */
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

export default function TrigUnitCircle({ className }: ConceptAnimationProps) {
  const [thetaDeg, setThetaDeg] = useState(35);
  const [showTraces, setShowTraces] = useState(true);
  const [playing, setPlaying] = useState(false);
  const reduced = useReducedMotion();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  /* ---- mathematics, recomputed from state on every render (never cached display values) ---- */
  const theta = (thetaDeg * Math.PI) / 180;
  const sinT = Math.sin(theta);
  const cosT = Math.cos(theta);
  const tanT = Math.tan(theta);
  const tanDefined = Math.abs(cosT) > 1e-12;
  const pythagorean = sinT * sinT + cosT * cosT;
  const px = CX + R * cosT;
  const py = CY - R * sinT;
  /* ---- drawing: canvas 2D, everything derived from the values above ---- */
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = prepare(canvas);
    if (!ctx) return;

    ctx.fillStyle = C.bg;
    ctx.fillRect(0, 0, W, H);
    ctx.font = '12px ui-sans-serif, system-ui, sans-serif';
    ctx.textBaseline = 'middle';

    /* ---- left: the unit circle ---- */
    ctx.strokeStyle = C.grid;
    ctx.lineWidth = 1;
    for (let g = -1; g <= 1; g += 0.5) {
      if (g === 0) continue;
      const gx = CX + R * g;
      const gy = CY - R * g;
      ctx.beginPath();
      ctx.moveTo(gx, CY - AXIS);
      ctx.lineTo(gx, CY + AXIS);
      ctx.moveTo(CX - AXIS, gy);
      ctx.lineTo(CX + AXIS, gy);
      ctx.stroke();
    }

    ctx.strokeStyle = C.axis;
    ctx.beginPath();
    ctx.moveTo(CX - AXIS, CY);
    ctx.lineTo(CX + AXIS, CY);
    ctx.moveTo(CX, CY - AXIS);
    ctx.lineTo(CX, CY + AXIS);
    ctx.stroke();

    ctx.fillStyle = C.dim;
    ctx.fillText('1', CX + R + 4, CY + 10);
    ctx.fillText('−1', CX - R - 20, CY + 10);
    ctx.fillText('1', CX + 6, CY - R);
    ctx.fillText('−1', CX + 6, CY + R);

    ctx.strokeStyle = C.circle;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(CX, CY, R, 0, Math.PI * 2);
    ctx.stroke();

    /* the right-angled triangle: cos along x, sin along y */
    ctx.lineWidth = 4;
    ctx.strokeStyle = C.cosLeg;
    ctx.beginPath();
    ctx.moveTo(CX, CY);
    ctx.lineTo(px, CY);
    ctx.stroke();
    ctx.strokeStyle = C.sinLeg;
    ctx.beginPath();
    ctx.moveTo(px, CY);
    ctx.lineTo(px, py);
    ctx.stroke();

    /* angle arc, drawn from the positive x-axis to the current angle */
    ctx.strokeStyle = C.radius;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(CX, CY, 34, 0, -theta, true);
    ctx.stroke();
    const mid = theta / 2;
    ctx.fillStyle = C.radius;
    ctx.fillText(
      `θ = ${thetaDeg}°`,
      CX + 46 * Math.cos(mid) - 18,
      CY - 46 * Math.sin(mid) + 10,
    );

    ctx.strokeStyle = C.radius;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(CX, CY);
    ctx.lineTo(px, py);
    ctx.stroke();

    ctx.fillStyle = C.ink;
    ctx.beginPath();
    ctx.arc(px, py, 5, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = C.dim;
    ctx.fillText('P(cos θ, sin θ)', px + 8, py - 12);

    /* ---- right: sin and cos traces, sampled from Math.sin / Math.cos ---- */
    if (showTraces) {
      ctx.strokeStyle = C.grid;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(WX0, WY);
      ctx.lineTo(WX1, WY);
      ctx.moveTo(WX0, WY - AMP);
      ctx.lineTo(WX1, WY - AMP);
      ctx.moveTo(WX0, WY + AMP);
      ctx.lineTo(WX1, WY + AMP);
      ctx.stroke();

      ctx.fillStyle = C.dim;
      ctx.fillText('1', WX1 + 4, WY - AMP);
      ctx.fillText('−1', WX1 + 4, WY + AMP);
      ctx.fillText('0°', WX0 - 4, WY + AMP + 14);
      ctx.fillText('360°', WX1 - 24, WY + AMP + 14);

      const samples = 361;
      ctx.lineWidth = 2;
      for (const [fn, colour] of [
        [Math.cos, C.waveCos],
        [Math.sin, C.waveSin],
      ] as const) {
        ctx.strokeStyle = colour;
        ctx.beginPath();
        for (let i = 0; i < samples; i++) {
          const d = (i * 360) / (samples - 1);
          const v = fn((d * Math.PI) / 180);
          const x = WX0 + (d / 360) * (WX1 - WX0);
          const y = WY - v * AMP;
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();
      }

      /* the current angle as a marker on both traces, using the same computed values */
      const markX = WX0 + (thetaDeg / 360) * (WX1 - WX0);
      ctx.setLineDash([3, 4]);
      ctx.strokeStyle = C.axis;
      ctx.beginPath();
      ctx.moveTo(markX, WY - AMP - 8);
      ctx.lineTo(markX, WY + AMP + 8);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = C.waveCos;
      ctx.beginPath();
      ctx.arc(markX, WY - cosT * AMP, 4, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = C.waveSin;
      ctx.beginPath();
      ctx.arc(markX, WY - sinT * AMP, 4, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = C.dim;
      ctx.fillText('cos θ (green)  sin θ (red)', WX0, WY + AMP + 34);
    }
  }, [thetaDeg, theta, px, py, sinT, cosT, showTraces]);

  useEffect(() => {
    draw();
  }, [draw]);

  /* ---- auto-sweep: motion only, and it never runs under prefers-reduced-motion ---- */
  useEffect(() => {
    if (!playing || reduced) return;
    let raf = 0;
    let last = 0;
    const step = (t: number) => {
      if (last && t - last >= 33) {
        last = t;
        setThetaDeg((d) => (d + 1) % 361);
      } else if (!last) {
        last = t;
      }
      raf = window.requestAnimationFrame(step);
    };
    raf = window.requestAnimationFrame(step);
    return () => window.cancelAnimationFrame(raf);
  }, [playing, reduced]);

  useEffect(() => {
    if (reduced && playing) setPlaying(false);
  }, [reduced, playing]);
  return (
    <section
      className={className}
      data-testid="trig-unit-circle"
      data-theta-deg={String(thetaDeg)}
      data-sin-raw={String(sinT)}
      data-cos-raw={String(cosT)}
      data-tan-raw={tanDefined ? String(tanT) : 'undefined'}
      data-pythagorean-raw={String(pythagorean)}
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
      <h3 style={{ margin: '0 0 4px', fontSize: 16, color: C.ink }}>
        Trigonometric ratios on the unit circle
      </h3>
      <p style={{ margin: '0 0 12px', fontSize: 13, color: C.dim }}>
        CBSE Class 10 Mathematics · Ch 8 §8.2 — the radius is 1, so the coordinates of P are
        (cos&nbsp;θ, sin&nbsp;θ).
      </p>

      <canvas
        ref={canvasRef}
        data-testid="trig-canvas"
        width={W}
        height={H}
        role="img"
        aria-label={`Unit circle at ${thetaDeg} degrees: sin is ${sinT.toFixed(3)}, cos is ${cosT.toFixed(3)}`}
        style={{ width: '100%', maxWidth: W, height: 'auto', display: 'block', borderRadius: 8 }}
      />

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 18, marginTop: 14 }}>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 13 }}>
          <span>Angle θ: {thetaDeg}°</span>
          <input
            type="range"
            min={0}
            max={360}
            step={1}
            value={thetaDeg}
            data-testid="trig-theta"
            aria-label="Angle theta in degrees"
            onChange={(e) => setThetaDeg(Number(e.target.value))}
            style={{ width: 220 }}
          />
        </label>

        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
          <input
            type="checkbox"
            checked={showTraces}
            data-testid="trig-traces"
            onChange={(e) => setShowTraces(e.target.checked)}
          />
          <span>Show sin / cos traces</span>
        </label>

        <button
          type="button"
          data-testid="trig-play"
          onClick={() => setPlaying((p) => !p)}
          disabled={reduced}
          aria-pressed={playing}
          style={{
            fontSize: 13,
            padding: '6px 12px',
            borderRadius: 8,
            border: '1px solid #5b6f96',
            background: playing ? '#1d4ed8' : '#111a2e',
            color: C.ink,
            cursor: reduced ? 'not-allowed' : 'pointer',
          }}
        >
          {playing ? 'Pause sweep' : 'Sweep θ'}
        </button>

        <button
          type="button"
          data-testid="trig-reset"
          onClick={() => {
            setPlaying(false);
            setThetaDeg(35);
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
          Reset
        </button>
      </div>

      {reduced ? (
        <p data-testid="trig-reduced-note" style={{ fontSize: 12, color: C.dim, margin: '10px 0 0' }}>
          Reduced motion is on, so the automatic sweep stays off — drag the slider to move θ
          yourself.
        </p>
      ) : null}

      <dl
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
          gap: 8,
          margin: '14px 0 0',
          fontSize: 13,
        }}
      >
        <div>
          <dt style={{ color: C.dim }}>sin θ</dt>
          <dd data-testid="trig-sin" style={{ margin: 0, color: C.waveSin }}>
            {sinT.toFixed(3)}
          </dd>
        </div>
        <div>
          <dt style={{ color: C.dim }}>cos θ</dt>
          <dd data-testid="trig-cos" style={{ margin: 0, color: C.waveCos }}>
            {cosT.toFixed(3)}
          </dd>
        </div>
        <div>
          <dt style={{ color: C.dim }}>tan θ = sin θ / cos θ</dt>
          <dd data-testid="trig-tan" style={{ margin: 0 }}>
            {tanDefined ? tanT.toFixed(3) : 'undefined (cos θ = 0)'}
          </dd>
        </div>
        <div>
          <dt style={{ color: C.dim }}>sin²θ + cos²θ</dt>
          <dd data-testid="trig-pythagorean" style={{ margin: 0 }}>
            {pythagorean.toFixed(6)}
          </dd>
        </div>
      </dl>

      <p data-testid="trig-what-to-notice" style={{ fontSize: 13, margin: '14px 0 0' }}>
        <strong>What to notice:</strong> sin θ and cos θ are just the legs of a right triangle drawn
        inside a circle of radius 1 — as θ sweeps, sin θ rises to 1 at 90° and falls back, while cos θ
        does the opposite, and sin²θ + cos²θ stays pinned at 1.
      </p>
      <p data-testid="trig-try-this" style={{ fontSize: 13, margin: '6px 0 0', color: C.dim }}>
        <strong>Try this:</strong> set θ = 90° and read tan θ — cos θ is 0 there, so the ratio is
        undefined. Then try θ = 45° and compare sin θ with cos θ.
      </p>
    </section>
  );
}
