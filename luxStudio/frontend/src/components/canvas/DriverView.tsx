import { memo, useRef, useMemo, useCallback, useLayoutEffect } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { useShallow } from 'zustand/react/shallow';
import * as THREE from 'three';
import { useConfigStore, type ConfigState } from '../../store/useConfigStore';
import SimulationCar, { CAR_COLORS } from './SimulationCar';
import type { RoadElement } from '../../types';

interface CarState {
  id: number;
  offsetX: number;
  laneIndex: number;
  laneZ: number;
  relSpeed: number;
  color: string;
  facing: number;
  group: THREE.Group | null;
}

function roadCfgSelector(s: ConfigState) {
  return {
    roadElements: s.roadElements as RoadElement[],
    road_width: s.road_width as number,
    spacing: s.spacing as number,
  };
}

export interface LaneInfo { index: number; z: number; width: number; label: string; }

export function getLaneInfo(elements: RoadElement[]): LaneInfo[] {
  const lanes: LaneInfo[] = [];
  let z = 0;
  for (const el of elements) {
    if (el.type === 'carriageway' && el.lanes && el.lanes > 0) {
      const laneW = el.width / el.lanes;
      for (let i = 0; i < el.lanes; i++) {
        lanes.push({ index: lanes.length, z: z + laneW * (i + 0.5), width: laneW, label: `Carril ${lanes.length + 1}` });
      }
    }
    z += el.width;
  }
  return lanes;
}

const EYE_HEIGHT = 1.15;
const CAR_SPAWN_AHEAD = 25;
const CAR_SPAWN_RANGE = 60;
const DESPAWN_BEHIND = 40;

export type TrafficDirection = 'same' | 'oncoming';

const DriverView = memo(function DriverView({
  speedKmh = 60,
  carCount = 6,
  driverLaneIndex = 0,
  trafficDirection = 'same',
  active = false,
}: {
  speedKmh?: number;
  carCount?: number;
  carSpeedSpread?: number;
  driverLaneIndex?: number;
  trafficDirection?: TrafficDirection;
  active?: boolean;
}) {
  const { camera, gl } = useThree();
  const cfg = useConfigStore(useShallow(roadCfgSelector));

  const lanes = useMemo(() => getLaneInfo(cfg.roadElements), [cfg.roadElements]);
  const driverLaneZ = useMemo(
    () => (lanes[driverLaneIndex]?.z ?? (cfg.road_width / 2)),
    [lanes, driverLaneIndex, cfg.road_width],
  );
  const otherLanes = useMemo(
    () => lanes.filter((_, i) => i !== driverLaneIndex),
    [lanes, driverLaneIndex],
  );

  const scrollRef = useRef(0);
  const carsRef = useRef<CarState[]>([]);
  const fovSetRef = useRef(false);

  const spawnCars = useCallback(() => {
    if (otherLanes.length === 0) return;
    const baseSpeed = speedKmh / 3.6;
    const cars: CarState[] = [];
    const startX = scrollRef.current;
    for (let i = 0; i < carCount; i++) {
      const laneIdx = Math.floor(Math.random() * otherLanes.length);
      let relSpeed: number;
      let spawnX: number;
      if (trafficDirection === 'same') {
        // Faster than us: spawn behind, catch up, overtake us
        const factor = 1.3 + Math.random() * 0.7;
        relSpeed = -(baseSpeed * factor); // negative → car X increases faster than camera
        spawnX = startX - DESPAWN_BEHIND - Math.random() * 80;
      } else {
        // Oncoming: come from ahead toward us
        relSpeed = baseSpeed * (1 + Math.random() * 1.5);
        spawnX = startX + CAR_SPAWN_AHEAD + Math.random() * 50;
      }
      cars.push({
        id: i,
        offsetX: spawnX,
        laneIndex: laneIdx,
        laneZ: otherLanes[laneIdx].z,
        relSpeed,
        color: CAR_COLORS[i % CAR_COLORS.length],
        facing: trafficDirection === 'same' ? 1 : -1,
        group: null,
      });
    }
    carsRef.current = cars;
  }, [carCount, otherLanes, speedKmh, trafficDirection]);

  const prevKey = useRef('');
  const paramKey = `${active}-${carCount}-${speedKmh}-${driverLaneIndex}-${trafficDirection}`;
  if (paramKey !== prevKey.current) {
    prevKey.current = paramKey;
    if (active) {
      scrollRef.current = 0;
      spawnCars();
    }
  }

  useLayoutEffect(() => {
    if (active) {
      const orig = gl.getPixelRatio();
      gl.setPixelRatio(Math.min(orig, 1));
      return () => gl.setPixelRatio(orig);
    }
  }, [active, gl]);

  const setCarRef = useCallback((id: number) => (g: THREE.Group | null) => {
    const car = carsRef.current.find((c) => c.id === id);
    if (car && g) {
      car.group = g;
      g.position.set(car.offsetX, 0, car.laneZ);
      g.rotation.y = car.facing > 0 ? 0 : Math.PI;
    }
  }, []);

  useFrame((_, delta) => {
    if (!active) return;

    if (!fovSetRef.current && camera.type === 'PerspectiveCamera') {
      (camera as THREE.PerspectiveCamera).fov = 60;
      (camera as THREE.PerspectiveCamera).updateProjectionMatrix();
      fovSetRef.current = true;
    }

    const speedMs = speedKmh / 3.6;
    scrollRef.current += speedMs * delta;

    camera.position.set(scrollRef.current, EYE_HEIGHT, driverLaneZ);
    camera.lookAt(scrollRef.current + 50, 0.55, driverLaneZ);

    const cars = carsRef.current;
    for (let i = 0; i < cars.length; i++) {
      const car = cars[i];
      car.offsetX -= car.relSpeed * delta;

      // Recycle: when car falls too far behind, respawn ahead
      if (car.offsetX < scrollRef.current - DESPAWN_BEHIND) {
        car.offsetX = scrollRef.current + CAR_SPAWN_AHEAD + Math.random() * CAR_SPAWN_RANGE;
        const newLane = Math.floor(Math.random() * otherLanes.length);
        car.laneIndex = newLane;
        car.laneZ = otherLanes[newLane].z;
      }
      // Catch: if a car got way ahead, bring it back
      if (car.offsetX > scrollRef.current + CAR_SPAWN_AHEAD + CAR_SPAWN_RANGE + 50) {
        car.offsetX = scrollRef.current + CAR_SPAWN_AHEAD + Math.random() * 50;
      }

      if (car.group) {
        car.group.position.set(car.offsetX, 0, car.laneZ);
        car.group.rotation.y = car.facing > 0 ? 0 : Math.PI;
      }
    }
  });

  if (!active || lanes.length === 0) return null;

  return (
    <group>
      {carsRef.current.map((car) => (
        <SimulationCar key={car.id} ref={setCarRef(car.id)} color={car.color} headlightOn={car.relSpeed > -5} />
      ))}
    </group>
  );
});

export default DriverView;
