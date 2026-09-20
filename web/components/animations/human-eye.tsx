'use client';

import { useEffect, useRef, useState } from 'react';

export type ConceptAnimationProps = { className?: string };

const W = 760;
const H = 470;

// --- the model's fixed parameters, all stated in the caption ---------------
const RETINA_M = 0.025; // lens to retina, metres
const PUPIL_MM = 4; // entrance pupil diameter
const ACCOMMODATION_D = 4; // how much extra power the eye can add
const READING_M = 0.25; // the conventional near point used to size spectacles

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

const clamp = (x: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, x));

export default function HumanEye({ className }: ConceptAnimationProps) {
  const [objectM, setObjectM] = useState(0.5);
  const [restPower, setRestPower] = useState(40);
  const [spectacles, setSpectacles] = useState(false);
  const [playing, setPlaying] = useState(true);

  const reduced = useReducedMotion();
  const animating = playing && !reduced;
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const tRef = useRef(0);
  const drawRef = useRef<() => void>(() => {});

  // --- thin-lens model, every number below is computed from the two sliders --
  const relaxedPower = restPower; // dioptres
  const staticPower = 1 / RETINA_M; // power needed to focus a far object (40 D)
  const isMyopic = relaxedPower > staticPower;
  const spectaclePower = isMyopic
    ? -(relaxedPower - staticPower) // concave lens: brings the far point to infinity
    : (1 / READING_M + staticPower) - (relaxedPower + ACCOMMODATION_D); // convex lens for reading
  const minPower = relaxedPower + (spectacles ? spectaclePower : 0);
  const maxPower = relaxedPower + ACCOMMODATION_D + (spectacles ? spectaclePower : 0);

  const requiredPower = 1 / objectM + staticPower;
  const eyePower = clamp(requiredPower, minPower, maxPower);
  const imageM = eyePower - 1 / objectM > 1e-9 ? 1 / (eyePower - 1 / objectM) : Infinity;
  const imageMm = imageM * 1000;
  const blurMm = Number.isFinite(imageM) ? (PUPIL_MM * Math.abs(imageM - RETINA_M)) / imageM : PUPIL_MM;
  const sharp = blurMm < 0.05;

  const farPointM = minPower - staticPower > 1e-9 ? 1 / (minPower - staticPower) : Infinity;
  const nearPointM = maxPower - staticPower > 1e-9 ? 1 / (maxPower - staticPower) : Infinity;
  const fmt = (m: number) => (!Number.isFinite(m) || m > 100 ? '∞' : `${m.toFixed(2)} m`);

  const draw = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const phase = (tRef.current * 0.3) % 1;

    ctx.fillStyle = '#0b1220';
    ctx.fillRect(0, 0, W, H);
    ctx.strokeStyle = '#1e293b';
    ctx.lineWidth = 1;
    ctx.strokeRect(0.5, 0.5, W - 1, H - 1);

    text(ctx, 'The eye as a lens: where the image actually lands', 24, 26, '#94a3b8', 14);
    text(
      ctx,
      `lens–retina ${(RETINA_M * 1000).toFixed(1)} mm · pupil ${PUPIL_MM} mm · accommodation ${ACCOMMODATION_D} D · object drawn schematically`,
      24,
      46,
      '#64748b',
      11,
    );

    const axisY = 252;
    const lensX = 400;
    const retinaX = 600;
    const pxPerMm = (retinaX - lensX) / (RETINA_M * 1000);

    // eyeball
    ctx.strokeStyle = '#334155';
    ctx.lineWidth = 2.2;
    ctx.beginPath();
    ctx.arc((lensX + retinaX) / 2, axisY, (retinaX - lensX) / 2, 0, Math.PI * 2);
    ctx.stroke();
    ctx.fillStyle = 'rgba(56,189,248,0.05)';
    ctx.fill();

    // retina
    line(ctx, retinaX, axisY - 74, retinaX, axisY + 74, '#f472b6', 3);
    text(ctx, 'retina', retinaX + 8, axisY - 82, '#f472b6', 12);
    text(ctx, `${(RETINA_M * 1000).toFixed(1)} mm`, retinaX + 8, axisY - 66, '#f472b6', 11);

    // lens, aperture = pupil
    const aperture = 26;
    ctx.strokeStyle = '#38bdf8';
    ctx.lineWidth = 2.4;
    ctx.beginPath();
    ctx.moveTo(lensX, axisY - aperture);
    ctx.quadraticCurveTo(lensX - 13, axisY, lensX, axisY + aperture);
    ctx.quadraticCurveTo(lensX + 13, axisY, lensX, axisY - aperture);
    ctx.stroke();
    text(ctx, `eye lens, power in use ${eyePower.toFixed(1)} D`, lensX - 8, axisY + 96, '#38bdf8', 12, 'right');

    // spectacle lens (drawn in front; treated as in contact with the eye lens)
    if (spectacles) {
      const sx = 366;
      ctx.strokeStyle = '#a78bfa';
      ctx.lineWidth = 2.4;
      ctx.beginPath();
      ctx.moveTo(sx, axisY - 44);
      ctx.quadraticCurveTo(sx - (spectaclePower < 0 ? 10 : -10), axisY, sx, axisY + 44);
      ctx.quadraticCurveTo(sx + (spectaclePower < 0 ? 10 : -10), axisY, sx, axisY - 44);
      ctx.stroke();
      text(ctx, `spectacles ${spectaclePower >= 0 ? '+' : ''}${spectaclePower.toFixed(2)} D`, sx - 4, axisY + 62, '#a78bfa', 12, 'right');
    }

    // object, drawn at a schematic distance (log-scaled) with its real distance labelled
    const frac = Math.log(objectM / 0.15) / Math.log(5 / 0.15);
    const objX = 330 - 280 * clamp(frac, 0, 1);
    const objH = 46;
    line(ctx, objX, axisY, objX, axisY - objH, '#fbbf24', 4);
    ctx.fillStyle = '#fbbf24';
    ctx.beginPath();
    ctx.moveTo(objX, axisY - objH - 10);
    ctx.lineTo(objX - 6, axisY - objH);
    ctx.lineTo(objX + 6, axisY - objH);
    ctx.closePath();
    ctx.fill();
    text(ctx, `object at ${objectM.toFixed(2)} m`, objX, axisY + 18, '#fbbf24', 12, 'center');
    text(ctx, '(distance not to scale)', objX, axisY + 34, '#64748b', 10, 'center');

    // image plane, mapped with the same mm scale as the retina
    const imgX = lensX + imageMm * pxPerMm;
    ctx.save();
    ctx.setLineDash([6, 6]);
    ctx.strokeStyle = sharp ? '#34d399' : '#f87171';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(imgX, axisY - 88);
    ctx.lineTo(imgX, axisY + 88);
    ctx.stroke();
    ctx.restore();
    text(
      ctx,
      `image at ${imageMm.toFixed(1)} mm`,
      imgX,
      axisY - 100,
      sharp ? '#34d399' : '#f87171',
      12,
      'center',
    );

    // rays: through the aperture edges and the centre, converging on the image plane
    const rays = [-aperture, -aperture / 2, 0, aperture / 2, aperture];
    rays.forEach((yl, k) => {
      const hitY = axisY + yl;
      const imgY = axisY; // an on-axis object point images on the axis
      const dx = imgX - lensX;
      const dy = imgY - hitY;
      const slope = dx === 0 ? 0 : dy / dx;
      const stopX = Math.max(imgX, retinaX);
      const stopY = hitY + slope * (stopX - lensX);
      ctx.strokeStyle = 'rgba(251,191,36,0.55)';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(objX, axisY - objH);
      ctx.lineTo(lensX, hitY);
      ctx.lineTo(stopX, stopY);
      ctx.stroke();
      if (k % 2 === 0) {
        for (let d = 0; d < 5; d += 1) {
          const p = (((phase + d / 5 + k * 0.11) % 1) + 1) % 1;
          const px = objX + (lensX - objX) * p;
          const py = axisY - objH + (hitY - (axisY - objH)) * p;
          ctx.fillStyle = '#fde68a';
          ctx.beginPath();
          ctx.arc(px, py, 2.6, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    });

    // the blur patch on the retina, drawn from the same blur number shown below
    const blurPx = (blurMm / 2) * pxPerMm;
    ctx.strokeStyle = sharp ? '#34d399' : '#f87171';
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.moveTo(retinaX, axisY - Math.max(blurPx, 1.5));
    ctx.lineTo(retinaX, axisY + Math.max(blurPx, 1.5));
    ctx.stroke();
    text(
      ctx,
      sharp ? 'sharp: image on the retina' : `blur spot ${blurMm.toFixed(2)} mm across`,
      retinaX - 6,
      axisY + 104,
      sharp ? '#34d399' : '#f87171',
      12,
      'right',
    );

    // ---- power range bar: is the required power inside what the eye can do? ----
    const bx0 = 40;
    const bx1 = 360;
    const by = 420;
    const pLo = 34;
    const pHi = 48;
    const px = (p: number) => bx0 + ((bx1 - bx0) * (p - pLo)) / (pHi - pLo);
    text(ctx, 'eye power available vs power needed (dioptres)', bx0, by - 26, '#94a3b8', 12);
    line(ctx, bx0, by, bx1, by, '#475569', 2);
    line(ctx, px(minPower), by - 9, px(minPower), by + 9, '#38bdf8', 2);
    line(ctx, px(maxPower), by - 9, px(maxPower), by + 9, '#38bdf8', 2);
    line(ctx, px(minPower), by, px(maxPower), by, '#38bdf8', 5);
    for (let p = pLo; p <= pHi; p += 2) {
      line(ctx, px(p), by, px(p), by + 5, '#475569', 1.2);
      text(ctx, String(p), px(p), by + 16, '#475569', 10, 'center');
    }
    const needX = clamp(px(requiredPower), bx0, bx1);
    line(ctx, needX, by - 20, needX, by + 9, '#fbbf24', 2.6);
    text(
      ctx,
      `needed ${requiredPower.toFixed(1)} D${requiredPower > maxPower ? ' — above the range' : requiredPower < minPower ? ' — below the range' : ' — inside the range'}`,
      needX,
      by - 30,
      '#fbbf24',
      11,
      'center',
    );
    text(ctx, `the eye supplies ${minPower.toFixed(1)}–${maxPower.toFixed(1)} D`, bx0, by + 34, '#38bdf8', 12);

    // ---- computed summary, drawn from the same values as the DOM readout ----
    text(ctx, `1/u + 1/d = 1/${objectM.toFixed(2)} + 1/${RETINA_M.toFixed(3)} = ${requiredPower.toFixed(2)} D needed`, 400, 396, '#e2e8f0', 12);
    text(ctx, `image distance ${imageMm.toFixed(2)} mm  vs  retina ${(RETINA_M * 1000).toFixed(2)} mm`, 400, 416, '#e2e8f0', 12);
    text(ctx, `blur spot = ${PUPIL_MM} mm × |${imageMm.toFixed(2)} − ${(RETINA_M * 1000).toFixed(2)}| / ${imageMm.toFixed(2)} = ${blurMm.toFixed(3)} mm`, 400, 436, '#e2e8f0', 12);
    text(ctx, `far point ${fmt(farPointM)}   near point ${fmt(nearPointM)}`, 400, 456, '#94a3b8', 12);
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
        data-testid="eye-canvas"
        role="img"
        aria-label="Ray diagram of the eye: object, lens, and the image plane compared with the retina"
        style={{ width: '100%', height: 'auto', display: 'block', borderRadius: 10 }}
      />
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem 1.5rem', marginTop: '0.75rem', alignItems: 'center' }}>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 13 }}>
          <span>
            object distance u: <strong data-testid="eye-u">{objectM.toFixed(2)} m</strong>
          </span>
          <input
            type="range"
            min={0.15}
            max={5}
            step={0.05}
            value={objectM}
            aria-label="Distance from the object to the eye, in metres"
            onChange={(e) => setObjectM(Number(e.target.value))}
            style={{ width: 200 }}
          />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 13 }}>
          <span>
            relaxed power of the eye lens: <strong data-testid="eye-rest">{restPower.toFixed(1)} D</strong>
          </span>
          <input
            type="range"
            min={36}
            max={44}
            step={0.5}
            value={restPower}
            aria-label="Relaxed power of the eye lens in dioptres"
            onChange={(e) => setRestPower(Number(e.target.value))}
            style={{ width: 200 }}
          />
        </label>
        <button type="button" onClick={() => setRestPower(40)} aria-label="Preset: a normal eye" style={{ padding: '5px 10px', cursor: 'pointer' }}>
          normal eye
        </button>
        <button type="button" onClick={() => setRestPower(42.5)} aria-label="Preset: a myopic eye" style={{ padding: '5px 10px', cursor: 'pointer' }}>
          myopic eye
        </button>
        <button
          type="button"
          onClick={() => setRestPower(37.5)}
          aria-label="Preset: a hypermetropic eye"
          style={{ padding: '5px 10px', cursor: 'pointer' }}
        >
          hypermetropic eye
        </button>
        <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 13 }}>
          <input
            type="checkbox"
            checked={spectacles}
            aria-label="Put correcting spectacles on the eye"
            onChange={(e) => setSpectacles(e.target.checked)}
          />
          wear spectacles
        </label>
        <button
          type="button"
          onClick={() => setPlaying((p) => !p)}
          disabled={reduced}
          aria-label={playing ? 'Pause the ray animation' : 'Play the ray animation'}
          style={{ padding: '5px 12px', cursor: reduced ? 'not-allowed' : 'pointer' }}
        >
          {playing ? 'Pause' : 'Play'}
        </button>
      </div>
      <p style={{ fontSize: 13, margin: '0.6rem 0 0.2rem' }} data-testid="eye-readout">
        <strong>What to notice:</strong> {spectacles ? 'with the spectacles on' : 'with no spectacles'}, an object at{' '}
        {objectM.toFixed(2)} m needs {requiredPower.toFixed(1)} D and the eye supplies {eyePower.toFixed(1)} D, so the
        image lands {imageMm.toFixed(1)} mm behind the lens — {sharp ? 'on' : imageMm < 25 ? 'in front of' : 'behind'} the{' '}
        25.0 mm retina, giving a {blurMm.toFixed(2)} mm blur spot.
      </p>
      <p style={{ fontSize: 13, margin: '0 0 0.2rem', color: '#475569' }}>
        <strong>Try this:</strong> press <em>myopic eye</em> and watch the image cross in front of the retina, then tick{' '}
        <em>wear spectacles</em> — the computed power is {spectaclePower >= 0 ? '+' : ''}
        {spectaclePower.toFixed(2)} D and the far point moves to {fmt(farPointM)}. Model note: a thin-lens model with
        the spectacle lens treated as in contact with the eye lens; lens thickness, aberrations and the eye&rsquo;s
        actual accommodation mechanism are not modelled, and the object is drawn at a schematic distance although every
        number is computed from the real distances.
      </p>
      <p style={{ fontSize: 12, margin: 0, color: '#64748b' }}>
        computed — needed: <span data-testid="eye-pneeded">{requiredPower.toFixed(2)}</span> D, used:{' '}
        <span data-testid="eye-pused">{eyePower.toFixed(2)}</span> D, image:{' '}
        <span data-testid="eye-v">{imageMm.toFixed(2)}</span> mm, retina:{' '}
        <span data-testid="eye-retina">{(RETINA_M * 1000).toFixed(2)}</span> mm, blur:{' '}
        <span data-testid="eye-blur">{blurMm.toFixed(3)}</span> mm, far point:{' '}
        <span data-testid="eye-far">{fmt(farPointM)}</span>, near point:{' '}
        <span data-testid="eye-near">{fmt(nearPointM)}</span>, spectacle power:{' '}
        <span data-testid="eye-spec">{spectaclePower.toFixed(2)}</span> D, verdict:{' '}
        <span data-testid="eye-verdict">{sharp ? 'sharp' : 'blurred'}</span>
      </p>
    </figure>
  );
}
