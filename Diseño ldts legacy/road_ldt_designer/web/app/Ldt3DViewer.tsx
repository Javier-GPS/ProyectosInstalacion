"use client";

import { RotateCcw } from "lucide-react";
import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

export type LdtPhotometry = {
  c_angles_deg: number[];
  gamma_angles_deg: number[];
  intensity_cd_per_klm: number[][];
};

type ViewerRefs = {
  camera: THREE.PerspectiveCamera;
  controls: OrbitControls;
  render: () => void;
  updateSection: (cDeg: number) => void;
};

function normalizedC(cDeg: number) {
  return ((Number(cDeg) % 360) + 360) % 360;
}

function interpolatedCRow(photometry: LdtPhotometry, requestedC: number) {
  const samples = photometry.c_angles_deg
    .map((cDeg, index) => ({
      cDeg: normalizedC(cDeg),
      row: photometry.intensity_cd_per_klm[index],
    }))
    .sort((first, second) => first.cDeg - second.cDeg);
  const cDeg = normalizedC(requestedC);
  const upperIndex = samples.findIndex((sample) => sample.cDeg >= cDeg);
  const upper = upperIndex >= 0 ? samples[upperIndex] : samples[0];
  const lower =
    upperIndex > 0
      ? samples[upperIndex - 1]
      : samples[samples.length - 1];
  const lowerC =
    upperIndex > 0
      ? lower.cDeg
      : upperIndex === 0
        ? lower.cDeg - 360
        : lower.cDeg;
  const upperC = upperIndex >= 0 ? upper.cDeg : upper.cDeg + 360;
  const adjustedC = cDeg;
  const span = upperC - lowerC;
  const weight = span > 0 ? (adjustedC - lowerC) / span : 0;
  return lower.row.map(
    (value, index) =>
      (1 - weight) * Number(value || 0) +
      weight * Number(upper.row[index] || 0),
  );
}

function buildPhotometricSurface(photometry: LdtPhotometry) {
  const cAngles = [...photometry.c_angles_deg];
  const rows = photometry.intensity_cd_per_klm.map((row) => [...row]);
  const gammaAngles = photometry.gamma_angles_deg;

  if (cAngles.length < 2 || gammaAngles.length < 2 || rows.length !== cAngles.length) {
    throw new Error("La tabla fotométrica no contiene una malla C-gamma válida.");
  }

  const closesAt360 = Math.abs(cAngles[cAngles.length - 1] - cAngles[0] - 360) < 1e-6;
  if (!closesAt360) {
    cAngles.push(cAngles[0] + 360);
    rows.push([...rows[0]]);
  }

  const maximumIntensity = Math.max(
    0.001,
    ...rows.flatMap((row) => row.map((value) => Number(value) || 0)),
  );
  const positions: number[] = [];
  const colors: number[] = [];
  const indices: number[] = [];
  const lowColor = new THREE.Color("#ded9d1");
  const highColor = new THREE.Color("#1e1e1e");
  const maximumRadius = 2.15;

  cAngles.forEach((cDeg, cIndex) => {
    const cRad = THREE.MathUtils.degToRad(cDeg);
    gammaAngles.forEach((gammaDeg, gammaIndex) => {
      const intensity = Math.max(0, Number(rows[cIndex][gammaIndex]) || 0);
      const normalized = intensity / maximumIntensity;
      const radius = Math.max(0.018, normalized * maximumRadius);
      const gammaRad = THREE.MathUtils.degToRad(gammaDeg);
      const radialDistance = radius * Math.sin(gammaRad);

      positions.push(
        radialDistance * Math.cos(cRad),
        -radius * Math.cos(gammaRad),
        radialDistance * Math.sin(cRad),
      );

      const color = lowColor.clone().lerp(highColor, Math.pow(normalized, 0.68));
      colors.push(color.r, color.g, color.b);
    });
  });

  const gammaCount = gammaAngles.length;
  for (let cIndex = 0; cIndex < cAngles.length - 1; cIndex += 1) {
    for (let gammaIndex = 0; gammaIndex < gammaCount - 1; gammaIndex += 1) {
      const a = cIndex * gammaCount + gammaIndex;
      const b = (cIndex + 1) * gammaCount + gammaIndex;
      const c = b + 1;
      const d = a + 1;
      indices.push(a, b, d, b, c, d);
    }
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  geometry.computeBoundingSphere();

  return { geometry, maximumIntensity };
}

export default function Ldt3DViewer({
  photometry,
  selectedC = 0,
}: {
  photometry: LdtPhotometry;
  selectedC?: number;
}) {
  const mountRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<ViewerRefs | null>(null);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(34, 1, 0.01, 100);
    camera.position.set(3.35, 2.3, 3.35);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.setClearColor(0x000000, 0);
    renderer.domElement.setAttribute(
      "aria-label",
      "Distribución fotométrica tridimensional. Arrastra para rotar y usa la rueda para ampliar.",
    );
    renderer.domElement.setAttribute("role", "img");
    mount.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = false;
    controls.enablePan = false;
    controls.minDistance = 2.4;
    controls.maxDistance = 9;
    controls.target.set(0, -0.7, 0);

    scene.add(new THREE.HemisphereLight(0xffffff, 0x8f8a83, 2.1));
    const keyLight = new THREE.DirectionalLight(0xffffff, 2.8);
    keyLight.position.set(3, 4, 2);
    scene.add(keyLight);

    const grid = new THREE.GridHelper(5.2, 10, 0x6a6a6a, 0xe8e2d8);
    const gridMaterial = grid.material as THREE.Material;
    gridMaterial.transparent = true;
    gridMaterial.opacity = 0.42;
    scene.add(grid);

    const origin = new THREE.Mesh(
      new THREE.SphereGeometry(0.055, 18, 12),
      new THREE.MeshBasicMaterial({ color: 0x1e1e1e }),
    );
    scene.add(origin);

    const { geometry, maximumIntensity } = buildPhotometricSurface(photometry);
    const surface = new THREE.Mesh(
      geometry,
      new THREE.MeshStandardMaterial({
        vertexColors: true,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: 0.91,
        roughness: 0.72,
        metalness: 0.02,
      }),
    );
    scene.add(surface);

    const wireframe = new THREE.Mesh(
      geometry,
      new THREE.MeshBasicMaterial({
        color: 0x1e1e1e,
        wireframe: true,
        transparent: true,
        opacity: 0.055,
      }),
    );
    scene.add(wireframe);

    const sectionGeometry = new THREE.BufferGeometry();
    const sectionLine = new THREE.Line(
      sectionGeometry,
      new THREE.LineBasicMaterial({
        color: 0xe59a1d,
        transparent: true,
        opacity: 1,
      }),
    );
    sectionLine.renderOrder = 4;
    scene.add(sectionLine);

    const render = () => {
      renderer.render(scene, camera);
    };

    const updateSection = (cDeg: number) => {
      const row = interpolatedCRow(photometry, cDeg);
      const cRad = THREE.MathUtils.degToRad(normalizedC(cDeg));
      const points = photometry.gamma_angles_deg.map((gammaDeg, index) => {
        const intensity = Math.max(0, Number(row[index]) || 0);
        const radius = Math.max(
          0.018,
          (intensity / maximumIntensity) * 2.15,
        );
        const gammaRad = THREE.MathUtils.degToRad(gammaDeg);
        const radialDistance = radius * Math.sin(gammaRad);
        return new THREE.Vector3(
          radialDistance * Math.cos(cRad),
          -radius * Math.cos(gammaRad),
          radialDistance * Math.sin(cRad),
        );
      });
      sectionGeometry.setFromPoints(points);
      sectionGeometry.computeBoundingSphere();
      render();
    };

    const resize = () => {
      const width = Math.max(1, mount.clientWidth);
      const height = Math.max(280, mount.clientHeight);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height, false);
      render();
    };

    controls.addEventListener("change", render);
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(mount);
    resize();
    viewerRef.current = { camera, controls, render, updateSection };
    updateSection(selectedC);

    return () => {
      resizeObserver.disconnect();
      controls.removeEventListener("change", render);
      controls.dispose();
      geometry.dispose();
      (surface.material as THREE.Material).dispose();
      (wireframe.material as THREE.Material).dispose();
      sectionGeometry.dispose();
      (sectionLine.material as THREE.Material).dispose();
      (origin.geometry as THREE.BufferGeometry).dispose();
      (origin.material as THREE.Material).dispose();
      renderer.dispose();
      renderer.domElement.remove();
      viewerRef.current = null;
    };
  }, [photometry]);

  useEffect(() => {
    viewerRef.current?.updateSection(selectedC);
  }, [selectedC]);

  const resetView = () => {
    const viewer = viewerRef.current;
    if (!viewer) return;
    viewer.camera.position.set(3.35, 2.3, 3.35);
    viewer.controls.target.set(0, -0.7, 0);
    viewer.controls.update();
    viewer.render();
  };

  const maximumIntensity = Math.max(
    0,
    ...photometry.intensity_cd_per_klm.flatMap((row) => row),
  );

  return (
    <div className="ldt-3d-viewer">
      <div className="ldt-3d-toolbar">
        <span>
          <b>Intensidad 3D</b>
          <small>
            Máx. {maximumIntensity.toFixed(0)} cd/klm · plano C
            {normalizedC(selectedC).toFixed(0)}° resaltado
          </small>
        </span>
        <button type="button" onClick={resetView}>
          <RotateCcw size={14} /> Restablecer vista
        </button>
      </div>
      <div className="ldt-3d-stage" ref={mountRef}>
        <div className="ldt-axis-label ldt-axis-c0">C0°</div>
        <div className="ldt-axis-label ldt-axis-c90">C90°</div>
      </div>
      <div className="ldt-3d-help">
        <span>Arrastrar: rotar</span>
        <span>Rueda o gesto: zoom</span>
        <span>Origen: centro fotométrico</span>
      </div>
    </div>
  );
}
