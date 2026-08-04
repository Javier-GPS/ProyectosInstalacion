"use client";

import { useMemo, useState, type PointerEvent } from "react";
import type { LdtPhotometry } from "./Ldt3DViewer";

type CurveSource = {
  id: "target" | "physical" | "compensated";
  label: string;
  color: string;
  photometry: LdtPhotometry;
};

type CurveSeries = CurveSource & {
  row: number[];
  oppositeRow: number[];
  mirrorRow: number[];
  mirrorOppositeRow: number[];
  scale: number;
};

const VIEWBOX_WIDTH = 680;
const POLAR_CENTER_X = VIEWBOX_WIDTH / 2;

type PolarLayout = {
  height: number;
  centerY: number;
  radius: number;
};

type HoverPoint = {
  gamma: number;
  side: "selected" | "opposite";
  x: number;
  y: number;
};

function normalizedC(cDeg: number) {
  return ((Number(cDeg) % 360) + 360) % 360;
}

function mirrorC(cDeg: number) {
  return normalizedC(180 - normalizedC(cDeg));
}

function oppositeC(cDeg: number) {
  return normalizedC(cDeg + 180);
}

function interpolateCRow(photometry: LdtPhotometry, requestedC: number) {
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
  const span = upperC - lowerC;
  const weight = span > 0 ? (cDeg - lowerC) / span : 0;
  return lower.row.map(
    (value, index) =>
      (1 - weight) * Number(value || 0) +
      weight * Number(upper.row[index] || 0),
  );
}

function interpolateGamma(
  gammaAngles: number[],
  row: number[],
  requestedGamma: number,
) {
  if (!gammaAngles.length) return 0;
  if (requestedGamma <= gammaAngles[0]) return Number(row[0] || 0);
  const last = gammaAngles.length - 1;
  if (requestedGamma >= gammaAngles[last]) return Number(row[last] || 0);
  const upper = gammaAngles.findIndex((gamma) => gamma >= requestedGamma);
  const lower = Math.max(0, upper - 1);
  const span = gammaAngles[upper] - gammaAngles[lower];
  const weight =
    span > 0 ? (requestedGamma - gammaAngles[lower]) / span : 0;
  return (
    (1 - weight) * Number(row[lower] || 0) +
    weight * Number(row[upper] || 0)
  );
}

function niceMaximum(value: number) {
  if (value <= 0) return 1;
  const magnitude = 10 ** Math.floor(Math.log10(value));
  const normalized = value / magnitude;
  const step =
    normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10;
  return step * magnitude;
}

function contiguousWidth(
  gammaAngles: number[],
  row: number[],
  fraction: number,
) {
  if (!row.length) return 0;
  const peak = Math.max(...row);
  const peakIndex = row.indexOf(peak);
  const threshold = peak * fraction;
  let lower = peakIndex;
  let upper = peakIndex;
  while (lower > 0 && row[lower - 1] >= threshold) lower -= 1;
  while (upper + 1 < row.length && row[upper + 1] >= threshold) upper += 1;
  return gammaAngles[upper] - gammaAngles[lower];
}

export default function LdtSectionViewer({
  target,
  physical,
  compensated,
  selectedC,
  peakC,
  onSelectedC,
}: {
  target: LdtPhotometry;
  physical?: LdtPhotometry | null;
  compensated?: LdtPhotometry | null;
  selectedC: number;
  peakC?: number | null;
  onSelectedC: (value: number) => void;
}) {
  const [normalized, setNormalized] = useState(false);
  const [showSymmetry, setShowSymmetry] = useState(false);
  const [gammaLimit, setGammaLimit] = useState<90 | 180>(90);
  const [hoverPoint, setHoverPoint] = useState<HoverPoint | null>(null);

  const sources = useMemo(() => {
    const next: CurveSource[] = [
      {
        id: "target",
        label: "Objetivo",
        color: "#1e1e1e",
        photometry: target,
      },
    ];
    if (physical) {
      next.push({
        id: "physical",
        label: "Físico",
        color: "#b42318",
        photometry: physical,
      });
    }
    if (compensated) {
      next.push({
        id: "compensated",
        label: "Precompensado",
        color: "#2d6783",
        photometry: compensated,
      });
    }
    return next;
  }, [target, physical, compensated]);

  const series = useMemo<CurveSeries[]>(
    () =>
      sources.map((source) => {
        const row = interpolateCRow(source.photometry, selectedC);
        const oppositeRow = interpolateCRow(
          source.photometry,
          oppositeC(selectedC),
        );
        const mirrorRow = interpolateCRow(
          source.photometry,
          mirrorC(selectedC),
        );
        const mirrorOppositeRow = interpolateCRow(
          source.photometry,
          oppositeC(mirrorC(selectedC)),
        );
        const visibleValues = source.photometry.gamma_angles_deg
          .map((gamma, index) => ({
            gamma,
            value: showSymmetry
              ? Math.max(
                  row[index] || 0,
                  oppositeRow[index] || 0,
                  mirrorRow[index] || 0,
                  mirrorOppositeRow[index] || 0,
                )
              : Math.max(row[index] || 0, oppositeRow[index] || 0),
          }))
          .filter((item) => item.gamma <= gammaLimit)
          .map((item) => item.value);
        const scale = normalized
          ? 100 / Math.max(...visibleValues, 0.000001)
          : 1;
        return {
          ...source,
          row,
          oppositeRow,
          mirrorRow,
          mirrorOppositeRow,
          scale,
        };
      }),
    [sources, selectedC, gammaLimit, normalized, showSymmetry],
  );

  const yMaximum = useMemo(() => {
    if (normalized) return 100;
    const maximum = Math.max(
      ...series.flatMap((item) =>
        item.photometry.gamma_angles_deg
          .map((gamma, index) =>
            gamma <= gammaLimit
              ? showSymmetry
                ? Math.max(
                    item.row[index] || 0,
                    item.oppositeRow[index] || 0,
                    item.mirrorRow[index] || 0,
                    item.mirrorOppositeRow[index] || 0,
                  )
                : Math.max(
                    item.row[index] || 0,
                    item.oppositeRow[index] || 0,
                  )
              : 0,
          ),
      ),
      1,
    );
    return niceMaximum(maximum);
  }, [series, gammaLimit, normalized, showSymmetry]);

  const layout: PolarLayout =
    gammaLimit === 90
      ? { height: 340, centerY: 42, radius: 255 }
      : { height: 430, centerY: 215, radius: 184 };

  const polarPosition = (
    gamma: number,
    radius: number,
    side: "selected" | "opposite",
  ) => {
    const radians = (Math.min(gamma, gammaLimit) * Math.PI) / 180;
    const direction = side === "selected" ? 1 : -1;
    return {
      x: POLAR_CENTER_X + direction * radius * Math.sin(radians),
      y: layout.centerY + radius * Math.cos(radians),
    };
  };

  const pathFor = (
    item: CurveSeries,
    row: number[],
    side: "selected" | "opposite",
  ) => {
    const points = item.photometry.gamma_angles_deg
      .map((gamma, index) => ({
        gamma,
        value: Number(row[index] || 0) * item.scale,
      }))
      .filter((point) => point.gamma <= gammaLimit);
    return points
      .map((point, index) => {
        const position = polarPosition(
          point.gamma,
          (Math.max(0, point.value) / yMaximum) * layout.radius,
          side,
        );
        return `${index === 0 ? "M" : "L"} ${position.x.toFixed(
          2,
        )} ${position.y.toFixed(2)}`;
      })
      .join(" ");
  };

  const polarArc = (radius: number) => {
    const points: { x: number; y: number }[] = [];
    for (let gamma = gammaLimit; gamma >= 0; gamma -= 2) {
      points.push(polarPosition(gamma, radius, "opposite"));
    }
    for (let gamma = 2; gamma <= gammaLimit; gamma += 2) {
      points.push(polarPosition(gamma, radius, "selected"));
    }
    return points
      .map(
        (point, index) =>
          `${index === 0 ? "M" : "L"} ${point.x.toFixed(
            2,
          )} ${point.y.toFixed(2)}`,
      )
      .join(" ");
  };

  const targetRow = series[0]?.row ?? [];
  const targetOppositeRow = series[0]?.oppositeRow ?? [];
  const targetVisibleIndices = target.gamma_angles_deg
    .map((gamma, index) => ({ gamma, index }))
    .filter((item) => item.gamma <= gammaLimit);
  const targetSelectedVisibleRow = targetVisibleIndices.map(
    (item) => targetRow[item.index] || 0,
  );
  const targetOppositeVisibleRow = targetVisibleIndices.map(
    (item) => targetOppositeRow[item.index] || 0,
  );
  const targetVisibleGamma = targetVisibleIndices.map((item) => item.gamma);
  const selectedPeakValue = Math.max(...targetSelectedVisibleRow, 0);
  const oppositePeakValue = Math.max(...targetOppositeVisibleRow, 0);
  const targetVisibleRow =
    selectedPeakValue >= oppositePeakValue
      ? targetSelectedVisibleRow
      : targetOppositeVisibleRow;
  const targetPeakValue = Math.max(selectedPeakValue, oppositePeakValue);
  const targetPeakIndex = targetVisibleRow.indexOf(targetPeakValue);
  const targetPeakGamma =
    targetPeakIndex >= 0 ? targetVisibleGamma[targetPeakIndex] : 0;
  const width90 = contiguousWidth(
    targetVisibleGamma,
    targetVisibleRow,
    0.9,
  );
  const fwhm = contiguousWidth(
    targetVisibleGamma,
    targetVisibleRow,
    0.5,
  );
  const selectedCIsInterpolated = sources.some(
    (source) =>
      !source.photometry.c_angles_deg.some(
        (value) =>
          Math.abs(normalizedC(value) - normalizedC(selectedC)) < 1e-7,
      ),
  );
  const hasUpperData = sources.some(
    (source) =>
      Math.max(...source.photometry.gamma_angles_deg, 0) > 90,
  );

  const angularTicks = Array.from(
    { length: gammaLimit === 90 ? 7 : 7 },
    (_, index) => index * (gammaLimit === 90 ? 15 : 30),
  );
  const radialTicks = Array.from({ length: 5 }, (_, index) => (index + 1) / 5);
  const tooltipItems =
    hoverPoint == null
      ? []
      : series.map((item) => ({
          ...item,
          value:
            interpolateGamma(
              item.photometry.gamma_angles_deg,
              hoverPoint.side === "selected"
                ? item.row
                : item.oppositeRow,
              hoverPoint.gamma,
            ) * item.scale,
        }));

  const handlePointerMove = (event: PointerEvent<SVGSVGElement>) => {
    const rectangle = event.currentTarget.getBoundingClientRect();
    const x =
      ((event.clientX - rectangle.left) / rectangle.width) * VIEWBOX_WIDTH;
    const y =
      ((event.clientY - rectangle.top) / rectangle.height) * layout.height;
    const deltaX = x - POLAR_CENTER_X;
    const deltaY = y - layout.centerY;
    const radius = Math.hypot(deltaX, deltaY);
    const gamma =
      (Math.atan2(Math.abs(deltaX), deltaY) * 180) / Math.PI;
    if (radius > layout.radius + 18 || gamma > gammaLimit + 2) {
      setHoverPoint(null);
      return;
    }
    setHoverPoint({
      gamma: Math.min(gammaLimit, Math.max(0, gamma)),
      side: deltaX >= 0 ? "selected" : "opposite",
      x,
      y,
    });
  };

  const hoverSpokeEnd =
    hoverPoint == null
      ? null
      : polarPosition(hoverPoint.gamma, layout.radius, hoverPoint.side);
  const tooltipX =
    hoverPoint?.side === "selected" ? 22 : VIEWBOX_WIDTH - 194;
  const tooltipY = gammaLimit === 90 ? 54 : 18;

  return (
    <div className="ldt-section-viewer">
      <div className="ldt-section-toolbar">
        <div className="section-mode-buttons">
          <button
            type="button"
            className={!normalized ? "active" : ""}
            onClick={() => setNormalized(false)}
          >
            cd/klm
          </button>
          <button
            type="button"
            className={normalized ? "active" : ""}
            onClick={() => setNormalized(true)}
          >
            Normalizado
          </button>
        </div>
        <div className="section-mode-buttons">
          <button
            type="button"
            className={gammaLimit === 90 ? "active" : ""}
            onClick={() => setGammaLimit(90)}
          >
            γ 0–90°
          </button>
          <button
            type="button"
            className={gammaLimit === 180 ? "active" : ""}
            disabled={!hasUpperData}
            onClick={() => setGammaLimit(180)}
          >
            γ 0–180°
          </button>
        </div>
        <button
          type="button"
          className={`symmetry-button ${showSymmetry ? "active" : ""}`}
          onClick={() => setShowSymmetry((current) => !current)}
        >
          {showSymmetry ? "Simetría visible" : "Comparar simetría"}
        </button>
      </div>

      <div className="section-c-control">
        <div>
          <span>
            Eje C activo
            {selectedCIsInterpolated && <small>interpolado</small>}
          </span>
          <label>
            C
            <input
              type="number"
              min="0"
              max="359"
              step="1"
              value={Math.round(normalizedC(selectedC))}
              onChange={(event) =>
                onSelectedC(
                  Math.min(359, Math.max(0, Number(event.target.value))),
                )
              }
            />
            °
          </label>
        </div>
        <input
          aria-label="Plano C del corte fotométrico"
          type="range"
          min="0"
          max="359"
          step="1"
          value={normalizedC(selectedC)}
          onChange={(event) => onSelectedC(Number(event.target.value))}
        />
        <div className="section-c-presets">
          {[0, 30, 60, 90, 180, 270].map((value) => (
            <button
              type="button"
              key={value}
              className={
                Math.round(normalizedC(selectedC)) === value ? "active" : ""
              }
              onClick={() => onSelectedC(value)}
            >
              C{value}°
            </button>
          ))}
          {peakC != null && (
            <button
              type="button"
              onClick={() => onSelectedC(normalizedC(peakC))}
            >
              C del máximo
            </button>
          )}
        </div>
      </div>

      <div className="section-chart">
        <svg
          viewBox={`0 0 ${VIEWBOX_WIDTH} ${layout.height}`}
          role="img"
          aria-label={`Diagrama polar fotométrico para el eje C${normalizedC(
            selectedC,
          ).toFixed(0)}–C${oppositeC(selectedC).toFixed(0)} grados`}
          onPointerMove={handlePointerMove}
          onPointerLeave={() => setHoverPoint(null)}
        >
          {radialTicks.map((ratio) => {
            const value = ratio * yMaximum;
            const labelPosition = polarPosition(
              38,
              ratio * layout.radius,
              "selected",
            );
            return (
              <g key={ratio}>
                <path
                  d={polarArc(ratio * layout.radius)}
                  fill="none"
                  className="section-grid-line"
                />
                <text
                  x={labelPosition.x + 5}
                  y={labelPosition.y - 4}
                  className="section-axis-text"
                >
                  {normalized
                    ? `${value.toFixed(0)} %`
                    : value >= 100
                      ? `${value.toFixed(0)}`
                      : `${value.toFixed(1)}`}
                </text>
              </g>
            );
          })}
          {angularTicks.map((gamma) => {
            const selectedEnd = polarPosition(
              gamma,
              layout.radius,
              "selected",
            );
            const oppositeEnd = polarPosition(
              gamma,
              layout.radius,
              "opposite",
            );
            const selectedLabel = polarPosition(
              gamma,
              layout.radius + 17,
              "selected",
            );
            const oppositeLabel = polarPosition(
              gamma,
              layout.radius + 17,
              "opposite",
            );
            const sharedAxis = gamma === 0 || gamma === 180;
            return (
              <g key={gamma}>
                <line
                  x1={POLAR_CENTER_X}
                  x2={selectedEnd.x}
                  y1={layout.centerY}
                  y2={selectedEnd.y}
                  className="section-grid-line angular"
                />
                {!sharedAxis && (
                  <line
                    x1={POLAR_CENTER_X}
                    x2={oppositeEnd.x}
                    y1={layout.centerY}
                    y2={oppositeEnd.y}
                    className="section-grid-line angular"
                  />
                )}
                <text
                  x={selectedLabel.x}
                  y={selectedLabel.y + 3}
                  textAnchor="middle"
                  className="section-axis-text"
                >
                  {gamma}°
                </text>
                {!sharedAxis && (
                  <text
                    x={oppositeLabel.x}
                    y={oppositeLabel.y + 3}
                    textAnchor="middle"
                    className="section-axis-text"
                  >
                    {gamma}°
                  </text>
                )}
              </g>
            );
          })}
          <text
            x={18}
            y={gammaLimit === 90 ? 24 : 18}
            className="section-axis-title"
          >
            Radio: {normalized ? "% del pico de cada curva" : "cd/klm"}
          </text>
          <text
            x={VIEWBOX_WIDTH - 24}
            y={layout.centerY - 12}
            textAnchor="end"
            className="section-plane-label selected"
          >
            C{normalizedC(selectedC).toFixed(0)}°
          </text>
          <text
            x={24}
            y={layout.centerY - 12}
            className="section-plane-label opposite"
          >
            C{oppositeC(selectedC).toFixed(0)}°
          </text>
          <text
            x={POLAR_CENTER_X + 9}
            y={layout.centerY + 16}
            className="section-nadir-label"
          >
            γ 0° · nadir
          </text>

          {series.map((item) => (
            <g key={item.id}>
              {showSymmetry && (
                <>
                  <path
                    d={pathFor(item, item.mirrorRow, "selected")}
                    fill="none"
                    stroke={item.color}
                    strokeWidth="1.5"
                    strokeDasharray="6 5"
                    opacity="0.48"
                    vectorEffect="non-scaling-stroke"
                  />
                  <path
                    d={pathFor(
                      item,
                      item.mirrorOppositeRow,
                      "opposite",
                    )}
                    fill="none"
                    stroke={item.color}
                    strokeWidth="1.5"
                    strokeDasharray="6 5"
                    opacity="0.48"
                    vectorEffect="non-scaling-stroke"
                  />
                </>
              )}
              <path
                d={pathFor(item, item.row, "selected")}
                fill="none"
                stroke={item.color}
                strokeWidth={item.id === "target" ? "2.6" : "2.2"}
                vectorEffect="non-scaling-stroke"
              />
              <path
                d={pathFor(item, item.oppositeRow, "opposite")}
                fill="none"
                stroke={item.color}
                strokeWidth={item.id === "target" ? "2.6" : "2.2"}
                vectorEffect="non-scaling-stroke"
              />
            </g>
          ))}

          {hoverPoint != null && hoverSpokeEnd != null && (
            <g className="section-tooltip">
              <line
                x1={POLAR_CENTER_X}
                x2={hoverSpokeEnd.x}
                y1={layout.centerY}
                y2={hoverSpokeEnd.y}
              />
              <rect
                x={tooltipX}
                y={tooltipY}
                width="172"
                height={34 + tooltipItems.length * 20}
                rx="6"
              />
              <text
                x={tooltipX + 10}
                y={tooltipY + 18}
                className="section-tooltip-title"
              >
                C
                {(
                  hoverPoint.side === "selected"
                    ? normalizedC(selectedC)
                    : oppositeC(selectedC)
                ).toFixed(0)}
                ° · γ {hoverPoint.gamma.toFixed(1)}°
              </text>
              {tooltipItems.map((item, index) => (
                <g key={item.id}>
                  <circle
                    cx={tooltipX + 11}
                    cy={tooltipY + 36 + index * 20}
                    r="3"
                    fill={item.color}
                  />
                  <text
                    x={tooltipX + 20}
                    y={tooltipY + 39 + index * 20}
                  >
                    {item.label}: {item.value.toFixed(normalized ? 1 : 0)}
                    {normalized ? " %" : " cd/klm"}
                  </text>
                </g>
              ))}
            </g>
          )}
        </svg>
      </div>

      <div className="section-legend">
        {series.map((item) => (
          <span key={item.id}>
            <i style={{ background: item.color }} />
            {item.label}
          </span>
        ))}
        {showSymmetry && (
          <span className="mirror-legend">
            <i />
            Eje reflejado C{mirrorC(selectedC).toFixed(0)}°–C
            {oppositeC(mirrorC(selectedC)).toFixed(0)}°
          </span>
        )}
      </div>

      <div className="section-cut-stats">
        <span>
          <small>MÁXIMO DEL CORTE</small>
          <b>{targetPeakValue.toFixed(0)} cd/klm</b>
        </span>
        <span>
          <small>γ DEL MÁXIMO</small>
          <b>{targetPeakGamma.toFixed(1)}°</b>
        </span>
        <span>
          <small>CRESTA 90 %</small>
          <b>{width90.toFixed(1)}°</b>
        </span>
        <span>
          <small>FWHM</small>
          <b>{fwhm.toFixed(1)}°</b>
        </span>
      </div>
    </div>
  );
}
