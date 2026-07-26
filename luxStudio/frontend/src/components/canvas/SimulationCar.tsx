import { forwardRef, memo, useMemo, useRef, type Ref } from 'react';
import * as THREE from 'three';

const _geoCache = new Map<string, THREE.BufferGeometry>();
function cachedGeo<T extends THREE.BufferGeometry>(key: string, factory: () => T): T {
  if (!_geoCache.has(key)) _geoCache.set(key, factory());
  return _geoCache.get(key) as T;
}

const _matCache = new Map<string, THREE.Material>();
function cachedMat<T extends THREE.Material>(key: string, factory: () => T): T {
  if (!_matCache.has(key)) _matCache.set(key, factory());
  return _matCache.get(key) as T;
}

export const CAR_COLORS = [
  '#e74c3c', '#3498db', '#2ecc71', '#f39c12',
  '#9b59b6', '#1abc9c', '#e67e22', '#34495e',
  '#16a085', '#c0392b', '#2980b9', '#d35400',
];

const SimulationCar = memo(forwardRef(function SimulationCar(
  {
    color = '#e74c3c',
    headlightOn = true,
  }: {
    color?: string;
    headlightOn?: boolean;
  },
  ref: Ref<THREE.Group>,
) {
  const bodyMat = useMemo(
    () => cachedMat(`car-body-${color}`, () => new THREE.MeshStandardMaterial({ color, roughness: 0.35, metalness: 0.55 })),
    [color],
  );
  const darkMat = useMemo(
    () => cachedMat('car-dark', () => new THREE.MeshStandardMaterial({ color: '#1a1a1a', roughness: 0.9, metalness: 0.1 })),
    [],
  );
  const glassMat = useMemo(
    () => cachedMat('car-glass', () => new THREE.MeshStandardMaterial({
      color: '#1a1a2e', roughness: 0.1, metalness: 0.8,
      transparent: true, opacity: 0.6,
    })),
    [],
  );
  const headlightMat = useMemo(
    () => cachedMat(`car-headlight-${headlightOn}`, () => new THREE.MeshStandardMaterial({
      color: '#ffffff', emissive: '#fffbe6', emissiveIntensity: headlightOn ? 3 : 0.1,
    })),
    [headlightOn],
  );
  const taillightMat = useMemo(
    () => cachedMat('car-taillight', () => new THREE.MeshStandardMaterial({
      color: '#ff2200', emissive: '#ff2200', emissiveIntensity: 2,
    })),
    [],
  );

  return (
    <group ref={ref}>
      <mesh castShadow position={[0, 0.3, 0]} geometry={cachedGeo('car-body', () => new THREE.BoxGeometry(1.8, 0.35, 0.85))} material={bodyMat} />
      <mesh castShadow position={[0.98, 0.15, 0]} geometry={cachedGeo('car-bumper', () => new THREE.BoxGeometry(0.15, 0.2, 0.82))} material={darkMat} />
      <mesh castShadow position={[-0.98, 0.15, 0]} geometry={cachedGeo('car-rear', () => new THREE.BoxGeometry(0.15, 0.2, 0.82))} material={darkMat} />
      <mesh castShadow position={[0.15, 0.62, 0]} geometry={cachedGeo('car-cabin', () => new THREE.BoxGeometry(0.85, 0.35, 0.72))} material={glassMat} />
      <mesh castShadow position={[0.75, 0.38, 0]} geometry={cachedGeo('car-hood', () => new THREE.BoxGeometry(0.3, 0.08, 0.75))} material={bodyMat} />
      <mesh castShadow position={[-0.7, 0.38, 0]} geometry={cachedGeo('car-trunk', () => new THREE.BoxGeometry(0.35, 0.08, 0.75))} material={bodyMat} />
      <mesh position={[0.98, 0.22, 0.2]} geometry={cachedGeo('car-hl', () => new THREE.SphereGeometry(0.06, 8, 8))} material={headlightMat} />
      <mesh position={[0.98, 0.22, -0.2]} geometry={cachedGeo('car-hl', () => new THREE.SphereGeometry(0.06, 8, 8))} material={headlightMat} />
      <pointLight intensity={9} distance={12} decay={2} color="#fffbe6" position={[0.98, 0.22, 0]} />
      <mesh position={[-0.98, 0.22, 0.28]} geometry={cachedGeo('car-tl', () => new THREE.SphereGeometry(0.05, 8, 8))} material={taillightMat} />
      <mesh position={[-0.98, 0.22, -0.28]} geometry={cachedGeo('car-tl', () => new THREE.SphereGeometry(0.05, 8, 8))} material={taillightMat} />
      {([[-1, 0.08, 0.48], [-1, 0.08, -0.48], [1, 0.08, 0.48], [1, 0.08, -0.48]] as const).map((pos, i) => (
        <mesh key={`w${i}`} castShadow position={[pos[0], pos[1], pos[2]]} rotation={[0, 0, Math.PI / 2]}>
          <cylinderGeometry args={[0.14, 0.14, 0.1, 12]} />
          <meshStandardMaterial color="#111" roughness={0.95} metalness={0.05} />
        </mesh>
      ))}
    </group>
  );
}));

export default SimulationCar;
