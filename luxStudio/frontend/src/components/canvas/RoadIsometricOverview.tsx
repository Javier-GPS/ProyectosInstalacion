import React, { useMemo } from 'react';
import { Cuboid } from 'lucide-react';
import { useShallow } from 'zustand/react/shallow';
import { useConfigStore, type ConfigState } from '../../store/useConfigStore';
import { useI18n } from '../../i18n';
import type { RoadElement } from '../../types';

type IsoCfg = Pick<
  ConfigState,
  'arm_length' | 'arrangement' | 'height' |
  'pole_offset' | 'pole_side' | 'road_width' | 'spacing' | 'tilt'
> & { roadElements: RoadElement[] };

type Point3 = { x: number; y: number; z: number };
type Point2 = { x: number; y: number };
type Rect = { x: number; y: number; w: number; h: number };
type Side = 'left' | 'right' | 'center';
type IsoScene = {
  armProjection: number;
  meterScale: number;
  project: (p: Point3) => Point2;
};

const SVG_W = 900;
const SVG_H = 500;
const ROAD_DEPTH = 0.38;
const DEG = Math.PI / 180;
const ELEVATION = 35 * DEG;
const ROTATION = 45 * DEG;
const HEAD_TILT_VISUAL_GAIN = 1.8;

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function rawProject(p: Point3): Point2 {
  const xr = p.x * Math.cos(ROTATION) - p.z * Math.sin(ROTATION);
  const zr = p.x * Math.sin(ROTATION) + p.z * Math.cos(ROTATION);
  return {
    x: xr,
    y: zr * Math.sin(ELEVATION) - p.y * Math.cos(ELEVATION),
  };
}

function makeProjector(points: Point3[]) {
  const projected = points.map(rawProject);
  const minX = Math.min(...projected.map((p) => p.x));
  const maxX = Math.max(...projected.map((p) => p.x));
  const minY = Math.min(...projected.map((p) => p.y));
  const maxY = Math.max(...projected.map((p) => p.y));
  const padX = 70;
  const padY = 42;
  const scale = Math.min((SVG_W - padX * 2) / Math.max(1, maxX - minX), (SVG_H - padY * 2) / Math.max(1, maxY - minY));

  const project = (p: Point3): Point2 => {
    const raw = rawProject(p);
    return {
      x: padX + (raw.x - minX) * scale,
      y: padY + (raw.y - minY) * scale,
    };
  };

  const meterA = project({ x: 0, y: 0, z: 0 });
  const meterB = project({ x: 0, y: 0, z: 1 });
  const roadMeterScale = Math.hypot(meterB.x - meterA.x, meterB.y - meterA.y);

  return { project, scale: roadMeterScale };
}

function path(points: Point2[]): string {
  return points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
}

function mid(a: Point2, b: Point2): Point2 {
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
}

function unitNormal(a: Point2, b: Point2, distance: number): Point2 {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len = Math.hypot(dx, dy) || 1;
  return { x: (-dy / len) * distance, y: (dx / len) * distance };
}

function rectFromPoints(points: Point2[], padding = 0): Rect {
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const x = Math.min(...xs) - padding;
  const y = Math.min(...ys) - padding;
  const maxX = Math.max(...xs) + padding;
  const maxY = Math.max(...ys) + padding;
  return { x, y, w: maxX - x, h: maxY - y };
}

function intersects(a: Rect, b: Rect): boolean {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}

function spacingLayout(a: Point2, b: Point2, label: string, obstacles: Rect[], preferredLifts: number[]) {
  for (const lift of preferredLifts) {
    const n = unitNormal(a, b, lift);
    const p1 = { x: a.x + n.x, y: a.y + n.y };
    const p2 = { x: b.x + n.x, y: b.y + n.y };
    const m = mid(p1, p2);
    const labelBox = { x: m.x - Math.max(42, label.length * 3.8), y: m.y - 28, w: Math.max(84, label.length * 7.6), h: 22 };
    const lineBox = rectFromPoints([p1, p2], 30);
    if (!obstacles.some((box) => intersects(labelBox, box) || intersects(lineBox, box))) {
      return { p1, p2, m, labelBox };
    }
  }
  const lift = preferredLifts[preferredLifts.length - 1];
  const n = unitNormal(a, b, lift);
  const p1 = { x: a.x + n.x, y: a.y + n.y };
  const p2 = { x: b.x + n.x, y: b.y + n.y };
  return { p1, p2, m: mid(p1, p2), labelBox: rectFromPoints([p1, p2], 0) };
}

function offsetPoint(a: Point2, b: Point2, distance: number): Point2 {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len = Math.hypot(dx, dy) || 1;
  return { x: a.x + (dx / len) * distance, y: a.y + (dy / len) * distance };
}

function beamFootprint(
  scene: IsoScene,
  pole: { x: number; z: number; side: Side },
  rowSideSign: number,
  cfg: IsoCfg,
) {
  const headZ = pole.side === 'center' ? pole.z : pole.z + rowSideSign * scene.armProjection;
  const top = scene.project({ x: pole.x, y: cfg.height, z: pole.z });
  const head = scene.project({ x: pole.x, y: cfg.height, z: headZ });
  const dx = head.x - top.x;
  const dy = head.y - top.y;
  const len = Math.hypot(dx, dy) || 1;
  const headForward = clamp(scene.meterScale * 0.22, 3, 8);
  const headHalfWidth = clamp(scene.meterScale * 0.07, 1.2, 3);
  const frontLower = {
    x: head.x + (dx / len) * headForward + (-dy / len) * headHalfWidth,
    y: head.y + (dy / len) * headForward + (dx / len) * headHalfWidth,
  };
  const targetZ = Math.max(0.2, Math.min(cfg.road_width - 0.2, headZ + rowSideSign * Math.max(cfg.road_width * 0.42, 2.8)));
  const spreadZ = Math.max(1.1, cfg.road_width * 0.18);
  const spreadX = Math.max(2.6, cfg.spacing * 0.08);

  return [
    frontLower,
    scene.project({ x: pole.x - spreadX, y: 0.04, z: Math.max(0.2, targetZ - spreadZ) }),
    scene.project({ x: pole.x, y: 0.04, z: targetZ }),
    scene.project({ x: pole.x + spreadX, y: 0.04, z: Math.min(cfg.road_width - 0.2, targetZ + spreadZ) }),
  ];
}

function getCarriagewayEdge(elements: RoadElement[], side: 'left' | 'right'): number {
  if (side === 'left') {
    let z = 0;
    for (const el of elements) {
      if (el.type === 'carriageway') return z;
      z += el.width;
    }
    return 0;
  }
  let z = elements.reduce((s, e) => s + e.width, 0);
  for (let i = elements.length - 1; i >= 0; i--) {
    if (elements[i].type === 'carriageway') return z;
    z -= elements[i].width;
  }
  return z;
}

function buildPoleRows(cfg: IsoCfg): Array<{ x: number; z: number; side: Side; phase?: number }> {
  const W = cfg.road_width;
  const spacing = cfg.spacing;
  const sideZ = (side: 'left' | 'right') => {
    const edge = getCarriagewayEdge(cfg.roadElements, side);
    return side === 'left' ? edge - cfg.pole_offset : edge + cfg.pole_offset;
  };
  const rows: Array<{ x: number; z: number; side: Side; phase?: number }> = [];
  const xs = [-spacing, 0, spacing];

  if (cfg.arrangement === 'Lineal') {
    rows.push(...xs.map((x) => ({ x, z: sideZ(cfg.pole_side), side: cfg.pole_side })));
  } else if (cfg.arrangement === 'Bilateral') {
    xs.forEach((x) => {
      rows.push({ x, z: sideZ('left'), side: 'left' });
      rows.push({ x, z: sideZ('right'), side: 'right' });
    });
  } else if (cfg.arrangement === 'Bilateral Alternada') {
    const firstSide = cfg.pole_side;
    const secondSide = firstSide === 'left' ? 'right' : 'left';
    rows.push({ x: -spacing, z: sideZ(firstSide), side: firstSide });
    rows.push({ x: 0, z: sideZ(secondSide), side: secondSide });
    rows.push({ x: spacing, z: sideZ(firstSide), side: firstSide });
  } else if (cfg.arrangement === 'Central Doble') {
    xs.forEach((x) => {
      rows.push({ x, z: W / 2, side: 'left' });
      rows.push({ x, z: W / 2, side: 'right' });
    });
  } else {
    rows.push(...xs.map((x) => ({ x, z: W / 2, side: 'center' as const })));
  }

  return rows;
}

const Label = ({
  x,
  y,
  children,
  anchor = 'middle',
  muted = false,
}: {
  x: number;
  y: number;
  children: React.ReactNode;
  anchor?: 'start' | 'middle' | 'end';
  muted?: boolean;
}) => (
  <text
    x={x}
    y={y}
    textAnchor={anchor}
    fontSize="13"
    fontWeight="800"
    fill={muted ? '#475569' : '#0f172a'}
    paintOrder="stroke"
    stroke="#f8fafc"
    strokeWidth="4"
    strokeLinejoin="round"
  >
    {children}
  </text>
);

const Dimension = ({
  a,
  b,
  label,
  lift = 0,
  labelLift = -8,
  labelDx = 0,
  labelDy = 0,
  anchor = 'middle',
  noExtensions = false,
}: {
  a: Point2;
  b: Point2;
  label: string;
  lift?: number;
  labelLift?: number;
  labelDx?: number;
  labelDy?: number;
  anchor?: 'start' | 'middle' | 'end';
  noExtensions?: boolean;
}) => {
  const n = unitNormal(a, b, lift);
  const p1 = { x: a.x + n.x, y: a.y + n.y };
  const p2 = { x: b.x + n.x, y: b.y + n.y };
  const m = mid(p1, p2);
  const lx = m.x + labelDx;
  const ly = m.y + labelLift + labelDy;
  const rawAngle = Math.atan2(p2.y - p1.y, p2.x - p1.x) * 180 / Math.PI;
  const labelAngle = (rawAngle > 90 || rawAngle < -90) ? rawAngle - 180 : rawAngle;

  return (
    <g>
      {!noExtensions && <line x1={a.x} y1={a.y} x2={p1.x} y2={p1.y} stroke="#94a3b8" strokeWidth="1.1" strokeDasharray="4 4" />}
      {!noExtensions && <line x1={b.x} y1={b.y} x2={p2.x} y2={p2.y} stroke="#94a3b8" strokeWidth="1.1" strokeDasharray="4 4" />}
      <line x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y} stroke="#334155" strokeWidth="1.7" markerStart="url(#isoArrow)" markerEnd="url(#isoArrow)" />
      <g transform={`translate(${lx.toFixed(1)}, ${ly.toFixed(1)}) rotate(${labelAngle.toFixed(1)})`}>
        <Label x={0} y={0} anchor={anchor}>{label}</Label>
      </g>
    </g>
  );
};

const LeaderLabel = ({
  from,
  to,
  label,
  anchor = 'start',
  accent = false,
  minWidth = 94,
  gap = 0,
}: {
  from: Point2;
  to: Point2;
  label: string;
  anchor?: 'start' | 'middle' | 'end';
  accent?: boolean;
  minWidth?: number;
  gap?: number;
}) => {
  const labelW = Math.max(minWidth, label.length * 7.1 + 14);
  const labelX = anchor === 'end' ? to.x - labelW - gap + 8 : anchor === 'middle' ? to.x - labelW / 2 : to.x + gap - 8;
  const labelAnchorX = anchor === 'end' ? to.x - gap : anchor === 'middle' ? to.x : to.x + gap;

  return (
    <g>
      <line x1={from.x} y1={from.y} x2={to.x} y2={to.y} stroke={accent ? '#0891b2' : '#64748b'} strokeWidth="1.3" strokeDasharray="4 4" />
      <circle cx={from.x} cy={from.y} r="3" fill={accent ? '#22d3ee' : '#64748b'} />
      <rect
        x={labelX}
        y={to.y - 17}
        width={labelW}
        height="24"
        rx="6"
        fill="#ffffff"
        stroke={accent ? '#67e8f9' : '#cbd5e1'}
        opacity="0.94"
      />
      <Label x={labelAnchorX} y={to.y} anchor={anchor} muted={!accent}>{label}</Label>
    </g>
  );
};

function renderPole(base: Point2, top: Point2, meterScale: number) {
  const poleStroke = clamp(meterScale * 0.07, 2, 4.2);
  const highlightStroke = clamp(poleStroke * 0.3, 0.55, 1);
  const baseRx = clamp(meterScale * 0.14, 3.4, 6.5);
  const baseRy = clamp(meterScale * 0.06, 1.8, 3.2);

  return (
    <g>
      {/* Poste vertical */}
      <line x1={base.x} y1={base.y} x2={top.x} y2={top.y} stroke="#0f172a" strokeWidth={poleStroke} strokeLinecap="round" />
      <line x1={base.x - poleStroke * 0.28} y1={base.y} x2={top.x - poleStroke * 0.28} y2={top.y} stroke="#7dd3fc" strokeWidth={highlightStroke} strokeLinecap="round" opacity="0.22" />
      <ellipse cx={base.x} cy={base.y + baseRy * 0.6} rx={baseRx} ry={baseRy} fill="#0f172a" opacity="0.16" />
    </g>
  );
}

function renderArm(top: Point2, rear: Point2, showArm: boolean, meterScale: number) {
  if (!showArm) return null;

  const dx = rear.x - top.x;
  const dy = rear.y - top.y;
  const sag = clamp(meterScale * 0.16, 2, 7);
  const armStroke = clamp(meterScale * 0.07, 1.8, 3.4);
  const highlightStroke = clamp(armStroke * 0.3, 0.5, 0.95);
  const c1 = { x: top.x + dx * 0.06, y: top.y - sag };
  const c2 = { x: top.x + dx * 0.78, y: rear.y - Math.max(sag * 0.6, Math.abs(dy) * 0.28) };
  const d = `M ${top.x.toFixed(1)} ${top.y.toFixed(1)} C ${c1.x.toFixed(1)} ${c1.y.toFixed(1)} ${c2.x.toFixed(1)} ${c2.y.toFixed(1)} ${rear.x.toFixed(1)} ${rear.y.toFixed(1)}`;

  return (
    <g>
      {/* Brazo corto, conectado a la parte trasera de la luminaria */}
      <path d={d} fill="none" stroke="#0f172a" strokeWidth={armStroke} strokeLinecap="round" />
      <path d={d} fill="none" stroke="#7dd3fc" strokeWidth={highlightStroke} strokeLinecap="round" opacity="0.24" />
    </g>
  );
}

function renderLuminaireHead(rear: Point2, angle: number, length: number) {
  const l = length;
  const rearTop = -l * 0.24;
  const rearBottom = l * 0.27;
  const noseTop = -l * 0.16;
  const noseBottom = l * 0.16;
  const strokeWidth = clamp(l * 0.06, 0.65, 1.1);

  return (
    <g transform={`translate(${rear.x.toFixed(1)} ${rear.y.toFixed(1)}) rotate(${angle.toFixed(1)})`}>
      {/* Sombra bajo la cabeza */}
      <ellipse cx={l * 0.5} cy={l * 0.34} rx={l * 0.4} ry={l * 0.14} fill="#0f172a" opacity="0.15" filter="url(#isoHeadGlow)" />
      {/* back/rear: lado conectado al brazo */}
      <path d={`M 0 ${rearTop.toFixed(1)} C ${(l * 0.09).toFixed(1)} ${(-l * 0.33).toFixed(1)} ${(l * 0.22).toFixed(1)} ${(-l * 0.32).toFixed(1)} ${(l * 0.32).toFixed(1)} ${(-l * 0.21).toFixed(1)} L ${(l * 0.28).toFixed(1)} ${rearBottom.toFixed(1)} C ${(l * 0.16).toFixed(1)} ${(l * 0.34).toFixed(1)} ${(l * 0.04).toFixed(1)} ${(l * 0.25).toFixed(1)} 0 ${rearTop.toFixed(1)} Z`} fill="#102238" stroke="#091728" strokeWidth={strokeWidth} />
      {/* Cuerpo simple: trasera alta, frontal fino y redondeado */}
      <path d={`M ${(l * 0.26).toFixed(1)} ${(-l * 0.18).toFixed(1)} L ${(l * 0.84).toFixed(1)} ${noseTop.toFixed(1)} C ${(l * 1.02).toFixed(1)} ${(-l * 0.08).toFixed(1)} ${(l * 1.03).toFixed(1)} ${(l * 0.05).toFixed(1)} ${(l * 0.86).toFixed(1)} ${noseBottom.toFixed(1)} L ${(l * 0.32).toFixed(1)} ${rearBottom.toFixed(1)} Z`} fill="#183a5d" stroke="#0d2740" strokeWidth={strokeWidth} />
      {/* Cara superior */}
      <path d={`M ${(l * 0.34).toFixed(1)} ${(-l * 0.22).toFixed(1)} L ${(l * 0.78).toFixed(1)} ${(-l * 0.11).toFixed(1)} C ${(l * 0.86).toFixed(1)} ${(-l * 0.1).toFixed(1)} ${(l * 0.9).toFixed(1)} ${(-l * 0.03).toFixed(1)} ${(l * 0.8).toFixed(1)} ${(l * 0.04).toFixed(1)} L ${(l * 0.38).toFixed(1)} ${(-l * 0.04).toFixed(1)} Z`} fill="#2a5274" opacity="0.72" />
      {/* Difusor inferior plano */}
      <path d={`M ${(l * 0.36).toFixed(1)} ${(l * 0.09).toFixed(1)} L ${(l * 0.76).toFixed(1)} ${(l * 0.1).toFixed(1)} C ${(l * 0.86).toFixed(1)} ${(l * 0.1).toFixed(1)} ${(l * 0.86).toFixed(1)} ${(l * 0.17).toFixed(1)} ${(l * 0.74).toFixed(1)} ${(l * 0.2).toFixed(1)} L ${(l * 0.38).toFixed(1)} ${(l * 0.16).toFixed(1)} Z`} fill="#c8f7ff" opacity="0.76" />
      <path d={`M ${(l * 0.42).toFixed(1)} ${(l * 0.13).toFixed(1)} L ${(l * 0.68).toFixed(1)} ${(l * 0.16).toFixed(1)}`} stroke="#67e8f9" strokeWidth={clamp(l * 0.045, 0.45, 0.75)} strokeLinecap="round" opacity="0.55" />
    </g>
  );
}

function renderLuminaire(
  scene: IsoScene,
  pole: { x: number; z: number; side: Side },
  index: number,
  cfg: IsoCfg,
) {
  const rowSideSign = pole.side === 'right' ? -1 : 1;
  const top3 = { x: pole.x, y: cfg.height, z: pole.z };
  const head3 = {
    x: pole.x,
    y: cfg.height,
    z: pole.side === 'center' ? pole.z : pole.z + rowSideSign * scene.armProjection,
  };
  const base = scene.project({ x: pole.x, y: 0, z: pole.z });
  const top = scene.project(top3);
  const rear = scene.project(head3);
  const roadTarget = scene.project({
    x: pole.x,
    y: head3.y,
    z: head3.z + rowSideSign * Math.max(0.8, scene.armProjection * 0.35),
  });
  const fallbackDx = roadTarget.x - rear.x;
  const fallbackDy = roadTarget.y - rear.y;
  const fallbackAngle = Math.atan2(fallbackDy, fallbackDx) / DEG;
  const horizontalDirection = Math.cos(fallbackAngle * DEG) >= 0 ? 1 : -1;
  const headAngle = fallbackAngle - horizontalDirection * cfg.tilt * HEAD_TILT_VISUAL_GAIN;
  const headLengthMeters = cfg.arrangement === 'Bilateral' ? 0.45 : 0.65;
  const headLength = clamp(scene.meterScale * headLengthMeters, 10, 22);
  const beam = beamFootprint(scene, pole, rowSideSign, cfg);

  return (
    <g key={`${pole.x}-${pole.z}-${index}`}>
      <polygon points={path(beam)} fill="url(#isoGlow)" stroke="#67e8f9" strokeOpacity="0.18" />
      {renderPole(base, top, scene.meterScale)}
      {renderArm(top, rear, cfg.arm_length > 0, scene.meterScale)}
      {renderLuminaireHead(rear, headAngle, headLength)}
    </g>
  );
}

const RoadIsometricOverview: React.FC = () => {
  const { t } = useI18n();
  const cfg = useConfigStore(
    useShallow(s => ({
      arm_length: s.arm_length,
      arrangement: s.arrangement,
      height: s.height,
      pole_offset: s.pole_offset,
      pole_side: s.pole_side,
      road_width: s.road_width,
      roadElements: s.roadElements,
      spacing: s.spacing,
      tilt: s.tilt,
    })),
  );

  const scene = useMemo(() => {
    const W = cfg.road_width;
    const length = Math.max(cfg.spacing * 2.15, 34);
    const x0 = -length / 2;
    const x1 = length / 2;
    const poleRows = buildPoleRows(cfg);
    const armProjection = Math.max(0, cfg.arm_length);
    const points: Point3[] = [
      { x: x0, y: -ROAD_DEPTH, z: 0 },
      { x: x1, y: -ROAD_DEPTH, z: 0 },
      { x: x0, y: -ROAD_DEPTH, z: W },
      { x: x1, y: -ROAD_DEPTH, z: W },
      { x: x0, y: 0, z: 0 },
      { x: x1, y: 0, z: W },
      { x: x0, y: cfg.height + 1.2, z: 0 },
      { x: x1, y: cfg.height + 1.2, z: W },
    ];

    poleRows.forEach((pole) => {
      const sideSign = pole.side === 'right' ? -1 : 1;
      const headZ = pole.side === 'center' ? pole.z : pole.z + sideSign * armProjection;
      points.push({ x: pole.x, y: 0, z: pole.z });
      points.push({ x: pole.x, y: cfg.height, z: headZ });
    });

    const { project, scale } = makeProjector(points);
    const prism = (z0: number, z1: number) => {
      const top = [
        project({ x: x0, y: 0, z: z0 }),
        project({ x: x1, y: 0, z: z0 }),
        project({ x: x1, y: 0, z: z1 }),
        project({ x: x0, y: 0, z: z1 }),
      ];
      const front = [
        project({ x: x0, y: 0, z: z1 }),
        project({ x: x1, y: 0, z: z1 }),
        project({ x: x1, y: -ROAD_DEPTH, z: z1 }),
        project({ x: x0, y: -ROAD_DEPTH, z: z1 }),
      ];
      const end = [
        project({ x: x1, y: 0, z: z0 }),
        project({ x: x1, y: 0, z: z1 }),
        project({ x: x1, y: -ROAD_DEPTH, z: z1 }),
        project({ x: x1, y: -ROAD_DEPTH, z: z0 }),
      ];
      return { top, front, end };
    };

    let zPos = 0;
    const elements = cfg.roadElements.map((el) => {
      const z0 = zPos;
      const z1 = zPos + el.width;
      zPos = z1;
      return { ...el, z0, z1, p: prism(z0, z1) };
    });

    const totalLanes = cfg.roadElements
      .filter(e => e.type === 'carriageway')
      .reduce((s, e) => s + (e.lanes ?? 2), 0);

    return {
      project,
      length,
      x0,
      x1,
      W,
      elements,
      totalLanes,
      poleRows,
      armProjection,
      meterScale: scale,
    };
  }, [cfg]);

  const isBilateral = cfg.arrangement === 'Bilateral';
  const isCentralDouble = cfg.arrangement === 'Central Doble';
  const isStaggeredBilateral = cfg.arrangement === 'Bilateral Alternada';
  const spacingSide = ['Lineal', 'Bilateral', 'Bilateral Alternada', 'Central Doble'].includes(cfg.arrangement)
    ? 'right'
    : (cfg.pole_side === 'right' ? 'right' : 'left');
  const spacingZ = spacingSide === 'right' ? scene.W + 0.7 : -0.7;
  const spacingA = scene.project({ x: -cfg.spacing, y: 0.24, z: spacingZ });
  const spacingB = scene.project({ x: 0, y: 0.24, z: spacingZ });
  const spacingLabel = `${t('iso.spacing')} = ${cfg.spacing.toFixed(0)} m`;
  const widthA = scene.project({ x: scene.x1 + 0.4, y: 0.14, z: 0 });
  const widthB = scene.project({ x: scene.x1 + 0.4, y: 0.14, z: scene.W });
  const firstPole = scene.poleRows.reduce((best, pole) => {
    if (!best) return pole;
    if (pole.side === cfg.pole_side && Math.abs(pole.x) <= Math.abs(best.x)) return pole;
    return Math.abs(pole.x) < Math.abs(best.x) ? pole : best;
  }, scene.poleRows[0] as (typeof scene.poleRows)[number] | undefined);
  const sideSign = firstPole?.side === 'right' ? -1 : 1;
  const annotationSideSign = isStaggeredBilateral ? 1 : sideSign;
  const poleBase3 = firstPole ? { x: firstPole.x, y: 0, z: firstPole.z } : null;
  const poleTop3 = firstPole ? { x: firstPole.x, y: cfg.height, z: firstPole.z } : null;
  const head3 = firstPole
    ? {
        x: firstPole.x,
        y: cfg.height,
        z: firstPole.side === 'center' ? firstPole.z : firstPole.z + sideSign * scene.armProjection,
      }
    : null;
  const armReferenceHead3 = firstPole
    ? {
        x: firstPole.x,
        y: cfg.height,
        z: firstPole.side === 'center' ? firstPole.z : firstPole.z + sideSign * cfg.arm_length,
      }
    : null;
  const roadEdgeZ = firstPole
    ? (firstPole.side === 'center'
      ? scene.W / 2
      : getCarriagewayEdge(cfg.roadElements, firstPole.side))
    : 0;
  const roadEdge3 = firstPole ? { x: firstPole.x, y: 0.18, z: roadEdgeZ } : null;
  const poleBase = poleBase3 ? scene.project(poleBase3) : null;
  const poleTop = poleTop3 ? scene.project(poleTop3) : null;
  const head = head3 ? scene.project(head3) : null;
  const armReferenceHead = armReferenceHead3 ? scene.project(armReferenceHead3) : null;
  const roadEdge = roadEdge3 ? scene.project(roadEdge3) : null;
  const rMeasurePoint = poleBase && roadEdge ? mid(poleBase, roadEdge) : null;
  const rLabelPoint = poleBase && poleTop ? {
    x: poleTop.x + annotationSideSign * 44,
    y: (poleTop.y + poleBase.y) / 2 + (isBilateral || isCentralDouble || isStaggeredBilateral ? 26 : 18),
  } : null;
  const armDimensionLift = poleTop && armReferenceHead && isStaggeredBilateral
    ? Math.max(poleTop.y, armReferenceHead.y) - Math.min(poleTop.y, armReferenceHead.y) + 16
    : 0;
  const armDimensionA = poleTop && isStaggeredBilateral ? { ...poleTop, y: poleTop.y - armDimensionLift } : poleTop;
  const armDimensionB = armReferenceHead && isStaggeredBilateral ? { ...armReferenceHead, y: armReferenceHead.y - armDimensionLift } : armReferenceHead;
  const alphaArcStart = poleTop ? scene.project({ x: poleTop3!.x, y: poleTop3!.y + 0.01, z: poleTop3!.z + sideSign * 1.15 }) : null;
  const alphaArcEnd = head ? offsetPoint(poleTop!, head, 26) : null;
  const luminaireHeight = cfg.height;
  const spacing = spacingLayout(
    spacingA,
    spacingB,
    spacingLabel,
    [],
    spacingSide === 'right' ? [24] : [-24],
  );
  const spacingText = { x: spacing.m.x, y: spacing.m.y + (spacingSide === 'right' ? 24 : -12) };

  // Pole offset dimension Y lift for bilateral arrangements
  const highestLuminaireY = Math.min(
    ...scene.poleRows.flatMap((pole) => {
      const rowSideSign = pole.side === 'right' ? -1 : 1;
      return [
        scene.project({ x: pole.x, y: cfg.height, z: pole.z }).y,
        scene.project({
          x: pole.x,
          y: cfg.height,
          z: pole.side === 'center' ? pole.z : pole.z + rowSideSign * scene.armProjection,
        }).y,
      ];
    }),
  );
  const poleOffsetDy = (isBilateral || isCentralDouble)
    ? Math.max(18, highestLuminaireY - 28) - Math.min(widthA.y, widthB.y)
    : 0;

  // Lane lines per carriageway element
  const laneLineElements = scene.elements.flatMap((el) => {
    if (el.type !== 'carriageway') return [];
    const elLanes = el.lanes ?? 2;
    return Array.from({ length: Math.max(0, elLanes - 1) }, (_, i) => {
      const z = el.z0 + ((i + 1) / Math.max(elLanes, 1)) * el.width;
      const a = scene.project({ x: scene.x0 + 2, y: 0.04, z });
      const b = scene.project({ x: scene.x1 - 2, y: 0.04, z });
      return <line key={`ll-${el.z0}-${i}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#f8fafc" strokeWidth="2.2" strokeDasharray="13 10" opacity="0.78" />;
    });
  });

  // Flow arrows per lane within each carriageway element's z-range
  const flowArrows = scene.elements.flatMap((el) => {
    if (el.type !== 'carriageway') return [];
    const elLanes = el.lanes ?? 2;
    const laneWidth = el.width / elLanes;
    return Array.from({ length: elLanes }, (_, i) => {
      const z = el.z0 + (i + 0.5) * laneWidth;
      return {
        start: scene.project({ x: scene.x0 + 4.4, y: 0.16, z }),
        end: scene.project({ x: scene.x0 + 9.2, y: 0.16, z }),
        key: `flow-${el.z0}-${i}`,
      };
    });
  });

  // Element boundaries (thin lines between elements)
  const elementBoundaries = scene.elements.slice(0, -1).map((el) => {
    const z = el.z0 + el.width;
    const a = scene.project({ x: scene.x0, y: 0.03, z });
    const b = scene.project({ x: scene.x1, y: 0.03, z });
    return <line key={`boundary-${z}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#64748b" strokeWidth="0.8" strokeDasharray="5 4" opacity="0.5" />;
  });

  return (
    <div className="road-diagram-card flex h-full min-h-0 flex-col overflow-hidden rounded-xl">
      <div className="flex items-center justify-between border-b border-[#E8E2D8] bg-[#FFFFFF]/90 px-4 py-2">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-[#6A6A6A]">
          <Cuboid className="h-4 w-4 text-blue-500" aria-hidden="true" />
          {t('roadView.plantAndSection')}
        </h3>
        <span className="text-xs font-medium text-[#A09A91]">{t('iso.height')} = {luminaireHeight.toFixed(1)} m - {t('iso.totalWidth')} = {scene.W.toFixed(1)} m</span>
      </div>
      <div className="min-h-0 flex-1 p-2">
        <svg className="h-full w-full" viewBox={`0 0 ${SVG_W} ${SVG_H}`} role="img" aria-label="Isometric road lighting overview">
          <defs>
            <marker id="isoArrow" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0 0 L10 5 L0 10Z" fill="#334155" />
            </marker>
            <linearGradient id="isoAsphalt" x1="0" x2="1" y1="0" y2="1">
              <stop offset="0%" stopColor="#64748b" />
              <stop offset="100%" stopColor="#1f2937" />
            </linearGradient>
            <linearGradient id="isoAsphaltSide" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor="#334155" />
              <stop offset="100%" stopColor="#172033" />
            </linearGradient>
            <linearGradient id="isoWalk" x1="0" x2="1" y1="0" y2="1">
              <stop offset="0%" stopColor="#e0f2fe" />
              <stop offset="100%" stopColor="#a8bfd3" />
            </linearGradient>
            <radialGradient id="isoGlow" cx="50%" cy="42%" r="58%">
              <stop offset="0%" stopColor="#67e8f9" stopOpacity="0.36" />
              <stop offset="100%" stopColor="#67e8f9" stopOpacity="0" />
            </radialGradient>
            <filter id="isoSoftShadow" x="-30%" y="-30%" width="160%" height="160%">
              <feDropShadow dx="0" dy="10" stdDeviation="8" floodColor="#0f172a" floodOpacity="0.16" />
            </filter>
            <filter id="isoHeadGlow" x="-90%" y="-90%" width="280%" height="280%">
              <feGaussianBlur stdDeviation="4" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>

          <rect width={SVG_W} height={SVG_H} fill="#f8fafc" />
          <path d={`M48 86 H${SVG_W - 36} M48 176 H${SVG_W - 36} M48 266 H${SVG_W - 36} M48 356 H${SVG_W - 36} M124 34 V${SVG_H - 34} M250 34 V${SVG_H - 34} M376 34 V${SVG_H - 34} M502 34 V${SVG_H - 34} M628 34 V${SVG_H - 34} M754 34 V${SVG_H - 34}`} stroke="#cbd5e1" strokeWidth="0.8" opacity="0.46" />

          <g filter="url(#isoSoftShadow)">
            {scene.elements.map((el) => {
              const isCw = el.type === 'carriageway';
              return (
                <g key={`el-${el.z0}`}>
                  <polygon points={path(el.p.front)} fill={isCw ? 'url(#isoAsphaltSide)' : '#8ea6bb'} />
                  <polygon points={path(el.p.end)} fill={isCw ? '#2b384d' : '#b8cadd'} />
                  <polygon points={path(el.p.top)} fill={isCw ? 'url(#isoAsphalt)' : 'url(#isoWalk)'} stroke={isCw ? '#93c5fd' : '#7dd3fc'} strokeOpacity="0.35" />
                </g>
              );
            })}
          </g>

          {laneLineElements}
          {elementBoundaries}

          {scene.poleRows.map((pole, index) => renderLuminaire(scene, pole, index, cfg))}

          {(() => {
            const cws = scene.elements.filter(e => e.type === 'carriageway');
            if (cws.length > 1) {
              const leftEdge = cws[0].z0 + cws[0].width;
              const rightEdge = cws[cws.length - 1].z0;
              const medianZ = (leftEdge + rightEdge) / 2;
              const m1 = scene.project({ x: scene.x0 + 2.2, y: 0.18, z: medianZ });
              const m2 = scene.project({ x: scene.x1 - 2.2, y: 0.18, z: medianZ });
              return <line x1={m1.x} y1={m1.y} x2={m2.x} y2={m2.y} stroke="#e2e8f0" strokeWidth="2" strokeDasharray="18 12" opacity="0.82" />;
            }
            return null;
          })()}

          <g>
            <line x1={spacing.p1.x} y1={spacing.p1.y} x2={spacing.p2.x} y2={spacing.p2.y} stroke="#334155" strokeWidth="1.7" markerStart="url(#isoArrow)" markerEnd="url(#isoArrow)" />
            <g transform={`translate(${spacingText.x.toFixed(1)}, ${spacingText.y.toFixed(1)}) rotate(${(Math.atan2(spacing.p2.y - spacing.p1.y, spacing.p2.x - spacing.p1.x) * 180 / Math.PI).toFixed(1)})`}>
              <Label x={0} y={0}>{spacingLabel}</Label>
            </g>
          </g>
          <Dimension
            a={widthA}
            b={widthB}
            label={`${t('iso.totalWidth')} = ${scene.W.toFixed(1)} m`}
            lift={poleOffsetDy - 18}
            labelLift={22}
            labelDx={6}
            anchor="start"
            noExtensions
          />

          {rMeasurePoint && rLabelPoint && (
            <LeaderLabel
              from={rMeasurePoint}
              to={rLabelPoint}
              label={`${t('iso.poleOffset')} = ${cfg.pole_offset.toFixed(1)} m`}
              anchor={annotationSideSign === 1 ? 'start' : 'end'}
              minWidth={isCentralDouble || isStaggeredBilateral ? 86 : 94}
              gap={isCentralDouble || isStaggeredBilateral ? 5 : 0}
            />
          )}

          {armDimensionA && armDimensionB && cfg.arm_length > 0 && (
            <Dimension
              a={armDimensionA}
              b={armDimensionB}
              label={`B = ${cfg.arm_length.toFixed(1)} m`}
              lift={isStaggeredBilateral ? 0 : 24}
              labelLift={isStaggeredBilateral ? -13 : -15}
              noExtensions={isStaggeredBilateral}
            />
          )}

          {poleTop && head && alphaArcStart && alphaArcEnd && (
            <g>
              <line x1={poleTop.x} y1={poleTop.y} x2={alphaArcStart.x} y2={alphaArcStart.y} stroke="#64748b" strokeWidth="1.2" strokeDasharray="4 4" />
              <path
                d={`M ${alphaArcStart.x.toFixed(1)} ${alphaArcStart.y.toFixed(1)} Q ${poleTop.x.toFixed(1)} ${poleTop.y.toFixed(1)} ${alphaArcEnd.x.toFixed(1)} ${alphaArcEnd.y.toFixed(1)}`}
                fill="none"
                stroke="#0891b2"
                strokeWidth="1.8"
              />
              <LeaderLabel
                from={mid(alphaArcStart, alphaArcEnd)}
                to={{ x: Math.min(SVG_W - 220, poleTop.x + 116), y: poleTop.y - 52 }}
                label={`${t('iso.tilt')} = ${Math.abs(cfg.tilt).toFixed(0)} deg`}
                anchor="start"
                accent
              />
            </g>
          )}

          {poleBase && poleTop && (
            <g>
              <line x1={poleBase.x + annotationSideSign * 34} y1={poleBase.y} x2={poleTop.x + annotationSideSign * 34} y2={poleTop.y} stroke="#334155" strokeWidth="1.7" markerStart="url(#isoArrow)" markerEnd="url(#isoArrow)" />
              <line x1={poleBase.x} y1={poleBase.y} x2={poleBase.x + annotationSideSign * 34} y2={poleBase.y} stroke="#94a3b8" strokeWidth="1.1" strokeDasharray="4 4" />
              <line x1={poleTop.x} y1={poleTop.y} x2={poleTop.x + annotationSideSign * 34} y2={poleTop.y} stroke="#94a3b8" strokeWidth="1.1" strokeDasharray="4 4" />
              <Label x={poleTop.x + annotationSideSign * 44} y={(poleTop.y + poleBase.y) / 2} anchor={annotationSideSign === 1 ? 'start' : 'end'}>
                {t('iso.height')} = {cfg.height.toFixed(1)} m
              </Label>
            </g>
          )}

          <g>
            {flowArrows.map((arrow) => (
              <line
                key={arrow.key}
                x1={arrow.start.x}
                y1={arrow.start.y}
                x2={arrow.end.x}
                y2={arrow.end.y}
                stroke="#e2e8f0"
                strokeWidth="2.2"
                markerEnd="url(#isoArrow)"
                opacity="0.86"
              />
            ))}
          </g>

        </svg>
      </div>
    </div>
  );
};

export default RoadIsometricOverview;
