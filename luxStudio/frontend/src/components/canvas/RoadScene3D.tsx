import { useEffect, useMemo, useRef, useState, useDeferredValue } from 'react';
import { Canvas, useFrame, useThree, ThreeEvent } from '@react-three/fiber';
import { OrbitControls, ContactShadows, Grid, Html, Stars } from '@react-three/drei';
import { EffectComposer, Bloom, Vignette } from '@react-three/postprocessing';
import { useShallow } from 'zustand/react/shallow';
import * as THREE from 'three';
import { useConfigStore, type ConfigState } from '../../store/useConfigStore';
import {
  buildBuildingRows,
  normalizeByScale,
  powerVisualFactor,
  resolveVisualizationScale,
  unitSuffix,
  type PhotometricDisplayUnit,
} from '../../lib/visualization3d';
import {
  buildPoles,
  computeCdAt,
  computeDisplayAt,
  computeDisplayStats,
  computeEAt,
  computeEvAt,
  effectiveMf,
  luminaireVisualTilt,
  sampleGradientColor,
  type Photometric,
  type PoleInfo,
} from '../../lib/roadScenePhotometry';
import type { RoadElement } from '../../types';
import DriverView, { getLaneInfo, type LaneInfo } from './DriverView';
import { driverPoleCountForSpacing } from '../../lib/driverLuminance';

// ponytail: converts K to RGB via Planckian approximation
function cctToColor(cct: number): string {
  const t = cct / 100;
  let r: number, g: number, b: number;
  if (cct <= 6600) {
    r = 255;
    g = 99.4708025861 * Math.log(t) - 161.1195681661;
    b = cct <= 2000 ? 0 : 138.5177312231 * Math.log(t - 10) - 305.0447927307;
  } else {
    r = 329.698727446 * Math.pow(t - 60, -0.1332047592);
    g = 288.1221695283 * Math.pow(t - 60, -0.0755148492);
    b = 255;
  }
  const clamp = (v: number) => Math.max(0, Math.min(255, v));
  // Chromatic adaptation: desaturate toward white for a perceptually realistic look
  const gray = (r + g + b) / 3;
  const s = 0.5;
  r = r + (gray - r) * s;
  g = g + (gray - g) * s;
  b = b + (gray - b) * s;
  const toHex = (v: number) => Math.round(clamp(v)).toString(16).padStart(2, '0');
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
}

// ponytail: procedural asphalt texture — replace with real texture map when available
function makeAsphaltTexture(): THREE.CanvasTexture {
  const canvas = document.createElement('canvas');
  canvas.width = 256;
  canvas.height = 256;
  const ctx = canvas.getContext('2d')!;
  // Base color
  ctx.fillStyle = '#2a303a';
  ctx.fillRect(0, 0, 256, 256);
  // Noise grain
  for (let i = 0; i < 12000; i++) {
    const x = Math.random() * 256;
    const y = Math.random() * 256;
    const v = 40 + Math.random() * 40;
    ctx.fillStyle = `rgb(${v+20},${v+18},${v+22})`;
    ctx.fillRect(x, y, 1.5, 1.5);
  }
  // Occasional lighter speckles
  for (let i = 0; i < 800; i++) {
    const x = Math.random() * 256;
    const y = Math.random() * 256;
    const v = 100 + Math.random() * 60;
    ctx.fillStyle = `rgb(${v+20},${v+18},${v+22})`;
    ctx.fillRect(x, y, 1, 1);
  }
  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(20, 4);
  tex.anisotropy = 4;
  return tex;
}

// Shared geometry cache: avoids recreating identical geometries across components
const _geoCache = new Map<string, THREE.BufferGeometry>();
function cachedGeo<T extends THREE.BufferGeometry>(key: string, factory: () => T): T {
  if (!_geoCache.has(key)) {
    _geoCache.set(key, factory());
  }
  return _geoCache.get(key) as T;
}
const _matCache = new Map<string, THREE.Material>();
function cachedMat<T extends THREE.Material>(key: string, factory: () => T): T {
  if (!_matCache.has(key)) {
    _matCache.set(key, factory());
  }
  return _matCache.get(key) as T;
}
const _photometricGeoCache = new WeakMap<Photometric, Map<string, THREE.BufferGeometry>>();
function cachedPhotometricGeo<T extends THREE.BufferGeometry>(p: Photometric, key: string, factory: () => T): T {
  let cache = _photometricGeoCache.get(p);
  if (!cache) {
    cache = new Map();
    _photometricGeoCache.set(p, cache);
  }
  if (!cache.has(key)) cache.set(key, factory());
  return cache.get(key) as T;
}

const SCENE_CFG_KEYS = [
  'arm_length',
  'arrangement',
  'building_height',
  'buildings_as_obstacles',
  'cct',
  'generate_buildings',
  'height',
  'illuminance_scale_max',
  'illuminance_scale_min',
  'lanes',
  'median_width',
  'mf',
  'photometric_display_unit',
  'pole_count',
  'pole_offset',
  'pole_side',
  'power',
  'roadElements',
  'road_width',
  'sidewalk_left',
  'sidewalk_right',
  'spacing',
  'tilt',
] as const satisfies ReadonlyArray<keyof ConfigState>;

type SceneCfg = Pick<ConfigState, (typeof SCENE_CFG_KEYS)[number]>;

const sceneCfgSelector = (state: ConfigState): SceneCfg => {
  const out = {} as SceneCfg;
  for (const key of SCENE_CFG_KEYS) {
    (out as any)[key] = state[key];
  }
  return out;
};

const useSceneCfg = () => useConfigStore(useShallow(sceneCfgSelector));

const COLORS = {
  asphalt: '#1f2937',
  sidewalk: '#9ca3af',
  laneMark: '#f8fafc',
  pole: '#64748b',
  arm: '#64748b',
  headBody: '#fbbf24',
  headGlass: '#fef3c7',
  ground: '#020617',
  grid: '#1e293b',
  probe: '#22d3ee',
};

function LaneDashInstanced({ positions, count }: { positions: number[]; count: number }) {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const geom = useMemo(() => cachedGeo('lane-dash', () => new THREE.PlaneGeometry(0.6, 0.12)), []);
  const mat = useMemo(() => cachedMat('lane-dash-mat', () => new THREE.MeshStandardMaterial({
    color: '#f8fafc',
    roughness: 0.3,
    metalness: 0.0,
  })), []);
  useEffect(() => {
    if (!meshRef.current) return;
    const dummy = new THREE.Object3D();
    for (let i = 0; i < count; i++) {
      dummy.position.set(positions[i], 0, 0);
      dummy.rotation.x = -Math.PI / 2;
      dummy.updateMatrix();
      meshRef.current.setMatrixAt(i, dummy.matrix);
    }
    meshRef.current.instanceMatrix.needsUpdate = true;
  }, [positions, count]);
  return <instancedMesh ref={meshRef} args={[geom, mat, count]} />;
}


function Road({ cfg, onGroundClick, followCamera = false }: { cfg: SceneCfg; onGroundClick: (e: ThreeEvent<MouseEvent>) => void; followCamera?: boolean }) {
  const groupRef = useRef<THREE.Group>(null);
  const { camera } = useThree();
  const asphaltTex = useMemo(makeAsphaltTexture, []);
  const elements = cfg.roadElements as RoadElement[] | undefined;
  const W = cfg.road_width;
  const length = Math.max(cfg.spacing * Math.max(1, cfg.pole_count - 1) * 1.3, 30);
  const totalWidth = W;

  const dashX = useMemo(() => {
    const arr: number[] = [];
    const dash = 0.6;
    const gap = 0.9;
    for (let x = -length / 2 + 0.3; x < length / 2; x += dash + gap) {
      arr.push(x + dash / 2);
    }
    return arr;
  }, [length]);

  const elementMeshes = useMemo(() => {
    if (!elements || elements.length === 0) return null;
    let yPos = 0;
    const meshes: React.ReactNode[] = [];

    for (let i = 0; i < elements.length; i++) {
      const el = elements[i];
      const isCw = el.type === 'carriageway';
      const sw = el.width;
      const center = yPos + sw / 2;
      const key = `el-${i}`;

      meshes.push(
        <mesh
          key={key}
          receiveShadow
          rotation={[-Math.PI / 2, 0, 0]}
          position={[0, isCw ? 0.005 : 0.002, center]}
          onClick={onGroundClick}
        >
          <planeGeometry args={[length, sw]} />
          {isCw ? (
            <meshPhysicalMaterial
              map={asphaltTex}
              roughness={0.75}
              metalness={0.0}
              clearcoat={0.15}
              clearcoatRoughness={0.8}
            />
          ) : (
            <meshPhysicalMaterial color={COLORS.sidewalk} roughness={0.85} clearcoat={0.2} clearcoatRoughness={0.6} />
          )}
        </mesh>
      );

      if (isCw) {
        const elLanes = el.lanes ?? 2;
        const laneW = sw / Math.max(elLanes, 1);
        for (let li = 0; li < Math.max(0, elLanes - 1); li++) {
          const lz = yPos + (li + 1) * laneW;
          meshes.push(
            <group key={`${key}-lane-${li}`} position={[0, 0.012, lz]}>
              <LaneDashInstanced positions={dashX} count={dashX.length} />
            </group>
          );
        }
        // Edges
        meshes.push(
          <mesh key={`${key}-edge-l`} receiveShadow position={[0, 0.03, yPos]} rotation={[0, 0, 0]}>
            <boxGeometry args={[length, 0.06, 0.08]} />
            <meshStandardMaterial color="#6b7280" roughness={0.5} metalness={0.3} />
          </mesh>
        );
        meshes.push(
          <mesh key={`${key}-edge-r`} receiveShadow position={[0, 0.03, yPos + sw]} rotation={[0, 0, 0]}>
            <boxGeometry args={[length, 0.06, 0.08]} />
            <meshStandardMaterial color="#6b7280" roughness={0.5} metalness={0.3} />
          </mesh>
        );
        // Edge lines
        meshes.push(
          <mesh key={`${key}-line-l`} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.014, yPos]}>
            <planeGeometry args={[length, 0.15]} />
            <meshStandardMaterial color={COLORS.laneMark} />
          </mesh>
        );
        meshes.push(
          <mesh key={`${key}-line-r`} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.014, yPos + sw]}>
            <planeGeometry args={[length, 0.15]} />
            <meshStandardMaterial color={COLORS.laneMark} />
          </mesh>
        );
      }

      yPos += sw;
    }
    return meshes;
  }, [elements, length, onGroundClick]);

  useFrame(() => {
    if (!followCamera || !groupRef.current) return;
    const repeat = Math.max(10, cfg.spacing);
    groupRef.current.position.x = Math.floor(camera.position.x / repeat) * repeat;
  });

  return (
    <group ref={groupRef}>
      <mesh receiveShadow rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.01, totalWidth / 2 - totalWidth / 2]}>
        <planeGeometry args={[length, totalWidth + 4]} />
        <meshStandardMaterial color={COLORS.ground} roughness={1} />
      </mesh>
      {elementMeshes}
    </group>
  );
}

function buildFacadeGeometry(
  b: { x: number; z: number; width: number; depth: number; height: number; id: string },
  poles: PoleInfo[],
  p: Photometric,
  fluxScale: number,
  mf: number,
  scaleMin: number = 0,
  scaleMax: number = 50,
  cct: number = 4000,
  isNight: boolean = false,
  unit: PhotometricDisplayUnit = 'lux',
): THREE.BufferGeometry {
  const segW = 8;
  const segH = 14;
  const isLeft = b.id.startsWith('left-');
  const facadeZ = isLeft ? b.z + b.depth / 2 + 0.05 : b.z - b.depth / 2 - 0.05;
  const halfW = b.width / 2;
  const nv = (segW + 1) * (segH + 1);
  const positions = new Float32Array(nv * 3);
  const colors = new Float32Array(nv * 3);
  const normals = new Float32Array(nv * 3);
  const normalZ = isLeft ? 1 : -1;
  const luxValues: number[] = [];
  let vi = 0;
  for (let iy = 0; iy <= segH; iy++) {
    for (let ix = 0; ix <= segW; ix++) {
      const wx = b.x - halfW + (ix / segW) * b.width;
      const wy = (iy / segH) * b.height;
      const wz = facadeZ;
      positions[vi * 3] = wx;
      positions[vi * 3 + 1] = wy;
      positions[vi * 3 + 2] = wz;
      normals[vi * 3] = 0;
      normals[vi * 3 + 1] = 0;
      normals[vi * 3 + 2] = normalZ;
      const raw = computeEvAt(wx, wz, poles, p, fluxScale, mf, wy, normalZ);
      luxValues.push(unit === 'candela' ? raw * 0.3 / Math.PI : raw);
      vi++;
    }
  }
  const segs = segW * segH * 6;
  const idx = new (nv < 65536 ? Uint16Array : Uint32Array)(segs);
  let ti = 0;
  for (let iy = 0; iy < segH; iy++) {
    for (let ix = 0; ix < segW; ix++) {
      const a = iy * (segW + 1) + ix;
      const b2 = iy * (segW + 1) + ix + 1;
      const c = (iy + 1) * (segW + 1) + ix;
      const d = (iy + 1) * (segW + 1) + ix + 1;
      idx[ti++] = a; idx[ti++] = c; idx[ti++] = b2;
      idx[ti++] = b2; idx[ti++] = c; idx[ti++] = d;
    }
  }
  const facadeMax = Math.max(0.01, ...luxValues);
  const facadeScale = scaleMax > scaleMin
    ? { min: scaleMin, max: scaleMax }
    : { min: 0, max: facadeMax };
  if (isNight) {
    const lightColor = new THREE.Color(cctToColor(cct));
    const buildingBase = new THREE.Color('#080808');
    for (let i = 0; i < nv; i++) {
      const t = normalizeByScale(luxValues[i], facadeScale);
      const intensity = t;
      const litR = Math.min(1, buildingBase.r + lightColor.r * intensity * 0.4);
      const litG = Math.min(1, buildingBase.g + lightColor.g * intensity * 0.4);
      const litB = Math.min(1, buildingBase.b + lightColor.b * intensity * 0.4);
      colors[i * 3] = buildingBase.r * (1 - intensity) + litR * intensity;
      colors[i * 3 + 1] = buildingBase.g * (1 - intensity) + litG * intensity;
      colors[i * 3 + 2] = buildingBase.b * (1 - intensity) + litB * intensity;
    }
  } else {
    for (let i = 0; i < nv; i++) {
      const t = normalizeByScale(luxValues[i], facadeScale);
      const c = sampleGradientColor(Math.min(1, Math.max(0, t)));
      colors[i * 3] = c.r;
      colors[i * 3 + 1] = c.g;
      colors[i * 3 + 2] = c.b;
    }
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  geo.setAttribute('normal', new THREE.BufferAttribute(normals, 3));
  geo.setIndex(new THREE.BufferAttribute(idx, 1));
  return geo;
}

function autoLevels(maxEv: number): number[] {
  if (maxEv < 0.5) return [];
  const magnitude = Math.pow(10, Math.floor(Math.log10(maxEv)));
  const raw = maxEv / magnitude;
  let step: number;
  if (raw <= 2) step = 0.2 * magnitude;
  else if (raw <= 5) step = 0.5 * magnitude;
  else step = 1.0 * magnitude;
  const levels: number[] = [];
  for (let v = step; v < maxEv - step * 0.05; v += step) {
    levels.push(Math.round(v * 100) / 100);
  }
  if (levels.length < 2) {
    levels.push(Math.round(maxEv * 0.5 * 100) / 100);
  }
  return levels;
}

const MS_LOOKUP: number[][] = [
  [],          // 0
  [0, 3],      // 1
  [0, 1],      // 2
  [1, 3],      // 3
  [1, 2],      // 4
  [0, 1, 2, 3], // 5
  [0, 2],      // 6
  [2, 3],      // 7
  [2, 3],      // 8
  [0, 2],      // 9
  [0, 1, 2, 3], // 10
  [1, 2],      // 11
  [1, 3],      // 12
  [0, 1],      // 13
  [0, 3],      // 14
  [],          // 15
];

function marchingSquaresSegments(
  xs: number[],
  ys: number[],
  grid: number[][],
  threshold: number,
  facadeZ: number,
  normalZ: number,
  outPositions: number[],
  outColors: number[],
  facadeMaxEv: number,
): void {
  const segX = xs.length - 1;
  const segY = ys.length - 1;
  const nx = xs.length;
  const contourZ = facadeZ + 0.002 * normalZ;

  const tLevel = normalizeByScale(threshold, { min: 0, max: Math.max(0.01, facadeMaxEv) });
  const levelColor = sampleGradientColor(tLevel);

  for (let j = 0; j < segY; j++) {
    for (let i = 0; i < segX; i++) {
      const v0 = grid[j][i];
      const v1 = grid[j][i + 1];
      const v2 = grid[j + 1][i + 1];
      const v3 = grid[j + 1][i];

      const b0 = v0 >= threshold ? 1 : 0;
      const b1 = v1 >= threshold ? 1 : 0;
      const b2 = v2 >= threshold ? 1 : 0;
      const b3 = v3 >= threshold ? 1 : 0;
      const caseIdx = b0 | (b1 << 1) | (b2 << 2) | (b3 << 3);

      const segs = MS_LOOKUP[caseIdx];
      if (segs.length === 0) continue;

      const interpX = (va: number, vb: number, xa: number, xb: number): number => {
        if (Math.abs(vb - va) < 1e-10) return (xa + xb) / 2;
        return xa + (threshold - va) / (vb - va) * (xb - xa);
      };
      const interpY = (va: number, vb: number, ya: number, yb: number): number => {
        if (Math.abs(vb - va) < 1e-10) return (ya + yb) / 2;
        return ya + (threshold - va) / (vb - va) * (yb - ya);
      };

      const edgeVerts: [number, number, number][] = [];
      if (b0 !== b1) {
        edgeVerts[0] = [interpX(v0, v1, xs[i], xs[i + 1]), ys[j], contourZ];
      }
      if (b1 !== b2) {
        edgeVerts[1] = [xs[i + 1], interpY(v1, v2, ys[j], ys[j + 1]), contourZ];
      }
      if (b2 !== b3) {
        edgeVerts[2] = [interpX(v3, v2, xs[i], xs[i + 1]), ys[j + 1], contourZ];
      }
      if (b3 !== b0) {
        edgeVerts[3] = [xs[i], interpY(v0, v3, ys[j], ys[j + 1]), contourZ];
      }

      for (let s = 0; s < segs.length; s += 2) {
        const p1 = edgeVerts[segs[s]];
        const p2 = edgeVerts[segs[s + 1]];
        if (!p1 || !p2) continue;
        outPositions.push(p1[0], p1[1], p1[2]);
        outPositions.push(p2[0], p2[1], p2[2]);
        outColors.push(levelColor.r, levelColor.g, levelColor.b);
        outColors.push(levelColor.r, levelColor.g, levelColor.b);
      }
    }
  }
}

function FacadeIsoluxContours({
  rows,
  poles,
  photometric,
  fluxScale,
  mf,
}: {
  rows: ReturnType<typeof buildBuildingRows>;
  poles: PoleInfo[];
  photometric: Photometric | null;
  fluxScale: number;
  mf: number;
}) {
  const geometry = useMemo(() => {
    if (!photometric || poles.length === 0) return null;

    const segX = 40;
    const segY = 60;
    const positions: number[] = [];
    const colors: number[] = [];

    for (const b of rows) {
      const isLeft = b.id.startsWith('left-');
      const facadeZ = isLeft ? b.z + b.depth / 2 + 0.06 : b.z - b.depth / 2 - 0.06;
      const normalZ = isLeft ? 1 : -1;
      const halfW = b.width / 2;

      const xs: number[] = [];
      for (let i = 0; i <= segX; i++) xs.push(b.x - halfW + (i / segX) * b.width);
      const ys: number[] = [];
      for (let j = 0; j <= segY; j++) ys.push((j / segY) * b.height);

      const grid: number[][] = [];
      let maxEv = 0;
      for (let j = 0; j <= segY; j++) {
        const row: number[] = [];
        for (let i = 0; i <= segX; i++) {
          const ev = computeEvAt(xs[i], facadeZ, poles, photometric, fluxScale, mf, ys[j], normalZ);
          row.push(ev);
          if (ev > maxEv) maxEv = ev;
        }
        grid.push(row);
      }
      if (maxEv < 0.5) continue;

      const levels = autoLevels(maxEv);
      for (const level of levels) {
        marchingSquaresSegments(xs, ys, grid, level, facadeZ, normalZ, positions, colors, maxEv);
      }
    }

    if (positions.length === 0) return null;

    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    geo.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
    return geo;
  }, [rows, poles, photometric, fluxScale, mf]);

  if (!geometry) return null;

  return (
    <lineSegments geometry={geometry}>
      <lineBasicMaterial vertexColors transparent opacity={0.85} linewidth={1} />
    </lineSegments>
  );
}

function Buildings({
  rows,
  poles,
  photometric,
  fluxScale,
  mf,
  onFacadeClick,
  scaleMin,
  scaleMax,
  cct = 4000,
  isNight = false,
  unit = 'lux' as PhotometricDisplayUnit,
}: {
  rows: ReturnType<typeof buildBuildingRows>;
  poles: PoleInfo[];
  photometric: Photometric | null;
  fluxScale: number;
  mf: number;
  onFacadeClick: (x: number, z: number, y: number) => void;
  scaleMin: number;
  scaleMax: number;
  cct?: number;
  isNight?: boolean;
  unit?: PhotometricDisplayUnit;
}) {
  const facadeGeometries = useMemo(() => {
    if (!photometric || poles.length === 0) return new Map<string, THREE.BufferGeometry>();
    const map = new Map<string, THREE.BufferGeometry>();
    for (const b of rows) {
      map.set(b.id, buildFacadeGeometry(b, poles, photometric, fluxScale, mf, scaleMin, scaleMax, cct, isNight, unit));
    }
    return map;
  }, [rows, poles, photometric, fluxScale, mf, scaleMin, scaleMax, cct, isNight, unit]);

  return (
    <group>
      {rows.map((b) => (
        <group key={b.id}>
          <mesh castShadow={b.asObstacles} receiveShadow position={[b.x, b.height / 2, b.z]}>
            <boxGeometry args={[b.width, b.height, b.depth]} />
            <meshStandardMaterial color="#334155" roughness={0.82} metalness={0.05} side={THREE.FrontSide} />
          </mesh>
          {photometric && poles.length > 0 && (
            <mesh
              geometry={facadeGeometries.get(b.id)}
              onClick={(e) => {
                e.stopPropagation();
                onFacadeClick(e.point.x, e.point.z, e.point.y);
              }}
            >
              <meshBasicMaterial vertexColors side={THREE.DoubleSide} />
            </mesh>
          )}
        </group>
      ))}
    </group>
  );
}

function Pole({
  pole,
  cfg,
  visualFactor,
  selected,
  onClick,
}: {
  pole: PoleInfo;
  cfg: SceneCfg;
  visualFactor: number;
  selected: boolean;
  onClick: (pole: PoleInfo) => void;
}) {
  const dz = pole.headZ - pole.baseZ;
  const dy = pole.headY - cfg.height;
  const armLen = Math.sqrt(dz * dz + dy * dy);
  const armAngleX = Math.atan2(dz, dy);
  const headTiltX = luminaireVisualTilt(pole);
  const poleColor = selected ? '#38bdf8' : COLORS.pole;
  const handleSelect = (e: ThreeEvent<PointerEvent> | ThreeEvent<MouseEvent>) => {
    e.stopPropagation();
    onClick(pole);
  };

  // Shared geometries — same across all poles in the scene
  const geo = useMemo(() => {
    const h = cfg.height;
    return {
      invisibleBox: cachedGeo(`pole-box-${h}`, () => new THREE.BoxGeometry(0.3, h + 1.2, 0.3)),
      poleCyl: cachedGeo(`pole-cyl-${h}`, () => new THREE.CylinderGeometry(0.06, 0.08, h, 16)),
      basePlate: cachedGeo('pole-base', () => new THREE.CylinderGeometry(0.18, 0.24, 0.1, 16)),
      joint: cachedGeo('pole-joint', () => new THREE.SphereGeometry(0.1, 12, 8)),
      armJoint: cachedGeo('pole-arm-joint', () => new THREE.SphereGeometry(0.07, 12, 8)),
      armCyl: cachedGeo(`arm-cyl-${armLen.toFixed(2)}`, () => new THREE.CylinderGeometry(0.04, 0.05, armLen, 12)),
      armBox: cachedGeo(`arm-box-${armLen.toFixed(2)}`, () => new THREE.BoxGeometry(0.8, Math.max(0.2, armLen + 0.4), 0.8)),
      headBody: cachedGeo('head-body', () => new THREE.BoxGeometry(0.42, 0.12, 0.22)),
      headGlass: cachedGeo('head-glass', () => new THREE.BoxGeometry(0.38, 0.03, 0.2)),
      headHitbox: cachedGeo('head-hitbox', () => new THREE.BoxGeometry(0.9, 0.45, 0.55)),
      selRing: cachedGeo('sel-ring', () => new THREE.CylinderGeometry(0.18, 0.18, h, 24, 1, true)),
    };
  }, [cfg.height, armLen]);

  const mat = useMemo(() => ({
    invisible: cachedMat('invisible', () => new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false })),
    pole: cachedMat(`pole-${selected}`, () => new THREE.MeshStandardMaterial({
      color: poleColor, metalness: 0.7, roughness: 0.4,
      emissive: selected ? '#0e7490' : '#000000', emissiveIntensity: selected ? 0.35 : 0,
    })),
    poleBase: cachedMat(`pole-base-${selected}`, () => new THREE.MeshStandardMaterial({
      color: poleColor, metalness: 0.5, roughness: 0.6,
      emissive: selected ? '#0e7490' : '#000000', emissiveIntensity: selected ? 0.25 : 0,
    })),
    arm: cachedMat(`arm-${selected}`, () => new THREE.MeshStandardMaterial({
      color: poleColor, metalness: 0.7, roughness: 0.4,
      emissive: selected ? '#0e7490' : '#000000', emissiveIntensity: selected ? 0.3 : 0,
    })),
    headBody: cachedMat('head-body', () => new THREE.MeshStandardMaterial({
      color: COLORS.headBody, metalness: 0.6, roughness: 0.4,
      emissive: '#fbbf24', emissiveIntensity: 0.6,
    })),
    headGlass: cachedMat('head-glass', () => new THREE.MeshStandardMaterial({
      color: COLORS.headGlass, metalness: 0.1, roughness: 0.1,
      emissive: '#0ea5e9', emissiveIntensity: 0.7, transparent: true, opacity: 0.75,
    })),
    selRing: cachedMat('sel-ring', () => new THREE.MeshBasicMaterial({
      color: '#22d3ee', transparent: true, opacity: 0.16, depthWrite: false, side: THREE.DoubleSide,
    })),
  }), [selected, poleColor]);

  return (
    <group
      onClick={handleSelect}
      onPointerDown={handleSelect}
    >
      <mesh position={[pole.baseX, cfg.height / 2, pole.baseZ]} geometry={geo.invisibleBox} material={mat.invisible} onPointerDown={handleSelect} onClick={handleSelect} />
      <mesh castShadow position={[pole.baseX, cfg.height / 2, pole.baseZ]} geometry={geo.poleCyl} material={mat.pole} onPointerDown={handleSelect} onClick={handleSelect} />
      <mesh castShadow position={[pole.baseX, 0.05, pole.baseZ]} geometry={geo.basePlate} material={mat.poleBase} onPointerDown={handleSelect} onClick={handleSelect} />
      <mesh castShadow position={[pole.baseX, cfg.height, pole.baseZ]} geometry={geo.joint} material={mat.pole} onPointerDown={handleSelect} onClick={handleSelect} />
      <group position={[pole.baseX, cfg.height, pole.baseZ]} rotation={[armAngleX, 0, 0]}>
        <mesh position={[0, armLen / 2, 0]} geometry={geo.armBox} material={mat.invisible} onPointerDown={handleSelect} onClick={handleSelect} />
        <mesh castShadow position={[0, armLen / 2, 0]} geometry={geo.armCyl} material={mat.arm} onPointerDown={handleSelect} onClick={handleSelect} />
        <mesh castShadow position={[0, armLen, 0]} geometry={geo.armJoint} material={mat.arm} onPointerDown={handleSelect} onClick={handleSelect} />
        <group position={[0, armLen, 0]} rotation={[headTiltX, 0, 0]} scale={[visualFactor, Math.sqrt(visualFactor), visualFactor]}>
          <mesh castShadow position={[0, -0.06, 0]} geometry={geo.headBody} material={mat.headBody} onPointerDown={handleSelect} onClick={handleSelect} />
          <mesh castShadow position={[0, -0.14, 0]} geometry={geo.headGlass} material={mat.headGlass} onPointerDown={handleSelect} onClick={handleSelect} />
          <mesh position={[0, -0.08, 0]} geometry={geo.headHitbox} material={mat.invisible} onPointerDown={handleSelect} onClick={handleSelect} />
        </group>
      </group>
      {selected && (
        <mesh position={[pole.baseX, cfg.height / 2, pole.baseZ]} geometry={geo.selRing} material={mat.selRing} />
      )}
    </group>
  );
}

function PoleConfigPopup({
  pole,
  cfg,
  onClose,
}: {
  pole: PoleInfo;
  cfg: SceneCfg;
  onClose: () => void;
}) {
  const luminaireHeight = cfg.height + cfg.arm_length * Math.sin((cfg.tilt * Math.PI) / 180);
  const sideLabel = pole.baseZ < cfg.road_width / 2 ? 'izquierda' : pole.baseZ > cfg.road_width / 2 ? 'derecha' : 'central';

  return (
    <Html
      position={[pole.baseX, pole.headY + 1.25, pole.baseZ]}
      center
      distanceFactor={12}
      style={{ pointerEvents: 'auto' }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-[210px] rounded-lg border border-cyan-400/50 bg-slate-950/92 p-3 text-[11px] text-slate-100 shadow-2xl shadow-cyan-950/70 backdrop-blur"
      >
        <div className="mb-2 flex items-center justify-between gap-2 border-b border-slate-700/70 pb-2">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-cyan-300">Poste</div>
            <div className="text-[10px] text-slate-400">lado {sideLabel}</div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-[10px] font-bold text-slate-300 hover:border-cyan-400 hover:text-cyan-100"
          >
            x
          </button>
        </div>
        <div className="grid grid-cols-2 gap-1.5 font-mono">
          <span className="text-slate-400">h</span>
          <span className="text-right font-bold text-white">{cfg.height.toFixed(2)} m</span>
          <span className="text-slate-400">R</span>
          <span className="text-right font-bold text-white">{cfg.pole_offset.toFixed(2)} m</span>
          <span className="text-slate-400">B</span>
          <span className="text-right font-bold text-white">{cfg.arm_length.toFixed(2)} m</span>
          <span className="text-slate-400">alpha</span>
          <span className="text-right font-bold text-white">{cfg.tilt.toFixed(0)} deg</span>
          <span className="text-slate-400">h lum</span>
          <span className="text-right font-bold text-cyan-200">{luminaireHeight.toFixed(2)} m</span>
          <span className="text-slate-400">S</span>
          <span className="text-right font-bold text-white">{cfg.spacing.toFixed(1)} m</span>
        </div>
      </div>
    </Html>
  );
}

function PhotometricSolid({ pole, p, scale = 0.5, visualFactor = 1, nightBoost = 1, cct = 4000, showPointLight = true }: { pole: PoleInfo; p: Photometric; scale?: number; visualFactor?: number; nightBoost?: number; cct?: number; showPointLight?: boolean }) {
  const geometry = useMemo(() => cachedPhotometricGeo(
    p,
    `${scale}-${visualFactor}-${cct}-${nightBoost > 1}`,
    () => {
    const Mc = p.Mc;
    const Ng = p.Ng;
    const geom = new THREE.BufferGeometry();
    const positions: number[] = [];
    const colors: number[] = [];
    const indices: number[] = [];
    const maxI = Math.max(1e-6, ...p.intensity.flat());
    const driverMode = nightBoost > 1;
    const cc = driverMode ? new THREE.Color(cctToColor(cct)) : null;

    for (let ci = 0; ci < Mc; ci++) {
      for (let gi = 0; gi < Ng; gi++) {
        const c = (p.c[ci] * Math.PI) / 180;
        const g = (p.gamma[gi] * Math.PI) / 180;
        const I = p.intensity[ci][gi] / maxI;
        const r = scale * visualFactor * (0.05 + I * 1.4);
        const x = r * Math.sin(g) * Math.cos(c);
        const z = r * Math.sin(g) * Math.sin(c);
        const y = -r * Math.cos(g);
        positions.push(x, y, z);
        const fade = Math.min(1, Math.max(0, 0.2 + I * 0.6));
        if (driverMode && cc) {
          colors.push(cc.r * fade, cc.g * fade, cc.b * fade);
        } else {
          const gc = sampleGradientColor(fade);
          colors.push(gc.r, gc.g, gc.b);
        }
      }
    }
    for (let ci = 0; ci < Mc; ci++) {
      const c1 = (ci + 1) % Mc;
      for (let gi = 0; gi < Ng - 1; gi++) {
        const a = ci * Ng + gi;
        const b = c1 * Ng + gi;
        const cc = c1 * Ng + (gi + 1);
        const d = ci * Ng + (gi + 1);
        indices.push(a, b, cc, a, cc, d);
      }
    }
    geom.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
    geom.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
    geom.setIndex(indices);
    geom.computeVertexNormals();
      return geom;
    },
  ), [p, scale, visualFactor, cct, nightBoost]);

  return (
    <group position={[pole.headX, pole.headY, pole.headZ]} rotation={[0, pole.sideSign < 0 ? Math.PI : 0, 0]}>
      <group rotation={[luminaireVisualTilt(pole), 0, 0]}>
        <mesh geometry={geometry}>
          <meshStandardMaterial
            vertexColors
            transparent
            opacity={0.18}
            side={THREE.DoubleSide}
            depthWrite={false}
            emissive={nightBoost > 1 ? cctToColor(cct) : '#facc15'}
            emissiveIntensity={0.4}
          />
        </mesh>
        {showPointLight && (
          <pointLight
            intensity={Math.min(5, p.flux * 0.0025 * visualFactor) * nightBoost}
            distance={nightBoost > 1 ? 24 : Math.min(24, p.flux * 0.01 * visualFactor)}
            decay={2.5}
            color={cctToColor(cct)}
            position={[0, -0.05, 0]}
          />
        )}
      </group>
    </group>
  );
}

function IsoluxVisualization({
  poles,
  p,
  cfg,
  unit,
}: {
  poles: PoleInfo[];
  p: Photometric;
  cfg: SceneCfg;
  unit: PhotometricDisplayUnit;
}) {
  const data = useMemo(() => {
    const fluxScale = p.power > 0 ? cfg.power / p.power : 1.0;
    const mf = effectiveMf(cfg.mf, p);
    const W = cfg.road_width;
    const sl = cfg.sidewalk_left;
    const sr = cfg.sidewalk_right;
    const length = Math.max(cfg.spacing * Math.max(1, cfg.pole_count - 1) * 1.2, 30);
    const nx = 120;
    const nz = 40;
    const dx = length / nx;
    const dz = (W + sl + sr) / nz;
    const x0 = -length / 2;
    const z0 = -sl;

    const fieldFlat = new Float64Array(nx * nz);
    let sum = 0;
    let minPositive = Infinity;
    let maxValue = -Infinity;
    for (let i = 0; i < nx; i++) {
      const px = x0 + (i + 0.5) * dx;
      const rowBase = i * nz;
      for (let j = 0; j < nz; j++) {
        const pz = z0 + (j + 0.5) * dz;
        const e = unit === 'lux'
          ? computeEAt(px, pz, poles, p, fluxScale, mf)
          : computeCdAt(px, pz, poles, p, fluxScale, mf, undefined, W / 2);
        fieldFlat[rowBase + j] = e;
        sum += e;
        if (e > maxValue) maxValue = e;
        if (e > 0 && e < minPositive) minPositive = e;
      }
    }

    const scale = resolveVisualizationScale(
      'manual',
      cfg.illuminance_scale_min,
      cfg.illuminance_scale_max,
      Array.from(fieldFlat),
    );

    const total = nx * nz;
    const samplesArr = new Float32Array(total * 3);
    const positionsArr = new Float32Array(total * 3);
    const colorsArr = new Float32Array(total * 3);
    const indicesArr = new Uint16Array((nx - 1) * (nz - 1) * 6);
    const maxE = Math.max(1, maxValue);
    let maxX = 0;
    let maxZ = 0;
    let idx = 0;

    for (let i = 0; i < nx; i++) {
      const sx = x0 + (i + 0.5) * dx;
      for (let j = 0; j < nz; j++) {
        const e = fieldFlat[i * nz + j];
        const t = normalizeByScale(e, scale);
        const color = sampleGradientColor(t);
        const sz = z0 + (j + 0.5) * dz;
        const b3 = idx * 3;
        samplesArr[b3] = sx; samplesArr[b3 + 1] = 0.02; samplesArr[b3 + 2] = sz;
        positionsArr[b3] = sx; positionsArr[b3 + 1] = 0.01; positionsArr[b3 + 2] = sz;
        colorsArr[b3] = color.r; colorsArr[b3 + 1] = color.g; colorsArr[b3 + 2] = color.b;
        if (e > 0 && e >= maxE * 0.999) { maxX = sx; maxZ = sz; }
        idx++;
      }
    }

    let ii = 0;
    for (let i = 0; i < nx - 1; i++) {
      for (let j = 0; j < nz - 1; j++) {
        const a = i * nz + j;
        const b = i * nz + (j + 1);
        const c = (i + 1) * nz + j;
        const d = (i + 1) * nz + (j + 1);
        indicesArr[ii] = a; indicesArr[ii + 1] = b; indicesArr[ii + 2] = c;
        indicesArr[ii + 3] = b; indicesArr[ii + 4] = d; indicesArr[ii + 5] = c;
        ii += 6;
      }
    }

    return {
      samplesArr, positionsArr, colorsArr, indicesArr,
      maxE, maxX, maxZ,
      avgE: total > 0 ? sum / total : 0,
      minE: Number.isFinite(minPositive) ? minPositive : 0,
      length, W, sr, fluxScale, mf,
    };
  }, [poles, p, cfg, unit]);

  const geomPoints = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(data.samplesArr, 3));
    g.setAttribute('color', new THREE.BufferAttribute(data.colorsArr, 3));
    return g;
  }, [data]);

  const geomMesh = useMemo(() => {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(data.positionsArr, 3));
    g.setAttribute('color', new THREE.Float32BufferAttribute(data.colorsArr, 3));
    g.setIndex(new THREE.BufferAttribute(data.indicesArr, 1));
    g.computeVertexNormals();
    return g;
  }, [data]);

  return (
    <group>
      <points geometry={geomPoints}>
        <pointsMaterial vertexColors size={0.22} sizeAttenuation transparent opacity={0.95} depthWrite={false} />
      </points>
      <mesh geometry={geomMesh}>
        <meshBasicMaterial vertexColors transparent opacity={0.35} depthWrite={false} side={THREE.DoubleSide} />
      </mesh>
      <Html position={[data.maxX, 0.35, data.maxZ]} center style={{ pointerEvents: 'none' }} distanceFactor={10}>
        <div className="text-[10px] text-amber-200 font-mono px-1.5 py-0.5 rounded bg-amber-500/15 border border-amber-400/40 whitespace-pre shadow-lg shadow-amber-500/20">
{`${unit === 'lux' ? 'E' : 'L'} max = ${data.maxE.toFixed(1)} ${unitSuffix(unit)}`}
        </div>
      </Html>
      <Html position={[-data.length / 2 + 0.5, 0.35, data.W / 2]} style={{ pointerEvents: 'none' }} distanceFactor={10}>
        <div className="text-[9px] text-sky-300/90 font-mono px-1.5 py-0.5 rounded bg-slate-900/80 border border-sky-400/30 whitespace-pre">
{`${unit === 'lux' ? 'E' : 'L'} edge = ${computeDisplayAt(-data.length / 2 + 0.5, data.W / 2, poles, p, unit, data.fluxScale, data.mf).toFixed(1)} ${unitSuffix(unit)}`}
        </div>
      </Html>
      <Html position={[0, 0.35, data.W + data.sr + 0.4]} center style={{ pointerEvents: 'none' }} distanceFactor={10}>
        <div className="text-[9px] text-emerald-300/90 font-mono px-1.5 py-0.5 rounded bg-slate-900/80 border border-emerald-400/30 whitespace-pre">
{`${unit === 'lux' ? 'E' : 'L'} avg = ${data.avgE.toFixed(1)} ${unitSuffix(unit)}`}
        </div>
      </Html>
    </group>
  );
}

function Probe({
  point,
  value,
  cfg,
  unit,
  onClear,
  y,
  eValue,
  cdValue,
}: {
  point: { x: number; z: number };
  value: number;
  cfg: SceneCfg;
  unit: PhotometricDisplayUnit;
  onClear: () => void;
  y?: number;
  eValue?: number;
  cdValue?: number;
}) {
  const ringRef = useRef<THREE.Mesh>(null);
  const { x, z } = point;
  const isFacade = y !== undefined;
  const armLen = 1.0;
  const W = cfg.road_width;
  const roadCenter = W / 2;
  const armDirZ = z < roadCenter ? 1 : -1;
  const armZ = z + armDirZ * armLen;

  const frameCountRef = useRef(0);
  useFrame(({ clock }) => {
    frameCountRef.current += 1;
    if (frameCountRef.current % 2 !== 0) return; // throttle to ~30fps
    if (!ringRef.current) return;
    const s = 1 + Math.sin(clock.elapsedTime * 4) * 0.18;
    ringRef.current.scale.set(s, s, s);
    const mat = ringRef.current.material as THREE.MeshBasicMaterial;
    mat.opacity = 0.7 + Math.sin(clock.elapsedTime * 4) * 0.25;
  });

  return (
    <group>
      {isFacade ? (
        <>
          <mesh ref={ringRef} rotation={[-Math.PI / 2, 0, 0]} position={[x, y, z]}>
            <ringGeometry args={[0.28, 0.36, 36]} />
            <meshBasicMaterial color={COLORS.probe} transparent depthWrite={false} side={THREE.DoubleSide} />
          </mesh>
          <mesh rotation={[-Math.PI / 2, 0, 0]} position={[x, y, z]}>
            <circleGeometry args={[0.08, 24]} />
            <meshBasicMaterial color={COLORS.probe} transparent opacity={0.9} depthWrite={false} />
          </mesh>
          <mesh position={[x, y, (z + armZ) / 2]} rotation={[Math.PI / 2, 0, 0]}>
            <cylinderGeometry args={[0.012, 0.012, armLen, 8]} />
            <meshBasicMaterial color={COLORS.probe} transparent opacity={0.85} depthWrite={false} />
          </mesh>
          <mesh position={[x, y, armZ]}>
            <sphereGeometry args={[0.06, 16, 12]} />
            <meshBasicMaterial color={COLORS.probe} />
          </mesh>
          <Html position={[x, y + 0.25, armZ]} center style={{ pointerEvents: 'auto' }} distanceFactor={10}>
            <div
              onClick={onClear}
              className="text-lg font-bold font-mono px-4 py-3 rounded-md bg-black/90 border-2 border-cyan-400 text-cyan-200 shadow-lg shadow-cyan-500/50 cursor-pointer whitespace-pre select-none leading-relaxed"
            >
{`* Ev = ${value.toFixed(2)} lux
x = ${x >= 0 ? '+' : ''}${x.toFixed(2)} m
z = ${z.toFixed(2)} m
y = ${y.toFixed(2)} m`}
            </div>
          </Html>
        </>
      ) : (
        <>
          <mesh ref={ringRef} rotation={[-Math.PI / 2, 0, 0]} position={[x, 0.03, z]}>
            <ringGeometry args={[0.28, 0.36, 36]} />
            <meshBasicMaterial color={COLORS.probe} transparent depthWrite={false} side={THREE.DoubleSide} />
          </mesh>
          <mesh rotation={[-Math.PI / 2, 0, 0]} position={[x, 0.025, z]}>
            <circleGeometry args={[0.08, 24]} />
            <meshBasicMaterial color={COLORS.probe} transparent opacity={0.9} depthWrite={false} />
          </mesh>
          <mesh position={[x, 2.85, z]}>
            <cylinderGeometry args={[0.012, 0.012, 5.7, 8]} />
            <meshBasicMaterial color={COLORS.probe} transparent opacity={0.85} depthWrite={false} />
          </mesh>
          <mesh position={[x, 5.7, z]}>
            <sphereGeometry args={[0.06, 16, 12]} />
            <meshBasicMaterial color={COLORS.probe} />
          </mesh>
          <Html position={[x, 5.95, z]} center style={{ pointerEvents: 'auto' }} distanceFactor={10}>
            <div
              onClick={onClear}
              className="text-lg font-bold font-mono px-4 py-3 rounded-md bg-black/90 border-2 border-cyan-400 text-cyan-200 shadow-lg shadow-cyan-500/50 cursor-pointer whitespace-pre select-none leading-relaxed"
            >
{`* E = ${(eValue ?? value).toFixed(2)} lx
* L = ${(cdValue ?? value).toFixed(2)} cd/m²
x = ${x >= 0 ? '+' : ''}${x.toFixed(2)} m
z = ${z.toFixed(2)} m
z − front = ${z.toFixed(2)} m
back − z = ${(W - z).toFixed(2)} m
|center − z| = ${Math.abs(z - W / 2).toFixed(2)} m
nearest pole = ${(() => {
  let best = Infinity;
  for (const sign of [-1, 0, 1]) {
    const d = Math.abs(x - sign * cfg.spacing);
    if (d < best) best = d;
  }
  return best.toFixed(2);
})()} m`}
            </div>
          </Html>
        </>
      )}
    </group>
  );
}

function DriverRoadLuminance({
  poles,
  p,
  cfg,
  poleCount,
}: {
  poles: PoleInfo[];
  p: Photometric;
  cfg: SceneCfg;
  poleCount: number;
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  const { camera } = useThree();
  const workerRef = useRef<Worker | null>(null);
  const pendingRef = useRef(false);
  const generationRef = useRef(0);
  const requestIdRef = useRef(0);
  const lastRequestedXRef = useRef(-Infinity);
  const cctColor = useMemo(() => new THREE.Color(cctToColor(cfg.cct)), [cfg.cct]);

  const data = useMemo(() => {
    const fluxScale = p.power > 0 ? cfg.power / p.power : 1.0;
    const mf = effectiveMf(cfg.mf, p);
    const W = cfg.road_width;
    const sl = cfg.sidewalk_left;
    const sr = cfg.sidewalk_right;
    const width = W + sl + sr;
    const length = Math.max(140, cfg.spacing * 8);
    const canvas = document.createElement('canvas');
    canvas.width = 192;
    canvas.height = 48;
    const ctx = canvas.getContext('2d')!;
    const image = ctx.createImageData(canvas.width, canvas.height);
    const texture = new THREE.CanvasTexture(canvas);
    texture.wrapS = texture.wrapT = THREE.ClampToEdgeWrapping;
    texture.minFilter = THREE.LinearFilter;
    texture.magFilter = THREE.LinearFilter;
    texture.colorSpace = THREE.SRGBColorSpace;
    return { canvas, ctx, image, texture, length, width, z0: -sl, fluxScale, mf };
  }, [p, cfg]);

  useEffect(() => {
    const generation = ++generationRef.current;
    const worker = new Worker(new URL('../../workers/driverLuminance.worker.ts', import.meta.url), { type: 'module' });
    workerRef.current = worker;
    pendingRef.current = false;
    lastRequestedXRef.current = -Infinity;
    worker.onmessage = (event: MessageEvent<{
      type: 'frame';
      generation: number;
      requestId: number;
      xStart: number;
      pixels: ArrayBuffer;
    }>) => {
      if (event.data.type !== 'frame' || event.data.generation !== generation) return;
      pendingRef.current = false;
      data.image.data.set(new Uint8ClampedArray(event.data.pixels));
      data.ctx.putImageData(data.image, 0, 0);
      data.texture.needsUpdate = true;
      meshRef.current?.position.set(event.data.xStart + data.length / 2, 0.02, data.z0 + data.width / 2);
    };
    worker.onerror = () => {
      pendingRef.current = false;
    };
    worker.postMessage({
      type: 'init',
      generation,
      setup: {
        poles,
        photometric: p,
        fluxScale: data.fluxScale,
        mf: data.mf,
        spacing: Math.max(1, cfg.spacing),
        poleCount,
        textureWidth: data.canvas.width,
        textureHeight: data.canvas.height,
        worldLength: data.length,
        worldWidth: data.width,
        z0: data.z0,
        color: [cctColor.r, cctColor.g, cctColor.b],
      },
    });
    return () => {
      worker.terminate();
      if (workerRef.current === worker) workerRef.current = null;
    };
  }, [cctColor, cfg.spacing, data, p, poleCount, poles]);

  useEffect(() => () => data.texture.dispose(), [data]);

  useFrame(() => {
    const worker = workerRef.current;
    if (!meshRef.current || !worker || pendingRef.current) return;
    const cameraX = camera.position.x;
    if (Math.abs(cameraX - lastRequestedXRef.current) < 0.25) return;
    lastRequestedXRef.current = cameraX;
    pendingRef.current = true;
    worker.postMessage({
      type: 'render',
      generation: generationRef.current,
      requestId: ++requestIdRef.current,
      cameraX,
      cameraZ: camera.position.z,
    });
  });

  return (
    <mesh ref={meshRef} rotation={[-Math.PI / 2, 0, 0]} renderOrder={10}>
      <planeGeometry args={[data.length, data.width]} />
      <meshBasicMaterial map={data.texture} depthWrite={false} transparent opacity={0.72} blending={THREE.AdditiveBlending} />
    </mesh>
  );
}

function OrbitCameraManager({
  viewMode,
  savedStateRef,
}: {
  viewMode: 'orbit' | 'driver';
  savedStateRef: React.MutableRefObject<{ pos: THREE.Vector3Tuple; target: THREE.Vector3Tuple } | null>;
}) {
  const { camera } = useThree();
  const controlsRef = useRef<any>(null);
  const prevMode = useRef(viewMode);

  useEffect(() => {
    const prev = prevMode.current;
    prevMode.current = viewMode;

    if (prev === 'orbit' && viewMode === 'driver' && controlsRef.current) {
      savedStateRef.current = {
        pos: camera.position.toArray() as THREE.Vector3Tuple,
        target: controlsRef.current.target.toArray() as THREE.Vector3Tuple,
      };
    } else if (prev === 'driver' && viewMode === 'orbit' && savedStateRef.current) {
      camera.position.set(...savedStateRef.current.pos);
      if (camera instanceof THREE.PerspectiveCamera) {
        camera.fov = 45;
        camera.updateProjectionMatrix();
      }
      if (controlsRef.current) {
        controlsRef.current.target.set(...savedStateRef.current.target);
        controlsRef.current.update();
      }
    }
  }, [viewMode, camera, savedStateRef]);

  return (
    <OrbitControls
      ref={controlsRef}
      enableDamping
      dampingFactor={0.08}
      minDistance={5}
      maxDistance={60}
      maxPolarAngle={Math.PI / 2 - 0.05}
      target={[0, 3, 0]}
      enabled={viewMode === 'orbit'}
    />
  );
}

function Scene({
  photometric,
  probe,
  onGroundClick,
  onClearProbe,
  fluxScale,
  mf,
  onFacadeClick,
  selectedPoleId,
  onSelectPole,
  rows,
  viewMode,
  poles,
  visualFactor,
  poleCount = 3,
}: {
  photometric: Photometric | null;
  probe: { x: number; z: number; value: number; y?: number; eValue?: number; cdValue?: number } | null;
  onGroundClick: (e: ThreeEvent<MouseEvent>) => void;
  onClearProbe: () => void;
  fluxScale: number;
  mf: number;
  onFacadeClick: (x: number, z: number, y: number) => void;
  selectedPoleId: number | null;
  onSelectPole: (pole: PoleInfo) => void;
  rows: ReturnType<typeof buildBuildingRows>;
  viewMode?: 'orbit' | 'driver';
  poles: PoleInfo[];
  visualFactor: number;
  poleCount?: number;
}) {
  const cfg = useSceneCfg();
  const { camera } = useThree();
  const poleGroupRef = useRef<THREE.Group>(null);
  const unit = cfg.photometric_display_unit;

  const isNight = viewMode === 'driver';
  const roadCfg = isNight ? { ...cfg, pole_count: poleCount } : cfg;

  useFrame(() => {
    if (!poleGroupRef.current) return;
    if (!isNight) {
      poleGroupRef.current.position.x = 0;
      return;
    }
    const span = Math.max(1, cfg.spacing * Math.max(1, poleCount));
    poleGroupRef.current.position.x = Math.round(camera.position.x / span) * span;
  });

  return (
    <>
      <color attach="background" args={[isNight ? '#020308' : '#05070d']} />
      <fog attach="fog" args={['#05070d', isNight ? 55 : 35, isNight ? 150 : 120]} />
      <Stars radius={120} depth={50} count={2500} factor={4} saturation={0.2} fade speed={0.6} />
      <hemisphereLight args={['#3b4a6b', '#0a0e1a', isNight ? 0.08 : 0.35]} />
      <ambientLight intensity={isNight ? 0.035 : 0.15} />
      <directionalLight
        position={[15, 30, 10]}
        intensity={isNight ? 0.012 : 0.4}
        castShadow={!isNight}
        shadow-mapSize-width={1024}
        shadow-mapSize-height={1024}
        shadow-camera-far={80}
        shadow-camera-left={-30}
        shadow-camera-right={30}
        shadow-camera-top={30}
        shadow-camera-bottom={-30}
      />
      <Road cfg={roadCfg} onGroundClick={onGroundClick} followCamera={isNight} />
      <Grid
        args={[80, 80]}
        position={[0, -0.005, cfg.road_width / 2]}
        cellSize={1}
        cellThickness={0.5}
        cellColor={isNight ? '#0a0e1a' : '#1e293b'}
        sectionSize={5}
        sectionThickness={1}
        sectionColor={isNight ? '#111827' : '#334155'}
        fadeDistance={isNight ? 20 : 50}
        fadeStrength={isNight ? 2 : 1.5}
        infiniteGrid
      />
      <Html
        position={[cfg.spacing / 2, 0.05, -cfg.sidewalk_left - 0.3]}
        center
        style={{ pointerEvents: 'none' }}
        distanceFactor={14}
        transform={false}
      >
        <div className="text-[10px] text-slate-300 font-mono px-1.5 py-0.5 rounded bg-slate-900/60 border border-slate-700/50 whitespace-pre">
{`S = ${cfg.spacing.toFixed(1)} m`}
        </div>
      </Html>
      <group ref={poleGroupRef}>
        {poles.map((pole) => (
          <Pole
            key={pole.id}
            pole={pole}
            cfg={cfg}
            visualFactor={visualFactor}
            selected={pole.id === selectedPoleId}
            onClick={onSelectPole}
          />
        ))}
        {photometric &&
          poles.map((pole) => (
            <PhotometricSolid key={`sol-${pole.id}`} pole={pole} p={photometric} scale={0.65} visualFactor={visualFactor} nightBoost={isNight ? 4 : 1} cct={cfg.cct} showPointLight={!isNight} />
          ))}
        {cfg.generate_buildings && <Buildings rows={rows} poles={poles} photometric={photometric} fluxScale={fluxScale} mf={mf} onFacadeClick={onFacadeClick} scaleMin={cfg.illuminance_scale_min} scaleMax={cfg.illuminance_scale_max} cct={cfg.cct} isNight={isNight} unit={unit} />}
      </group>
      {photometric && poles.length > 0 && !isNight && <IsoluxVisualization poles={poles} p={photometric} cfg={cfg} unit={unit} />}
      {photometric && poles.length > 0 && isNight && <DriverRoadLuminance poles={poles} p={photometric} cfg={cfg} poleCount={poleCount} />}
      {probe && (
        <Probe point={{ x: probe.x, z: probe.z }} value={probe.value} cfg={cfg} unit={unit} onClear={onClearProbe} y={probe.y} eValue={probe.eValue} cdValue={probe.cdValue} />
      )}
      {!isNight && (
        <ContactShadows
          position={[0, 0.025, cfg.road_width / 2]}
          opacity={0.5}
          scale={80}
          blur={2.5}
          far={20}
          resolution={512}
          frames={1}
        />
      )}
      {!isNight && (
        <EffectComposer multisampling={0}>
          <Bloom
            intensity={0.6}
            luminanceThreshold={0.55}
            luminanceSmoothing={0.25}
            mipmapBlur
            radius={0.7}
          />
          <Vignette eskil={false} offset={0.2} darkness={0.6} />
        </EffectComposer>
      )}
    </>
  );
}

export default function RoadScene3D({
  onClose,
  variant = 'modal',
  viewMode = 'orbit',
  speedKmh = 60,
  carCount = 0,
  onViewModeChange,
  onSpeedChange,
}: {
  onClose: () => void;
  variant?: 'modal' | 'inline';
  viewMode?: 'orbit' | 'driver';
  speedKmh?: number;
  carCount?: number;
  onViewModeChange?: (mode: 'orbit' | 'driver') => void;
  onSpeedChange?: (v: number) => void;
}) {
  const ldtId = useConfigStore((s) => s.ldt_id);
  const cfg = useSceneCfg();
  const setIlluminanceScaleMin = useConfigStore((s) => s.setIlluminanceScaleMin);
  const setIlluminanceScaleMax = useConfigStore((s) => s.setIlluminanceScaleMax);
  const setPhotometricDisplayUnit = useConfigStore((s) => s.setPhotometricDisplayUnit);
  const setGenerateBuildings = useConfigStore((s) => s.setGenerateBuildings);
  const setBuildingHeight = useConfigStore((s) => s.setBuildingHeight);
  const setBuildingsAsObstacles = useConfigStore((s) => s.setBuildingsAsObstacles);
  const setPoleCount = useConfigStore((s) => s.setPoleCount);
  const {
    illuminance_scale_min,
    illuminance_scale_max,
    photometric_display_unit,
    generate_buildings,
    building_height,
    buildings_as_obstacles,
  } = cfg;
  const [photometric, setPhotometric] = useState<Photometric | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [probePos, setProbePos] = useState<{ x: number; z: number; y?: number; normalZ?: number } | null>(null);
  const [selectedPoleId, setSelectedPoleId] = useState<number | null>(null);
  const [sceneBrightness, setSceneBrightness] = useState(1.0);
  const [driverLaneIndex, setDriverLaneIndex] = useState(0);
  const pointerDownPos = useRef<{ x: number; y: number } | null>(null);
  const wasDrag = useRef(false);
  const scaleInitialized = useRef(false);
  const savedOrbitCamera = useRef<{ pos: THREE.Vector3Tuple; target: THREE.Vector3Tuple } | null>(null);

  useEffect(() => {
    const onPointerDown = (e: PointerEvent) => {
      pointerDownPos.current = { x: e.clientX, y: e.clientY };
      wasDrag.current = false;
    };
    const onPointerMove = (e: PointerEvent) => {
      if (!pointerDownPos.current) return;
      const dx = e.clientX - pointerDownPos.current.x;
      const dy = e.clientY - pointerDownPos.current.y;
      if (Math.sqrt(dx * dx + dy * dy) > 5) {
        wasDrag.current = true;
      }
    };
    const onPointerUp = () => {
      pointerDownPos.current = null;
    };
    window.addEventListener('pointerdown', onPointerDown);
    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', onPointerUp);
    return () => {
      window.removeEventListener('pointerdown', onPointerDown);
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', onPointerUp);
    };
  }, []);

  useEffect(() => {
    if (!ldtId) {
      setError('Select a luminaire to view the 3D scene.');
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    fetch(`/api/ldt/${ldtId}/photometric`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data: Photometric) => {
        setPhotometric(data);
        setLoading(false);
      })
      .catch((e) => {
        setError(String(e));
        setLoading(false);
      });
  }, [ldtId]);

  const deferredCfg = useDeferredValue(cfg);
  const driverPoleCount = useMemo(
    () => Math.max(deferredCfg.pole_count, driverPoleCountForSpacing(deferredCfg.spacing)),
    [deferredCfg.pole_count, deferredCfg.spacing],
  );
  const poles = useMemo(() => {
    if (viewMode === 'driver') {
      return buildPoles({ ...deferredCfg, pole_count: driverPoleCount });
    }
    return buildPoles(deferredCfg);
  }, [deferredCfg, driverPoleCount, viewMode]);
  const rows = useMemo(() => {
    if (!deferredCfg.generate_buildings) return [];
    const rowCfg = viewMode === 'driver' ? { ...deferredCfg, pole_count: driverPoleCount } : deferredCfg;
    return buildBuildingRows(rowCfg, deferredCfg.buildings_as_obstacles);
  }, [deferredCfg, driverPoleCount, viewMode]);

  const fluxScale = photometric && photometric.power > 0 ? cfg.power / photometric.power : 1.0;
  const visualFactor = powerVisualFactor(cfg.power);
  const mf = effectiveMf(cfg.mf, photometric);

  const fieldStats = useMemo(() => {
    if (viewMode === 'driver' || !photometric || poles.length === 0) return null;
    return computeDisplayStats(poles, photometric, cfg, photometric_display_unit, fluxScale, mf);
  }, [viewMode, photometric, poles, cfg, photometric_display_unit, fluxScale, mf]);

  const probe = useMemo(() => {
    if (!probePos || !photometric || poles.length === 0) return null;
    const { x, z, y, normalZ } = probePos;
    if (y !== undefined) {
      const value = computeEvAt(x, z, poles, photometric, fluxScale, mf, y, normalZ ?? 1);
      return { x, z, y, value };
    }
    const eValue = computeEAt(x, z, poles, photometric, fluxScale, mf);
    const cdValue = computeCdAt(x, z, poles, photometric, fluxScale, mf);
    return { x, z, value: photometric_display_unit === 'lux' ? eValue : cdValue, eValue, cdValue };
  }, [probePos?.x, probePos?.z, probePos?.y, probePos?.normalZ, poles, photometric, fluxScale, mf, photometric_display_unit]);

  useEffect(() => {
    if (fieldStats && !scaleInitialized.current) {
      setIlluminanceScaleMax(fieldStats.maxE);
      scaleInitialized.current = true;
    }
  }, [fieldStats]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleGroundClick = (e: ThreeEvent<MouseEvent>) => {
    if (viewMode === 'driver') return;
    e.stopPropagation();
    if (wasDrag.current) {
      wasDrag.current = false;
      return;
    }
    const x = e.point.x;
    const z = e.point.z;
    const nearestPole = poles.reduce<{ pole: PoleInfo | null; distance: number }>(
      (best, pole) => {
        const distance = Math.hypot(x - pole.baseX, z - pole.baseZ);
        return distance < best.distance ? { pole, distance } : best;
      },
      { pole: null, distance: Infinity },
    );

    if (nearestPole.pole && nearestPole.distance <= 0.3) {
      setSelectedPoleId(nearestPole.pole.id);
      return;
    }

    if (!photometric) return;
    setProbePos({ x, z });
  };

  const handleFacadeClick = (x: number, z: number, y: number) => {
    if (!photometric) return;
    const facadeIdx = rows.findIndex((b) => {
      const isLeft = b.id.startsWith('left-');
      const facadeZ = isLeft ? b.z + b.depth / 2 + 0.05 : b.z - b.depth / 2 - 0.05;
      return Math.abs(z - facadeZ) < 0.1 && x >= b.x - b.width / 2 && x <= b.x + b.width / 2 && y >= 0 && y <= b.height;
    });
    if (facadeIdx === -1) return;
    const b = rows[facadeIdx];
    setProbePos({ x, z, y, normalZ: b.id.startsWith('left-') ? 1 : -1 });
  };

  const handleClearProbe = () => setProbePos(null);
  const legendMax = illuminance_scale_max;
  const legendMin = 0;
  const selectedPole = poles.find((pole) => pole.id === selectedPoleId) ?? null;
  const selectedPoleSide =
    selectedPole && selectedPole.baseZ < cfg.road_width / 2
      ? 'izquierda'
      : selectedPole && selectedPole.baseZ > cfg.road_width / 2
        ? 'derecha'
        : 'central';
  const selectedLuminaireHeight = cfg.height + cfg.arm_length * Math.sin((cfg.tilt * Math.PI) / 180);

  return (
    <div
      className={
        variant === 'modal'
          ? 'fixed inset-0 z-50 bg-slate-950/95 backdrop-blur-sm flex flex-col'
          : 'h-full w-full bg-slate-950/95 flex flex-col'
      }
    >
      {variant === 'modal' && (
        <div className="flex items-center justify-between px-5 py-3 border-b border-slate-800/80 bg-gradient-to-r from-slate-900 to-slate-950">
          <div className="flex items-center gap-3">
            <div className="w-2 h-2 rounded-full bg-amber-400 shadow-[0_0_10px_2px_rgba(251,191,36,0.6)] animate-pulse" />
            <h2 className="text-slate-100 font-semibold text-sm tracking-wide">3D Road Preview</h2>
            {photometric && (
              <span className="text-[10px] font-mono text-slate-400 ml-2">
                {photometric.flux.toFixed(0)} lm · {photometric.power.toFixed(0)} W · {photometric.Mc}×{photometric.Ng}
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {onViewModeChange && (
              <button
                type="button"
                onClick={() => onViewModeChange(viewMode === 'orbit' ? 'driver' : 'orbit')}
                className={`text-[11px] px-3 py-1.5 rounded-md font-medium transition-all ${
                  viewMode === 'driver'
                    ? 'bg-amber-600 hover:bg-amber-700 text-white ring-1 ring-amber-400/50'
                    : 'bg-slate-700 hover:bg-slate-600 text-slate-200'
                }`}
              >
                {viewMode === 'driver' ? 'Driver ON' : 'Driver'}
              </button>
            )}
            <button
              onClick={onClose}
              className="text-[11px] px-3 py-1.5 rounded-md bg-[#1E1E1E] hover:bg-[#333333] text-white font-medium"
            >
              Close
            </button>
          </div>
        </div>
      )}
      <div className="flex-1 relative">
        {loading && (
          <div className="absolute inset-0 flex items-center justify-center text-slate-300 text-sm z-10">
            <div className="flex items-center gap-2">
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Loading photometric data...
            </div>
          </div>
        )}
        {error && (
          <div className="absolute inset-0 flex items-center justify-center text-red-300 text-sm z-10">
            {error}
          </div>
        )}
        <Canvas
          shadows
          dpr={[1, 1.5]}
          camera={{ position: [16, 10, 18], fov: 45, near: 0.1, far: 500 }}
          gl={{ antialias: true, toneMapping: THREE.ACESFilmicToneMapping, toneMappingExposure: sceneBrightness }}
        >
          <Scene
            photometric={photometric}
            probe={probe}
            onGroundClick={handleGroundClick}
            onClearProbe={handleClearProbe}
            fluxScale={fluxScale}
            mf={mf}
            onFacadeClick={handleFacadeClick}
            selectedPoleId={selectedPoleId}
            onSelectPole={(pole) => setSelectedPoleId(pole.id)}
            rows={rows}
            viewMode={viewMode}
            poles={poles}
            visualFactor={visualFactor}
            poleCount={viewMode === 'driver' ? driverPoleCount : cfg.pole_count}
          />
          <OrbitCameraManager viewMode={viewMode} savedStateRef={savedOrbitCamera} />
          <DriverView speedKmh={speedKmh} carCount={carCount} driverLaneIndex={driverLaneIndex} active={viewMode === 'driver'} />
        </Canvas>
        {selectedPole && viewMode !== 'driver' && (
          <div className="absolute right-3 top-3 z-20 w-[230px] rounded-lg border border-cyan-400/55 bg-slate-950/92 p-3 text-[11px] text-slate-100 shadow-2xl shadow-cyan-950/70 backdrop-blur">
            <div className="mb-2 flex items-start justify-between gap-2 border-b border-slate-700/70 pb-2">
              <div>
                <div className="text-[10px] font-bold uppercase tracking-[0.14em] text-cyan-300">Configuracion del poste</div>
                <div className="mt-0.5 text-[10px] text-slate-400">lado {selectedPoleSide}</div>
              </div>
              <button
                type="button"
                onClick={() => setSelectedPoleId(null)}
                className="rounded border border-slate-700 bg-slate-900 px-2 py-0.5 text-[10px] font-bold text-slate-300 hover:border-cyan-400 hover:text-cyan-100"
              >
                x
              </button>
            </div>
            <div className="grid grid-cols-2 gap-1.5 font-mono">
              <span className="text-slate-400">h</span>
              <span className="text-right font-bold text-white">{cfg.height.toFixed(2)} m</span>
              <span className="text-slate-400">R</span>
              <span className="text-right font-bold text-white">{cfg.pole_offset.toFixed(2)} m</span>
              <span className="text-slate-400">B</span>
              <span className="text-right font-bold text-white">{cfg.arm_length.toFixed(2)} m</span>
              <span className="text-slate-400">alpha</span>
              <span className="text-right font-bold text-white">{cfg.tilt.toFixed(0)} deg</span>
              <span className="text-slate-400">h lum</span>
              <span className="text-right font-bold text-cyan-200">{selectedLuminaireHeight.toFixed(2)} m</span>
              <span className="text-slate-400">S</span>
              <span className="text-right font-bold text-white">{cfg.spacing.toFixed(1)} m</span>
            </div>
          </div>
        )}
        {viewMode !== 'driver' && <div className="absolute top-3 left-3 max-w-[280px] rounded-md border border-slate-700/60 bg-slate-900/90 p-2 text-[10px] text-slate-200 shadow-xl">
            <div className="mt-0">
              <div className="flex items-center gap-2 mb-1">
                {fieldStats && (
                  <button
                    type="button"
                    onClick={() => {
                      setIlluminanceScaleMin(fieldStats.minE);
                      setIlluminanceScaleMax(fieldStats.maxE);
                    }}
                    className="flex-1 text-[11px] px-2 py-1 rounded bg-slate-700 hover:bg-slate-600 text-slate-200 font-semibold text-center"
                  >
                    autoescala
                  </button>
                )}
              </div>
              <div className="relative h-3 flex items-center mb-1.5">
                <div className="absolute inset-x-0 h-1.5 rounded-full bg-slate-700" />
                <div
                  className="absolute h-1.5 rounded-full"
                  style={{
                    left: `${(Math.min(100, Math.max(0, illuminance_scale_min)) / 100) * 100}%`,
                    width: `${Math.max(0, (Math.min(100, Math.max(0, illuminance_scale_max)) - Math.min(100, Math.max(0, illuminance_scale_min))) / 100 * 100)}%`,
                    background: 'linear-gradient(to right, #f59e0b, #3b82f6)',
                  }}
                />
                <input
                  type="range"
                  min={0}
                  max={100}
                  step={0.5}
                  value={Math.min(100, Math.max(0, illuminance_scale_min))}
                  onChange={(e) => {
                    const val = Number(e.target.value);
                    setIlluminanceScaleMin(Math.min(val, illuminance_scale_max));
                  }}
                  className="absolute inset-0 w-full h-full appearance-none bg-transparent pointer-events-none [&::-webkit-slider-thumb]:pointer-events-auto [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:h-3.5 [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-amber-500 [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-slate-900 [&::-webkit-slider-thumb]:shadow-md [&::-webkit-slider-thumb]:cursor-grab [&::-webkit-slider-thumb]:active:cursor-grabbing [&::-moz-range-thumb]:pointer-events-auto [&::-moz-range-thumb]:appearance-none [&::-moz-range-thumb]:h-3.5 [&::-moz-range-thumb]:w-3.5 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:bg-amber-500 [&::-moz-range-thumb]:border-2 [&::-moz-range-thumb]:border-slate-900 [&::-moz-range-thumb]:cursor-grab"
                  aria-label="Scale minimum"
                />
                <input
                  type="range"
                  min={0}
                  max={100}
                  step={0.5}
                  value={Math.min(100, Math.max(0, illuminance_scale_max))}
                  onChange={(e) => {
                    const val = Number(e.target.value);
                    setIlluminanceScaleMax(Math.max(val, illuminance_scale_min));
                  }}
                  className="absolute inset-0 w-full h-full appearance-none bg-transparent pointer-events-none [&::-webkit-slider-thumb]:pointer-events-auto [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:h-3.5 [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-blue-500 [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-slate-900 [&::-webkit-slider-thumb]:shadow-md [&::-webkit-slider-thumb]:cursor-grab [&::-webkit-slider-thumb]:active:cursor-grabbing [&::-moz-range-thumb]:pointer-events-auto [&::-moz-range-thumb]:appearance-none [&::-moz-range-thumb]:h-3.5 [&::-moz-range-thumb]:w-3.5 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:bg-blue-500 [&::-moz-range-thumb]:border-2 [&::-moz-range-thumb]:border-slate-900 [&::-moz-range-thumb]:cursor-grab"
                  aria-label="Scale maximum"
                />
              </div>
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5">
                  <span className="text-amber-400 text-[9px] font-semibold uppercase tracking-wider">min</span>
                  <input
                    type="number"
                    min={0}
                    step={0.01}
                    value={Number(illuminance_scale_min.toFixed(2))}
                    onChange={(e) => {
                      const val = Math.max(0, Number(e.target.value));
                      setIlluminanceScaleMin(Math.min(val, illuminance_scale_max));
                    }}
                    className="w-16 rounded border border-amber-700/50 bg-slate-950 px-1.5 py-0.5 text-[10px] text-amber-300 text-center outline-none focus:border-amber-500"
                    aria-label="Scale minimum value"
                  />
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="text-blue-400 text-[9px] font-semibold uppercase tracking-wider">max</span>
                  <input
                    type="number"
                    min={0}
                    step={0.01}
                    value={Number(illuminance_scale_max.toFixed(2))}
                    onChange={(e) => {
                      const val = Math.max(0, Number(e.target.value));
                      setIlluminanceScaleMax(Math.max(val, illuminance_scale_min));
                    }}
                    className="w-16 rounded border border-blue-700/50 bg-slate-950 px-1.5 py-0.5 text-[10px] text-blue-300 text-center outline-none focus:border-blue-500"
                    aria-label="Scale maximum value"
                  />
                </div>
              </div>
            </div>
          <div className="mt-2 grid grid-cols-2 gap-1">
            {(['lux', 'candela'] as PhotometricDisplayUnit[]).map((unit) => (
              <button
                key={unit}
                type="button"
                onClick={() => setPhotometricDisplayUnit(unit)}
                className={`rounded px-2 py-1 font-semibold ${photometric_display_unit === unit ? 'bg-cyan-600 text-white' : 'bg-slate-800 text-slate-300'}`}
              >
                {unit === 'lux' ? 'Lux (lx)' : 'Candela/m² (cd/m²)'}
              </button>
            ))}
          </div>

          <div className="mt-2 border-t border-slate-700/40 pt-2">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Luminarias</span>
              <span className="text-[11px] font-mono text-slate-300">{poles.length} uds</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[9px] text-slate-500">3</span>
              <input
                type="range"
                min={1}
                max={15}
                step={2}
                value={cfg.pole_count}
                onChange={(e) => setPoleCount(Number(e.target.value))}
                className="flex-1 h-1.5 appearance-none bg-slate-700 rounded-full cursor-pointer accent-cyan-500"
                aria-label="Número de luminarias"
              />
              <span className="text-[9px] text-slate-500">15</span>
            </div>
            <div className="mt-2 flex items-center justify-between">
              <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Edificios</span>
              <button
                type="button"
                onClick={() => setGenerateBuildings(!generate_buildings)}
                className={`text-[10px] px-3 py-1 rounded font-semibold transition-all ${generate_buildings ? 'bg-cyan-600 text-white' : 'bg-slate-800 text-slate-400'}`}
              >
                {generate_buildings ? 'ON' : 'OFF'}
              </button>
            </div>
          </div>

        </div>}
        {viewMode === 'orbit' ? (
          <div className="absolute bottom-3 left-3 text-[10px] text-slate-300 font-mono bg-slate-900/80 border border-slate-700/50 px-2.5 py-1.5 rounded-md flex flex-col gap-1">
            <div>drag · rotate &nbsp;|&nbsp; wheel · zoom &nbsp;|&nbsp; right-drag · pan</div>
            <div className="text-cyan-300/90">click on the road · measure illuminance (lx) and luminance (cd/m²)</div>
          </div>
        ) : (
          <div className="absolute bottom-3 left-3 flex flex-col gap-2 text-[10px] text-slate-300 font-mono bg-slate-900/85 border border-slate-700/50 p-2.5 rounded-md min-w-[200px]">
            <div className="text-[9px] uppercase tracking-wider text-amber-400 font-bold">Driver Controls</div>
            <div className="flex flex-wrap gap-1 mb-1">
              {getLaneInfo(cfg.roadElements).map((lane: LaneInfo) => (
                <button
                  key={lane.index}
                  type="button"
                  onClick={() => setDriverLaneIndex(lane.index)}
                  className={`text-[9px] px-2 py-0.5 rounded font-semibold transition-all ${
                    driverLaneIndex === lane.index
                      ? 'bg-amber-600 text-white'
                      : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
                  }`}
                >
                  {lane.label}
                </button>
              ))}
            </div>
            <label className="flex items-center gap-2">
              <span className="w-16 text-slate-400">Speed</span>
              <input
                type="range"
                min={10}
                max={120}
                step={5}
                value={speedKmh}
                onChange={(e) => onSpeedChange?.(Number(e.target.value))}
                className="flex-1 h-1 appearance-none bg-slate-700 rounded-full cursor-pointer accent-amber-500"
              />
              <span className="w-12 text-right text-amber-300">{speedKmh} km/h</span>
            </label>
            <div className="mt-2 flex items-center justify-between">
              <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">Edificios</span>
              <button
                type="button"
                onClick={() => setGenerateBuildings(!generate_buildings)}
                className={`text-[10px] px-3 py-1 rounded font-semibold transition-all ${generate_buildings ? 'bg-amber-600 text-white' : 'bg-slate-800 text-slate-400'}`}
              >
                {generate_buildings ? 'ON' : 'OFF'}
              </button>
            </div>
            <label className="flex items-center gap-2 mt-1">
              <span className="w-16 text-slate-400">Brillo</span>
              <input
                type="range"
                min={0.1}
                max={6}
                step={0.05}
                value={sceneBrightness}
                onChange={(e) => setSceneBrightness(Number(e.target.value))}
                className="flex-1 h-1 appearance-none bg-slate-700 rounded-full cursor-pointer accent-amber-500"
              />
              <span className="w-10 text-right text-amber-300">{sceneBrightness.toFixed(1)}</span>
            </label>
          </div>
        )}
        {viewMode !== 'driver' && <div className="absolute bottom-3 right-3 text-[10px] text-slate-300 bg-slate-900/85 border border-slate-700/60 px-2.5 py-2 rounded-md flex gap-2.5">
          <div className="flex flex-col justify-between h-[120px] my-0.5">
            {fieldStats ? (
              <>
                <span className="text-[9px] font-mono text-amber-200/90 leading-none">{(legendMax ?? fieldStats.maxE).toFixed(1)}</span>
                <span className="text-[9px] font-mono text-amber-300/70 leading-none">{((legendMax ?? fieldStats.maxE) * 0.75).toFixed(1)}</span>
                <span className="text-[9px] font-mono text-amber-300/50 leading-none">{((legendMax ?? fieldStats.maxE) * 0.5).toFixed(1)}</span>
                <span className="text-[9px] font-mono text-amber-300/30 leading-none">{((legendMax ?? fieldStats.maxE) * 0.25).toFixed(1)}</span>
                <span className="text-[9px] font-mono text-slate-500 leading-none">{legendMin.toFixed(1)}</span>
              </>
            ) : (
              <div className="flex flex-col justify-between h-full">
                <span className="text-[9px] font-mono text-slate-600 leading-none">--</span>
                <span className="text-[9px] font-mono text-slate-600 leading-none">--</span>
                <span className="text-[9px] font-mono text-slate-600 leading-none">--</span>
                <span className="text-[9px] font-mono text-slate-600 leading-none">--</span>
                <span className="text-[9px] font-mono text-slate-600 leading-none">--</span>
              </div>
            )}
          </div>
          <div className="flex flex-col items-center gap-1">
            <div
              className="w-3 rounded-sm flex-1"
              style={{ background: 'linear-gradient(to top,#020617 0%,#1e1b4b 15%,#581c87 30%,#9a3412 45%,#facc15 60%,#fef08a 78%,#fff 100%)' }}
            />
            <span className="text-[8px] text-slate-500 leading-none mt-0.5">{unitSuffix(photometric_display_unit)}</span>
          </div>
        </div>}
        {probe && viewMode !== 'driver' && (
          <button
            onClick={handleClearProbe}
            className="absolute top-16 right-5 text-[10px] font-mono px-2.5 py-1.5 rounded-md bg-cyan-950/90 border border-cyan-400/60 text-cyan-100 hover:bg-cyan-900"
          >
            ✕ clear probe
          </button>
        )}
      </div>
    </div>
  );
}
