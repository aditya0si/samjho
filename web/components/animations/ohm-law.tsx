'use client';

import { useEffect, useRef, useState } from 'react';

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

/** 1, 2, 5 × 10^k — the smallest "nice" number ≥ x, so axis ticks are readable. */
function niceCeil(x: number) {
  if (!(x > 0)) return 1;
  const exp = Math.floor(Math.log10(x));
  const base = Math.pow(10, exp);
  const m = x / base;
  const step = m <= 1 ? 1 : m <= 2 ? 2 : m <= 5 ? 5 : 10;
  return step * base;
}

type Reading = { v: number; i: number; r: number };

const LOOP = [
  { x: 60, y: 110 },
  { x: 350, y: 110 },
  { x: 350, y: 360 },
  { x: 60, y: 360 },
];

function loopLength() {
  let total = 0;
  for (let k = 0; k < LOOP.length; k += 1) {
    const a = LOOP[k]!;
    const b = LOOP[(k + 1) % LOOP.length]!;
    total += Math.hypot(b.x - a.x, b.y - a.y);
  }
  return total;
}

/** Point at arclength s along the rectangular circuit, walking clockwise. */
function pointOnLoop(s: number) {
  const total = loopLength();
  let d = ((s % total) + total) % total;
  for (let k = 0; k < LOOP.length; k += 1) {
    const a = LOOP[k]!;
    const b = LOOP[(k + 1) % LOOP.length]!;
    const seg = Math.hypot(b.x - a.x, b.y - a.y);
    if (d <= seg) {
      return { x: a.x + ((b.x - a.x) * d) / seg, y: a.y + ((b.y - a.y) * d) / seg };
    }
    d -= seg;
  }
  return { x: LOOP[0]!.x, y: LOOP[0]!.y };
}

export default function OhmLaw({ className }: ConceptAnimationProps) {
  const [voltage, setVoltage] = useState(6);
  const [resistance, setResistance] = useState(5);
  const [readings, setReadings] = useState<Reading[]>([]);
  const [playing, setPlaying] = useState(true);

  const reduced = useReducedMotion();
  const animating = playing && !reduced;
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const tRef = useRef(0);
  const drawRef = useRef<() => void>(() => {});

  // --- everything below is computed from the two sliders, nothing hardcoded ---
  const current = voltage / resistance; // I = V / R
  const power = voltage * current; // P = V I

  const gx0 = 432;
  const gy0 = 400;
  const gx1 = 736;
  const gy1 = 92;
  const vMax = 12;
  const iMax = niceCeil(
    Math.max(
      0.5,
      current,
      readings.reduce((m, p) => Math.max(m, p.i), 0),
    ),
  );

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

    // ================= circuit =================
    text(ctx, 'Circuit', 30, 30, '#94a3b8', 14);
    text(ctx, `battery ${voltage.toFixed(1)} V, resistor ${resistance.toFixed(1)} Ω`, 30, 50, '#64748b', 12);

    const wire = '#cbd5e1';
    // top side, with a gap where the resistor sits
    line(ctx, 60, 110, 170, 110, wire, 2.6);
    line(ctx, 250, 110, 350, 110, wire, 2.6);
    line(ctx, 350, 110, 350, 360, wire, 2.6);
    line(ctx, 350, 360, 60, 360, wire, 2.6);
    line(ctx, 60, 360, 60, 275, wire, 2.6);
    line(ctx, 60, 205, 60, 110, wire, 2.6);

    // resistor as a zig-zag whose length is fixed but label carries the value
    ctx.strokeStyle = '#f97316';
    ctx.lineWidth = 2.8;
    ctx.beginPath();
    ctx.moveTo(170, 110);
    for (let k = 0; k < 8; k += 1) {
      const x = 170 + (k + 0.5) * 10;
      ctx.lineTo(x, k % 2 === 0 ? 92 : 128);
    }
    ctx.lineTo(250, 110);
    ctx.stroke();
    text(ctx, `R = ${resistance.toFixed(1)} Ω`, 210, 66, '#f97316', 13, 'center');

    // battery: long plate = +, short plate = −
    line(ctx, 40, 205, 80, 205, '#fbbf24', 3.4);
    line(ctx, 52, 275, 68, 275, '#fbbf24', 3.4);
    line(ctx, 60, 205, 60, 275, 'rgba(0,0,0,0)', 0);
    text(ctx, '+', 92, 205, '#fbbf24', 14);
    text(ctx, '−', 92, 275, '#fbbf24', 14);
    text(ctx, `${voltage.toFixed(1)} V`, 22, 240, '#fbbf24', 13, 'center');

    // ammeter
    ctx.strokeStyle = '#38bdf8';
    ctx.lineWidth = 2.4;
    ctx.beginPath();
    ctx.arc(350, 235, 22, 0, Math.PI * 2);
    ctx.stroke();
    ctx.fillStyle = '#0b1220';
    ctx.fill();
    text(ctx, 'A', 350, 235, '#38bdf8', 16, 'center');
    text(ctx, `I = ${current.toFixed(2)} A`, 384, 235, '#38bdf8', 13);

    // conventional current direction (opposite to the electron drift)
    const dir = 1; // conventional current leaves +, so clockwise on screen
    const arrowAt = (x: number, y: number, dx: number, dy: number) => {
      const a = Math.atan2(dy * dir, dx * dir);
      ctx.fillStyle = '#f97316';
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(x - 10 * Math.cos(a - 0.5), y - 10 * Math.sin(a - 0.5));
      ctx.lineTo(x - 10 * Math.cos(a + 0.5), y - 10 * Math.sin(a + 0.5));
      ctx.closePath();
      ctx.fill();
    };
    arrowAt(120, 110, 1, 0);
    arrowAt(300, 110, 1, 0);
    arrowAt(350, 170, 0, 1);
    arrowAt(350, 310, 0, 1);
    arrowAt(200, 360, -1, 0);
    arrowAt(120, 360, -1, 0);
    text(ctx, 'conventional current (drawn)', 240, 384, '#f97316', 11, 'center');

    // electron drift: speed is proportional to the computed current
    const speed = 40 * current; // px per second
    const total = loopLength();
    const nDots = 22;
    for (let k = 0; k < nDots; k += 1) {
      const s = -tRef.current * speed + (k / nDots) * total;
      const p = pointOnLoop(s);
      ctx.fillStyle = 'rgba(56,189,248,0.85)';
      ctx.beginPath();
      ctx.arc(p.x, p.y, 2.6, 0, Math.PI * 2);
      ctx.fill();
    }
    text(ctx, 'electron drift, opposite the current — speed ∝ I (freezes at 0 A)', 240, 402, '#64748b', 11, 'center');

    // ================= V–I graph =================
    text(ctx, 'V–I graph', 432, 30, '#94a3b8', 14);
    line(ctx, gx0, gy0, gx1, gy0, '#64748b', 2);
    line(ctx, gx0, gy0, gx0, gy1, '#64748b', 2);
    text(ctx, 'V (volts)', gx1, gy0 + 18, '#64748b', 12, 'right');
    text(ctx, 'I (amperes)', gx0 - 6, gy1 - 4, '#64748b', 12, 'right');

    const toX = (v: number) => gx0 + ((gx1 - gx0 - 10) * v) / vMax;
    const toY = (i: number) => gy0 - ((gy0 - gy1) * i) / iMax;

    for (let k = 0; k <= 6; k += 1) {
      const v = (vMax * k) / 6;
      const x = toX(v);
      line(ctx, x, gy0, x, gy0 + 5, '#475569', 1.4);
      text(ctx, v.toFixed(0), x, gy0 + 18, '#475569', 11, 'center');
    }
    const iStep = iMax / 5;
    for (let k = 0; k <= 5; k += 1) {
      const i = iStep * k;
      const y = toY(i);
      line(ctx, gx0 - 5, y, gx0, y, '#475569', 1.4);
      text(ctx, i.toFixed(iMax < 2 ? 1 : 0), gx0 - 8, y, '#475569', 11, 'right');
    }

    // the model line for the resistor currently dialled in: I = V / R, same numbers as the readout
    ctx.save();
    ctx.setLineDash([7, 6]);
    ctx.strokeStyle = '#f97316';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(toX(0), toY(0));
    ctx.lineTo(toX(vMax), toY(vMax / resistance));
    ctx.stroke();
    ctx.restore();
    text(ctx, `dashed: I = V / R for R = ${resistance.toFixed(1)} Ω (slope = 1/R)`, gx0 + 4, gy1 - 6, '#f97316', 11);

    // recorded readings, each carrying the R it was taken at
    readings.forEach((p, idx) => {
      const x = toX(p.v);
      const y = toY(p.i);
      ctx.fillStyle = Math.abs(p.r - resistance) < 1e-9 ? '#34d399' : '#a78bfa';
      ctx.beginPath();
      ctx.arc(x, y, 4.5, 0, Math.PI * 2);
      ctx.fill();
      if (idx === readings.length - 1) {
        text(ctx, `(${p.v.toFixed(1)} V, ${p.i.toFixed(2)} A, R = ${p.r.toFixed(1)} Ω)`, x + 8, y - 12, '#e2e8f0', 11);
      }
    });

    // the live operating point
    ctx.fillStyle = '#fbbf24';
    ctx.beginPath();
    ctx.arc(toX(voltage), toY(current), 6, 0, Math.PI * 2);
    ctx.fill();
    text(ctx, `now: ${voltage.toFixed(1)} V, ${current.toFixed(2)} A`, toX(voltage) + 10, toY(current) + 16, '#fbbf24', 12);

    // live numbers repeated on the canvas, computed from the same state
    text(ctx, `I = V / R = ${voltage.toFixed(1)} / ${resistance.toFixed(1)} = ${current.toFixed(3)} A`, 432, 438, '#e2e8f0', 13);
    text(ctx, `P = V I = ${power.toFixed(2)} W   ·   readings taken: ${readings.length}`, 432, 456, '#94a3b8', 12);
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
        data-testid="ohm-canvas"
        role="img"
        aria-label="A series circuit with a battery and a resistor on the left, and a voltage-current graph on the right"
        style={{ width: '100%', height: 'auto', display: 'block', borderRadius: 10 }}
      />
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem 1.5rem', marginTop: '0.75rem', alignItems: 'center' }}>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 13 }}>
          <span>
            battery voltage V: <strong data-testid="ohm-v">{voltage.toFixed(1)} V</strong>
          </span>
          <input
            type="range"
            min={0}
            max={12}
            step={0.5}
            value={voltage}
            aria-label="Battery voltage in volts"
            onChange={(e) => setVoltage(Number(e.target.value))}
            style={{ width: 200 }}
          />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 13 }}>
          <span>
            resistance R: <strong data-testid="ohm-r">{resistance.toFixed(1)} Ω</strong>
          </span>
          <input
            type="range"
            min={1}
            max={20}
            step={0.5}
            value={resistance}
            aria-label="Resistance in ohms"
            onChange={(e) => setResistance(Number(e.target.value))}
            style={{ width: 200 }}
          />
        </label>
        <button
          type="button"
          onClick={() => setReadings((rs) => [...rs, { v: voltage, i: current, r: resistance }].slice(-40))}
          aria-label="Record the current reading on the graph"
          style={{ padding: '5px 12px', cursor: 'pointer' }}
        >
          Record reading
        </button>
        <button
          type="button"
          onClick={() => setReadings([])}
          aria-label="Clear all recorded readings"
          style={{ padding: '5px 12px', cursor: 'pointer' }}
        >
          Clear
        </button>
        <button
          type="button"
          onClick={() => setPlaying((p) => !p)}
          disabled={reduced}
          aria-label={playing ? 'Pause the electron drift' : 'Play the electron drift'}
          style={{ padding: '5px 12px', cursor: reduced ? 'not-allowed' : 'pointer' }}
        >
          {playing ? 'Pause' : 'Play'}
        </button>
      </div>
      <p style={{ fontSize: 13, margin: '0.6rem 0 0.2rem' }} data-testid="ohm-readout">
        <strong>What to notice:</strong> current = V / R = {current.toFixed(2)} A, so doubling the voltage doubles the
        current and doubling the resistance halves it — the recorded points fall on a straight line through the origin
        whose slope is 1/R.
      </p>
      <p style={{ fontSize: 13, margin: '0 0 0.2rem', color: '#475569' }}>
        <strong>Try this:</strong> record readings at 2 V, 4 V and 6 V with R = 5 Ω, then set R = 10 Ω and record
        again — the second set of points lies on a shallower line. Model note: the resistor is treated as ohmic at every
        voltage; battery internal resistance, wire resistance and any heating of the resistor are not modelled.
      </p>
      <p style={{ fontSize: 12, margin: 0, color: '#64748b' }}>
        live values — V: <span data-testid="ohm-readout-v">{voltage.toFixed(1)}</span> V, R:{' '}
        <span data-testid="ohm-readout-r">{resistance.toFixed(1)}</span> Ω, I:{' '}
        <span data-testid="ohm-readout-i">{current.toFixed(3)}</span> A, P:{' '}
        <span data-testid="ohm-readout-p">{power.toFixed(2)}</span> W, readings:{' '}
        <span data-testid="ohm-readout-points">{readings.length}</span>
      </p>
    </figure>
  );
}
