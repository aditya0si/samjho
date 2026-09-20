'use client';

/**
 * Concept animation — CBSE Class 10 Mathematics, Ch 10 "Circles" (§10.2 Tangent to a Circle).
 *
 * The radius r and the distance OP of the external point are state. The tangent length, the tangent
 * points, the right angle at the point of contact and the tangent–secant product are all computed
 * from those two numbers.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

export type ConceptAnimationProps = { className?: string };

const W = 680;
const H = 360;

const C = {
  bg: '#0b1020',
  grid: '#17233d',
  axis: '#6b7fa8',
  circle: '#60a5fa',
  tangent: '#fbbf24',
  radius: '#34d399',
  secant: '#c084fc',
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

export default function CircleTangents({ className }: ConceptAnimationProps) {
  const [r, setR] = useState(2);
  const [op, setOp] = useState(5);
  const [showSecant, setShowSecant] = useState(true);
  const reduced = useReducedMotion();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  /* ---- mathematics from r and OP ---- */
  const external = op > r + 1e-9;
  const pt = external ? Math.sqrt(op * op - r * r) : NaN; // tangent length
  const ptSquared = external ? pt * pt : NaN;
  const circleToP = op * op - r * r; // what the tangent length squared must equal
  // tangent points, computed from the right-triangle relation r² = OT · projection
  const tX = external ? (r * r) / op : NaN;
  const tY = external ? (r * pt) / op : NaN;
  // secant through the centre: near point A and far point B
  const pa = op - r;
  const pb = op + r;
  const paTimesPb = pa * pb;
  // perpendicularity check: vector OT · vector TP should vanish
  const dotOTPT = external ? tX * (op - tX) + tY * (0 - tY) : NaN;
  const angleOPT = external ? (Math.atan(r / pt) * 180) / Math.PI : NaN;
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = prepare(canvas);
    if (!ctx) return;

    ctx.fillStyle = C.bg;
    ctx.fillRect(0, 0, W, H);
    ctx.font = '12px ui-sans-serif, system-ui, sans-serif';
    ctx.textBaseline = 'middle';

    const worldX0 = -(r + 0.6);
    const worldX1 = op + 0.8;
    const worldW = worldX1 - worldX0;
    const yHalfWorld = Math.max(r * 1.35, 1);
    const s = Math.min((W - 70) / worldW, (H - 86) / (2 * yHalfWorld));
    const ox = 36 + (0 - worldX0) * s;
    const oy = H / 2 - 12;
    const X = (x: number) => ox + x * s;
    const Y = (y: number) => oy - y * s;

    /* the line OP, the reference direction */
    ctx.setLineDash([4, 5]);
    ctx.strokeStyle = C.grid;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(X(-r * 1.3), Y(0));
    ctx.lineTo(X(op * 1.02), Y(0));
    ctx.stroke();
    ctx.setLineDash([]);

    /* the circle */
    ctx.strokeStyle = C.circle;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(X(0), Y(0), r * s, 0, Math.PI * 2);
    ctx.stroke();

    /* secant through the centre: P → A → O → B */
    if (showSecant) {
      ctx.strokeStyle = C.secant;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(X(op), Y(0));
      ctx.lineTo(X(-r - 0.35), Y(0));
      ctx.stroke();
      for (const [ptx, label, dy] of [
        [r, 'A', 16],
        [-r, 'B', 16],
      ] as const) {
        ctx.fillStyle = C.secant;
        ctx.beginPath();
        ctx.arc(X(ptx), Y(0), 4.5, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = C.dim;
        ctx.fillText(label, X(ptx) - 4, Y(0) + dy);
      }
    }

    /* centre and external point */
    ctx.fillStyle = C.ink;
    ctx.beginPath();
    ctx.arc(X(0), Y(0), 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillText('O', X(0) - 14, Y(0) - 12);
    ctx.beginPath();
    ctx.arc(X(op), Y(0), 4.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillText('P', X(op) + 8, Y(0) - 12);

    if (external) {
      /* both tangents from P, and the radii to the points of contact */
      for (const sign of [1, -1] as const) {
        const tx = tX;
        const ty = sign * tY;
        ctx.strokeStyle = C.radius;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(X(0), Y(0));
        ctx.lineTo(X(tx), Y(ty));
        ctx.stroke();

        ctx.strokeStyle = C.tangent;
        ctx.lineWidth = 2.5;
        ctx.beginPath();
        ctx.moveTo(X(op), Y(0));
        ctx.lineTo(X(tx), Y(ty));
        ctx.stroke();

        ctx.fillStyle = C.tangent;
        ctx.beginPath();
        ctx.arc(X(tx), Y(ty), 4.5, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = C.dim;
        ctx.fillText(sign > 0 ? 'T' : 'T′', X(tx) + (sign > 0 ? 6 : 6), Y(ty) + (sign > 0 ? -12 : 14));

        /* right angle at the point of contact, built from the two drawn directions */
        const ux = X(0) - X(tx);
        const uy = Y(0) - Y(ty);
        const vx = X(op) - X(tx);
        const vy = Y(0) - Y(ty);
        const lu = Math.hypot(ux, uy) || 1;
        const lv = Math.hypot(vx, vy) || 1;
        const k = 12;
        const ax = (ux / lu) * k;
        const ay = (uy / lu) * k;
        const bx2 = (vx / lv) * k;
        const by2 = (vy / lv) * k;
        ctx.strokeStyle = C.ink;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(X(tx) + ax, Y(ty) + ay);
        ctx.lineTo(X(tx) + ax + bx2, Y(ty) + ay + by2);
        ctx.lineTo(X(tx) + bx2, Y(ty) + by2);
        ctx.stroke();
      }

      ctx.fillStyle = C.radius;
      ctx.fillText(`OT = r = ${r.toFixed(2)}`, X(0) + 6, Y(0) + 18);
      ctx.fillStyle = C.tangent;
      ctx.fillText(
        `PT = √(OP² − r²) = ${pt.toFixed(3)}`,
        X(op) - 230,
        Y(0) - 26,
      );
    } else {
      ctx.fillStyle = C.tangent;
      ctx.fillText(
        op < r
          ? 'P is inside the circle — no tangent can be drawn through P'
          : 'P lies on the circle — exactly one tangent passes through P',
        X(0) - 150,
        Y(0) - r * s - 16,
      );
    }

    if (showSecant) {
      ctx.fillStyle = C.secant;
      ctx.fillText(
        `secant: PA·PB = ${pa.toFixed(3)} × ${pb.toFixed(3)} = ${paTimesPb.toFixed(3)}`,
        X(0) - 150,
        Y(0) + r * s + 26,
      );
    }
  }, [r, op, external, pt, tX, tY, pa, pb, paTimesPb, showSecant]);
  useEffect(() => {
    draw();
  }, [draw]);

  const fmt = (v: number, d = 3) => (Number.isFinite(v) ? v.toFixed(d) : '—');

  return (
    <section
      className={className}
      data-testid="circle-tangents"
      data-r={String(r)}
      data-op={String(op)}
      data-external={external ? 'true' : 'false'}
      data-tangent-length={external ? String(pt) : 'none'}
      data-tangent-squared={external ? String(ptSquared) : 'none'}
      data-op-squared-minus-r-squared={String(circleToP)}
      data-pa={String(pa)}
      data-pb={String(pb)}
      data-pa-times-pb={String(paTimesPb)}
      data-dot-ot-pt={external ? String(dotOTPT) : 'none'}
      data-angle-opt={external ? String(angleOPT) : 'none'}
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
      <h3 style={{ margin: '0 0 4px', fontSize: 16 }}>Tangent length from an external point</h3>
      <p style={{ margin: '0 0 12px', fontSize: 13, color: C.dim }}>
        CBSE Class 10 Mathematics · Ch 10 §10.2 — a tangent touches the circle at exactly one point, and
        the radius to that point is perpendicular to it.
      </p>

      <canvas
        ref={canvasRef}
        data-testid="tangent-canvas"
        width={W}
        height={H}
        role="img"
        aria-label={`Circle of radius ${r} with external point P at distance ${op}; tangent length ${external ? pt.toFixed(3) : 'undefined'}`}
        style={{ width: '100%', maxWidth: W, height: 'auto', display: 'block', borderRadius: 8 }}
      />

      <div style={{ display: 'grid', gap: 8, marginTop: 14 }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13 }}>
          <span style={{ width: 150 }}>radius r = {r.toFixed(2)}</span>
          <input
            type="range"
            min={0.5}
            max={4}
            step={0.05}
            value={r}
            data-testid="tan-r"
            aria-label="Radius of the circle"
            onChange={(e) => setR(Number(e.target.value))}
            style={{ flex: 1, maxWidth: 300 }}
          />
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13 }}>
          <span style={{ width: 150 }}>OP = {op.toFixed(2)}</span>
          <input
            type="range"
            min={0.6}
            max={6}
            step={0.05}
            value={op}
            data-testid="tan-op"
            aria-label="Distance OP from the centre to the external point"
            onChange={(e) => setOp(Number(e.target.value))}
            style={{ flex: 1, maxWidth: 300 }}
          />
        </label>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'center', marginTop: 12 }}>
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
          <input
            type="checkbox"
            checked={showSecant}
            data-testid="tan-secant-toggle"
            onChange={(e) => setShowSecant(e.target.checked)}
          />
          <span>Show secant through the centre</span>
        </label>
        <button
          type="button"
          data-testid="tan-reset"
          onClick={() => {
            setR(2);
            setOp(5);
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

      <dl
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))',
          gap: 8,
          margin: '14px 0 0',
          fontSize: 13,
        }}
      >
        <div>
          <dt style={{ color: C.dim }}>tangent length PT = √(OP² − r²)</dt>
          <dd data-testid="tan-pt" style={{ margin: 0, color: C.tangent }}>
            {external ? fmt(pt) : 'no tangent from P'}
          </dd>
        </div>
        <div>
          <dt style={{ color: C.dim }}>OP² − r²</dt>
          <dd data-testid="tan-op2mr2" style={{ margin: 0 }}>
            {fmt(circleToP)}
          </dd>
        </div>
        <div>
          <dt style={{ color: C.dim }}>secant PA · PB = (OP − r)(OP + r)</dt>
          <dd data-testid="tan-secant" style={{ margin: 0, color: C.secant }}>
            {fmt(paTimesPb)}
          </dd>
        </div>
        <div>
          <dt style={{ color: C.dim }}>∠OPT (should be arcsin(r/OP))</dt>
          <dd data-testid="tan-angle" style={{ margin: 0 }}>
            {external ? `${fmt(angleOPT, 2)}°` : '—'}
          </dd>
        </div>
        <div>
          <dt style={{ color: C.dim }}>OT · TP (perpendicular ⇒ 0)</dt>
          <dd data-testid="tan-dot" style={{ margin: 0, color: C.radius }}>
            {external ? dotOTPT.toExponential(2) : '—'}
          </dd>
        </div>
      </dl>

      <p data-testid="tan-what-to-notice" style={{ fontSize: 13, margin: '14px 0 0' }}>
        <strong>What to notice:</strong> the two tangent lengths from P are equal, and PT² is exactly
        OP² − r². Switch the secant on and the same number reappears as PA · PB — the tangent–secant
        relation, PT² = PA · PB.
      </p>
      <p data-testid="tan-try-this" style={{ fontSize: 13, margin: '6px 0 0', color: C.dim }}>
        <strong>Try this:</strong> set OP = 5 and r = 3 — PT comes out exactly 4, the 3-4-5 triangle.
        Then drag OP down to r and watch the tangent length shrink to 0 as P lands on the circle.
      </p>
    </section>
  );
}
