'use client';

import { useEffect, useMemo, useRef, useState } from 'react';

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

function text(ctx: Ctx, s: string, x: number, y: number, color: string, size = 13, align: CanvasTextAlign = 'left') {
  ctx.fillStyle = color;
  ctx.font = `${size}px ui-sans-serif, system-ui, sans-serif`;
  ctx.textAlign = align;
  ctx.textBaseline = 'middle';
  ctx.fillText(s, x, y);
}

// ---------------------------------------------------------------------------
// small vector toolkit — the molecular geometry is built from bond lengths and
// bond angles here, not typed in as finished coordinates
// ---------------------------------------------------------------------------
type V3 = [number, number, number];
const v3 = (x: number, y: number, z: number): V3 => [x, y, z];
const add = (a: V3, b: V3): V3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const mul = (a: V3, s: number): V3 => [a[0] * s, a[1] * s, a[2] * s];
const sub = (a: V3, b: V3): V3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const dot = (a: V3, b: V3): number => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cross = (a: V3, b: V3): V3 => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const len = (a: V3): number => Math.sqrt(dot(a, a));
const unit = (a: V3): V3 => {
  const l = len(a) || 1;
  return mul(a, 1 / l);
};

/** Standard geometry used throughout, in ångström and degrees. */
const GEO = {
  ccSingle: 1.54,
  ccDouble: 1.34,
  ccTriple: 1.2,
  ch: 1.09,
  co: 1.23,
  coSingle: 1.43,
  oh: 0.96,
  tetra: 109.47,
  trigonal: 120,
  bent: 104.5,
  carboxylBend: 108,
};

function rotate(v: V3, axis: V3, deg: number): V3 {
  const k = unit(axis);
  const t = (deg * Math.PI) / 180;
  const c = Math.cos(t);
  const s = Math.sin(t);
  return add(add(mul(v, c), mul(cross(k, v), s)), mul(k, dot(k, v) * (1 - c)));
}

/** Three directions at the tetrahedral angle to `axis`, 120° apart about it. */
function threeAround(axis: V3, bond: number, phaseDeg: number): V3[] {
  const a = unit(axis);
  const u = unit(Math.abs(a[0]) < 0.9 ? cross(a, v3(1, 0, 0)) : cross(a, v3(0, 1, 0)));
  const w = cross(a, u);
  const ca = Math.cos((GEO.tetra * Math.PI) / 180);
  const sa = Math.sin((GEO.tetra * Math.PI) / 180);
  return [0, 1, 2].map((k) => {
    const t = ((phaseDeg + k * 120) * Math.PI) / 180;
    return mul(add(mul(a, ca), add(mul(u, sa * Math.cos(t)), mul(w, sa * Math.sin(t)))), bond);
  });
}

/** The other two tetrahedral directions when two are already taken. */
function twoRemaining(d1: V3, d2: V3, bond: number): V3[] {
  const m = unit(mul(add(unit(d1), unit(d2)), -1));
  const p = unit(cross(d1, d2));
  const half = ((GEO.tetra / 2) * Math.PI) / 180;
  return [
    mul(add(mul(m, Math.cos(half)), mul(p, Math.sin(half))), bond),
    mul(add(mul(m, Math.cos(half)), mul(p, -Math.sin(half))), bond),
  ];
}

type El = 'C' | 'H' | 'O';
type Atom = { el: El; p: V3 };
type Bond = { a: number; b: number; order: 1 | 2 | 3 };
type Molecule = { id: string; label: string; note: string; atoms: Atom[]; bonds: Bond[] };

function build(): Molecule[] {
  const out: Molecule[] = [];

  // --- methane: one carbon, four hydrogens on a tetrahedron ---------------
  {
    const atoms: Atom[] = [{ el: 'C', p: v3(0, 0, 0) }];
    const bonds: Bond[] = [];
    [
      v3(1, 1, 1),
      v3(1, -1, -1),
      v3(-1, 1, -1),
      v3(-1, -1, 1),
    ].forEach((d) => {
      atoms.push({ el: 'H', p: mul(unit(d), GEO.ch) });
      bonds.push({ a: 0, b: atoms.length - 1, order: 1 });
    });
    out.push({ id: 'methane', label: 'Methane CH₄', note: 'tetrahedral — four bonds 109.5° apart', atoms, bonds });
  }

  // --- ethane: two carbons, staggered hydrogens --------------------------
  {
    const atoms: Atom[] = [
      { el: 'C', p: v3(-GEO.ccSingle / 2, 0, 0) },
      { el: 'C', p: v3(GEO.ccSingle / 2, 0, 0) },
    ];
    const bonds: Bond[] = [{ a: 0, b: 1, order: 1 }];
    threeAround(v3(-1, 0, 0), GEO.ch, 0).forEach((h) => {
      atoms.push({ el: 'H', p: add(atoms[0]!.p, h) });
      bonds.push({ a: 0, b: atoms.length - 1, order: 1 });
    });
    threeAround(v3(1, 0, 0), GEO.ch, 60).forEach((h) => {
      atoms.push({ el: 'H', p: add(atoms[1]!.p, h) });
      bonds.push({ a: 1, b: atoms.length - 1, order: 1 });
    });
    out.push({ id: 'ethane', label: 'Ethane C₂H₆', note: 'two tetrahedral carbons joined by a single C–C bond', atoms, bonds });
  }

  // --- propane / butane: a zig-zag chain with tetrahedral angles ----------
  const chain = (n: number) => {
    const half = ((180 - 112) / 2) * (Math.PI / 180); // 112° at each carbon
    const dx = GEO.ccSingle * Math.cos(half);
    const dy = GEO.ccSingle * Math.sin(half);
    const pts: V3[] = [];
    for (let k = 0; k < n; k += 1) {
      const side = k % 2 === 0 ? 1 : -1;
      pts.push(v3((k - (n - 1) / 2) * dx, side * (dy / 2), 0));
    }
    return pts;
  };
  ([
    { n: 3, id: 'propane', label: 'Propane C₃H₈' },
    { n: 4, id: 'butane', label: 'Butane C₄H₁₀' },
  ] as const).forEach(({ n, id, label }) => {
    const pts = chain(n);
    const atoms: Atom[] = pts.map((p) => ({ el: 'C' as El, p }));
    const bonds: Bond[] = [];
    for (let k = 0; k + 1 < n; k += 1) bonds.push({ a: k, b: k + 1, order: 1 });
    for (let k = 0; k < n; k += 1) {
      const neigh = [] as V3[];
      if (k > 0) neigh.push(sub(pts[k - 1]!, pts[k]!));
      if (k + 1 < n) neigh.push(sub(pts[k + 1]!, pts[k]!));
      const dirs =
        neigh.length === 1
          ? threeAround(neigh[0]!, GEO.ch, k === 0 ? 0 : 60)
          : twoRemaining(neigh[0]!, neigh[1]!, GEO.ch);
      dirs.forEach((d) => {
        atoms.push({ el: 'H', p: add(pts[k]!, d) });
        bonds.push({ a: k, b: atoms.length - 1, order: 1 });
      });
    }
    out.push({
      id,
      label,
      note: 'zig-zag chain, 109.5° at each carbon',
      atoms,
      bonds,
    });
  });

  // --- ethene: planar, 120° ----------------------------------------------
  {
    const atoms: Atom[] = [
      { el: 'C', p: v3(-GEO.ccDouble / 2, 0, 0) },
      { el: 'C', p: v3(GEO.ccDouble / 2, 0, 0) },
    ];
    const bonds: Bond[] = [{ a: 0, b: 1, order: 2 }];
    ([[-0.5, 0.866], [-0.5, -0.866]] as [number, number][]).forEach(([x, y]) => {
      atoms.push({ el: 'H', p: add(atoms[0]!.p, mul(v3(x, y, 0), GEO.ch)) });
      bonds.push({ a: 0, b: atoms.length - 1, order: 1 });
    });
    ([[0.5, 0.866], [0.5, -0.866]] as [number, number][]).forEach(([x, y]) => {
      atoms.push({ el: 'H', p: add(atoms[1]!.p, mul(v3(x, y, 0), GEO.ch)) });
      bonds.push({ a: 1, b: atoms.length - 1, order: 1 });
    });
    out.push({ id: 'ethene', label: 'Ethene C₂H₄', note: 'planar, 120° apart — the C=C double bond', atoms, bonds });
  }

  // --- ethyne: linear -----------------------------------------------------
  {
    const c1 = v3(-GEO.ccTriple / 2, 0, 0);
    const c2 = v3(GEO.ccTriple / 2, 0, 0);
    out.push({
      id: 'ethyne',
      label: 'Ethyne C₂H₂',
      note: 'linear, 180° — the C≡C triple bond',
      atoms: [
        { el: 'C', p: c1 },
        { el: 'C', p: c2 },
        { el: 'H', p: add(c1, v3(-GEO.ch, 0, 0)) },
        { el: 'H', p: add(c2, v3(GEO.ch, 0, 0)) },
      ],
      bonds: [
        { a: 0, b: 1, order: 3 },
        { a: 0, b: 2, order: 1 },
        { a: 1, b: 3, order: 1 },
      ],
    });
  }

  // --- ethanol: the –OH functional group ---------------------------------
  {
    const c2 = v3(0, 0, 0);
    const c1 = add(c2, v3(-GEO.ccSingle, 0, 0));
    const dirCO = add(mul(v3(-1, 0, 0), Math.cos((GEO.tetra * Math.PI) / 180)), mul(v3(0, 1, 0), Math.sin((GEO.tetra * Math.PI) / 180)));
    const o = add(c2, mul(unit(dirCO), GEO.coSingle));
    const atoms: Atom[] = [
      { el: 'C', p: c1 },
      { el: 'C', p: c2 },
      { el: 'O', p: o },
    ];
    const bonds: Bond[] = [
      { a: 0, b: 1, order: 1 },
      { a: 1, b: 2, order: 1 },
    ];
    threeAround(v3(1, 0, 0), GEO.ch, 0).forEach((h) => {
      atoms.push({ el: 'H', p: add(c1, h) });
      bonds.push({ a: 0, b: atoms.length - 1, order: 1 });
    });
    twoRemaining(sub(c1, c2), sub(o, c2), GEO.ch).forEach((h) => {
      atoms.push({ el: 'H', p: add(c2, h) });
      bonds.push({ a: 1, b: atoms.length - 1, order: 1 });
    });
    const back = unit(sub(c2, o));
    const perp = unit(cross(back, v3(0, 0, 1)));
    const hDir = add(mul(back, Math.cos((GEO.bent * Math.PI) / 180)), mul(perp, Math.sin((GEO.bent * Math.PI) / 180)));
    atoms.push({ el: 'H', p: add(o, mul(unit(hDir), GEO.oh)) });
    bonds.push({ a: 2, b: atoms.length - 1, order: 1 });
    out.push({
      id: 'ethanol',
      label: 'Ethanol C₂H₅OH',
      note: 'the –OH group is what makes it an alcohol',
      atoms,
      bonds,
    });
  }

  // --- ethanoic acid: –COOH ----------------------------------------------
  {
    const c2 = v3(0, 0, 0);
    const c1 = add(c2, v3(-1.52, 0, 0));
    const dirA = add(mul(v3(-1, 0, 0), Math.cos((GEO.trigonal * Math.PI) / 180)), mul(v3(0, 1, 0), Math.sin((GEO.trigonal * Math.PI) / 180)));
    const dirB = add(mul(v3(-1, 0, 0), Math.cos((GEO.trigonal * Math.PI) / 180)), mul(v3(0, -1, 0), Math.sin((GEO.trigonal * Math.PI) / 180)));
    const oDouble = add(c2, mul(unit(dirA), GEO.co));
    const oSingle = add(c2, mul(unit(dirB), GEO.coSingle));
    const atoms: Atom[] = [
      { el: 'C', p: c1 },
      { el: 'C', p: c2 },
      { el: 'O', p: oDouble },
      { el: 'O', p: oSingle },
    ];
    const bonds: Bond[] = [
      { a: 0, b: 1, order: 1 },
      { a: 1, b: 2, order: 2 },
      { a: 1, b: 3, order: 1 },
    ];
    threeAround(v3(1, 0, 0), GEO.ch, 0).forEach((h) => {
      atoms.push({ el: 'H', p: add(c1, h) });
      bonds.push({ a: 0, b: atoms.length - 1, order: 1 });
    });
    const back = unit(sub(c2, oSingle));
    const hDir = add(mul(back, Math.cos((GEO.carboxylBend * Math.PI) / 180)), mul(v3(0, 0, 1), Math.sin((GEO.carboxylBend * Math.PI) / 180)));
    atoms.push({ el: 'H', p: add(oSingle, mul(unit(hDir), GEO.oh)) });
    bonds.push({ a: 3, b: atoms.length - 1, order: 1 });
    out.push({
      id: 'ethanoic-acid',
      label: 'Ethanoic acid CH₃COOH',
      note: 'the –COOH group: one C=O and one O–H on the same carbon',
      atoms,
      bonds,
    });
  }

  // --- benzene: a planar ring --------------------------------------------
  {
    const atoms: Atom[] = [];
    const bonds: Bond[] = [];
    const ringR = 1.4;
    for (let k = 0; k < 6; k += 1) {
      const a = (k * 60 * Math.PI) / 180;
      atoms.push({ el: 'C', p: v3(ringR * Math.cos(a), ringR * Math.sin(a), 0) });
    }
    for (let k = 0; k < 6; k += 1) bonds.push({ a: k, b: (k + 1) % 6, order: k % 2 === 0 ? 2 : 1 });
    for (let k = 0; k < 6; k += 1) {
      const a = (k * 60 * Math.PI) / 180;
      atoms.push({ el: 'H', p: v3((ringR + GEO.ch) * Math.cos(a), (ringR + GEO.ch) * Math.sin(a), 0) });
      bonds.push({ a: k, b: atoms.length - 1, order: 1 });
    }
    out.push({
      id: 'benzene',
      label: 'Benzene C₆H₆',
      note: 'a flat ring; the double bonds drawn stand in for electrons shared round the ring',
      atoms,
      bonds,
    });
  }

  return out;
}

const MOLECULES = build();

function elementCounts(m: Molecule) {
  const c: Record<string, number> = {};
  m.atoms.forEach((a) => {
    c[a.el] = (c[a.el] ?? 0) + 1;
  });
  return c;
}

/** Molecular formula in Hill order, counted from the atoms — not typed in. */
function formulaOf(m: Molecule) {
  const c = elementCounts(m);
  return ['C', 'H', 'O']
    .filter((el) => (c[el] ?? 0) > 0)
    .map((el) => {
      const n = c[el] ?? 0;
      return `${el}${n > 1 ? n : ''}`;
    })
    .join('');
}

function bondTally(m: Molecule) {
  const t = { single: 0, double: 0, triple: 0 };
  m.bonds.forEach((b) => {
    if (b.order === 1) t.single += 1;
    else if (b.order === 2) t.double += 1;
    else t.triple += 1;
  });
  return t;
}

const EL_STYLE: Record<El, { fill: string; stroke: string; r: number; text: string }> = {
  C: { fill: '#334155', stroke: '#94a3b8', r: 13, text: '#e2e8f0' },
  O: { fill: '#b91c1c', stroke: '#fca5a5', r: 12, text: '#fee2e2' },
  H: { fill: '#e2e8f0', stroke: '#94a3b8', r: 8, text: '#0b1220' },
};

function project(p: V3, yawDeg: number, pitchDeg: number, scale: number, cx: number, cy: number) {
  const yaw = (yawDeg * Math.PI) / 180;
  const pitch = (pitchDeg * Math.PI) / 180;
  const x1 = p[0] * Math.cos(yaw) + p[2] * Math.sin(yaw);
  const z1 = -p[0] * Math.sin(yaw) + p[2] * Math.cos(yaw);
  const y2 = p[1] * Math.cos(pitch) - z1 * Math.sin(pitch);
  const z2 = p[1] * Math.sin(pitch) + z1 * Math.cos(pitch);
  const s = 1 / (1 + z2 * 0.1); // mild perspective, so the near side looks nearer
  return { x: cx + x1 * scale * s, y: cy - y2 * scale * s, z: z2, s };
}

export default function CarbonCompounds({ className }: ConceptAnimationProps) {
  const [id, setId] = useState(MOLECULES[0]!.id);
  const [yaw, setYaw] = useState(20);
  const [pitch, setPitch] = useState(18);
  const [showH, setShowH] = useState(true);
  const [playing, setPlaying] = useState(true);

  const reduced = useReducedMotion();
  const animating = playing && !reduced;
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const tRef = useRef(0);
  const drawRef = useRef<() => void>(() => {});

  const molecule = useMemo(() => MOLECULES.find((m) => m.id === id) ?? MOLECULES[0]!, [id]);
  const counts = useMemo(() => elementCounts(molecule), [molecule]);
  const formula = useMemo(() => formulaOf(molecule), [molecule]);
  const tally = useMemo(() => bondTally(molecule), [molecule]);

  // the alkane prediction CnH2n+2 is checked against the counted hydrogens
  const isAlkane = useMemo(
    () => molecule.bonds.every((b) => b.order === 1) && Object.keys(counts).every((el) => el === 'C' || el === 'H'),
    [molecule, counts],
  );
  const nCarbon = counts.C ?? 0;
  const predictedH = 2 * nCarbon + 2;
  const actualH = counts.H ?? 0;

  const draw = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // read the animation clock inside the draw call: a value captured during render would be stale
    const yawShown = (yaw + (animating ? tRef.current * 26 : 0)) % 360;

    ctx.fillStyle = '#0b1220';
    ctx.fillRect(0, 0, W, H);
    ctx.strokeStyle = '#1e293b';
    ctx.lineWidth = 1;
    ctx.strokeRect(0.5, 0.5, W - 1, H - 1);

    text(ctx, 'Ball-and-stick model — 3D coordinates projected to the screen', 24, 26, '#94a3b8', 14);
    text(ctx, `${molecule.label}   ·   ${formula}   ·   yaw ${yawShown.toFixed(0)}°, pitch ${pitch.toFixed(0)}°`, 24, 46, '#64748b', 12);

    const cx = 300;
    const cy = 250;
    const scale = 46;

    const pts = molecule.atoms.map((a) => project(a.p, yawShown, pitch, scale, cx, cy));

    // bonds first, far ones before near ones
    const bondOrder = molecule.bonds
      .map((b, i) => ({ b, i, z: (pts[b.a]!.z + pts[b.b]!.z) / 2 }))
      .sort((p, q) => p.z - q.z);
    bondOrder.forEach(({ b }) => {
      const A = molecule.atoms[b.a]!;
      const B = molecule.atoms[b.b]!;
      if (!showH && (A.el === 'H' || B.el === 'H')) return;
      const p1 = pts[b.a]!;
      const p2 = pts[b.b]!;
      const dx = p2.x - p1.x;
      const dy = p2.y - p1.y;
      const l = Math.hypot(dx, dy) || 1;
      const nx = -dy / l;
      const ny = dx / l;
      const offsets = b.order === 1 ? [0] : b.order === 2 ? [-2.4, 2.4] : [-3.6, 0, 3.6];
      const color =
        (A.el === 'O' || B.el === 'O') && b.order === 2 ? '#f97316' : A.el === 'O' || B.el === 'O' ? '#38bdf8' : '#94a3b8';
      offsets.forEach((o) => {
        ctx.strokeStyle = color;
        ctx.lineWidth = b.order === 1 ? 5 : 3.2;
        ctx.beginPath();
        ctx.moveTo(p1.x + nx * o, p1.y + ny * o);
        ctx.lineTo(p2.x + nx * o, p2.y + ny * o);
        ctx.stroke();
      });
    });

    // atoms, far ones first
    molecule.atoms
      .map((a, i) => ({ a, i, z: pts[i]!.z }))
      .sort((p, q) => p.z - q.z)
      .forEach(({ a, i }) => {
        if (!showH && a.el === 'H') return;
        const style = EL_STYLE[a.el];
        const p = pts[i]!;
        const r = style.r * (0.75 + 0.25 * p.s);
        ctx.fillStyle = style.fill;
        ctx.strokeStyle = style.stroke;
        ctx.lineWidth = 1.6;
        ctx.beginPath();
        ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
        text(ctx, a.el, p.x, p.y + 0.5, style.text, a.el === 'H' ? 9 : 11, 'center');
      });

    // legend and the geometry actually used, read from the same GEO table
    text(ctx, 'legend', 560, 96, '#94a3b8', 12);
    (['C', 'H', 'O'] as El[]).forEach((el, k) => {
      const y = 118 + k * 24;
      ctx.fillStyle = EL_STYLE[el].fill;
      ctx.strokeStyle = EL_STYLE[el].stroke;
      ctx.beginPath();
      ctx.arc(568, y, 8, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
      text(ctx, el === 'C' ? 'carbon' : el === 'O' ? 'oxygen' : 'hydrogen', 584, y, '#94a3b8', 12);
    });
    text(ctx, 'geometry used (Å, degrees):', 560, 202, '#94a3b8', 12);
    text(ctx, `C–C ${GEO.ccSingle.toFixed(2)}  C=C ${GEO.ccDouble.toFixed(2)}  C≡C ${GEO.ccTriple.toFixed(2)}`, 560, 222, '#64748b', 11);
    text(ctx, `C–H ${GEO.ch.toFixed(2)}  C–O ${GEO.coSingle.toFixed(2)}  C=O ${GEO.co.toFixed(2)}`, 560, 240, '#64748b', 11);
    text(ctx, `tetrahedral ${GEO.tetra.toFixed(2)}°  trigonal ${GEO.trigonal}°`, 560, 258, '#64748b', 11);
    text(ctx, `counted: C ${nCarbon}  H ${actualH}  O ${counts.O ?? 0}`, 560, 288, '#e2e8f0', 12);
    text(ctx, `bonds: ${tally.single} single, ${tally.double} double, ${tally.triple} triple`, 560, 306, '#e2e8f0', 12);
    text(
      ctx,
      isAlkane ? `alkane check CₙH₂ₙ₊₂: n=${nCarbon} → ${predictedH} H, model has ${actualH} H` : 'not a plain alkane',
      560,
      330,
      isAlkane && predictedH === actualH ? '#34d399' : '#fbbf24',
      11,
    );
    text(ctx, molecule.note, 24, 434, '#64748b', 12);
    text(
      ctx,
      showH ? 'hydrogens shown' : 'hydrogens hidden (carbon skeleton only)',
      24,
      452,
      '#64748b',
      12,
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
        data-testid="carbon-canvas"
        role="img"
        aria-label={`Ball-and-stick model of ${molecule.label}, a projection of a three-dimensional structure`}
        style={{ width: '100%', height: 'auto', display: 'block', borderRadius: 10 }}
      />
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem 1.5rem', marginTop: '0.75rem', alignItems: 'center' }}>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 13 }}>
          <span>compound</span>
          <select
            value={id}
            aria-label="Choose a carbon compound"
            onChange={(e) => setId(e.target.value)}
            style={{ padding: '3px 6px' }}
          >
            {MOLECULES.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 13 }}>
          <span>
            rotate: <strong data-testid="carbon-yaw">{yaw.toFixed(0)}°</strong>
          </span>
          <input
            type="range"
            min={0}
            max={360}
            step={1}
            value={yaw}
            aria-label="Rotation about the vertical axis, in degrees"
            onChange={(e) => setYaw(Number(e.target.value))}
            style={{ width: 190 }}
          />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 13 }}>
          <span>
            tilt: <strong data-testid="carbon-pitch">{pitch.toFixed(0)}°</strong>
          </span>
          <input
            type="range"
            min={-60}
            max={60}
            step={1}
            value={pitch}
            aria-label="Tilt about the horizontal axis, in degrees"
            onChange={(e) => setPitch(Number(e.target.value))}
            style={{ width: 160 }}
          />
        </label>
        <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 13 }}>
          <input
            type="checkbox"
            checked={showH}
            aria-label="Show or hide the hydrogen atoms"
            onChange={(e) => setShowH(e.target.checked)}
          />
          show hydrogens
        </label>
        <button
          type="button"
          onClick={() => setPlaying((p) => !p)}
          disabled={reduced}
          aria-label={playing ? 'Pause the rotation' : 'Play the rotation'}
          style={{ padding: '5px 12px', cursor: reduced ? 'not-allowed' : 'pointer' }}
        >
          {playing ? 'Pause' : 'Play'}
        </button>
      </div>
      <p style={{ fontSize: 13, margin: '0.6rem 0 0.2rem' }} data-testid="carbon-readout">
        <strong>What to notice:</strong> {molecule.label} has {nCarbon} carbon
        {nCarbon === 1 ? '' : 's'}, {actualH} hydrogen{actualH === 1 ? '' : 's'}
        {counts.O ? ` and ${counts.O} oxygen` : ''} — {molecule.note}.
      </p>
      <p style={{ fontSize: 13, margin: '0 0 0.2rem', color: '#475569' }}>
        <strong>Try this:</strong> rotate methane and count the four bonds spreading out of the carbon (109.5° apart),
        then switch to ethene and see them flatten to 120°. Model note: this is a stick model built from standard bond
        lengths and angles — electron density, bond energies and any bending or stretching of the bonds are not
        modelled, and the benzene ring is drawn with alternating double bonds although its electrons are in fact
        delocalised.
      </p>
      <p style={{ fontSize: 12, margin: 0, color: '#64748b' }}>
        counted from the model — formula: <span data-testid="carbon-formula">{formula}</span>, atoms:{' '}
        <span data-testid="carbon-counts">
          C{nCarbon}H{actualH}
          {counts.O ? `O${counts.O}` : ''}
        </span>
        , bonds: <span data-testid="carbon-bonds">{tally.single + tally.double + tally.triple}</span> (
        <span data-testid="carbon-bond-tally">
          {tally.single}/{tally.double}/{tally.triple}
        </span>{' '}
        single/double/triple)
      </p>
    </figure>
  );
}
