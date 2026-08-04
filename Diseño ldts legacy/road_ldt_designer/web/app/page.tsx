"use client";

import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Bot,
  Building2,
  Check,
  CheckCircle2,
  ChevronDown,
  CircleHelp,
  CircleGauge,
  Download,
  FileDown,
  Gauge,
  Info,
  Languages,
  Layers3,
  Lightbulb,
  LoaderCircle,
  Map,
  Play,
  RotateCcw,
  Ruler,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  SunMedium,
  UserRound,
  Waypoints,
} from "lucide-react";
import dynamic from "next/dynamic";
import {
  type ChangeEvent,
  useEffect,
  useId,
  useMemo,
  useState,
} from "react";
import LdtSectionViewer from "./LdtSectionViewer";

const Ldt3DViewer = dynamic(() => import("./Ldt3DViewer"), {
  ssr: false,
  loading: () => <div className="ldt-3d-loading">Preparando visualización 3D…</div>,
});

type FormState = {
  projectName: string;
  laneWidths: number[];
  sidewalkLeft: number;
  sidewalkRight: number;
  rTable: string;
  arrangement: string;
  unilateralSide: string;
  spacing: number;
  height: number;
  flux: number;
  setback: number;
  overhang: number;
  tilt: number;
  lightingClass: string;
  customLavg: number;
  customUo: number;
  customUl: number;
  customTi: number;
  customRei: number;
  maintenanceFactor: number;
  includeRei: boolean;
  sidewalkTarget: number;
  evaluateIntrusion: boolean;
  buildingSide: string;
  buildingSetback: number;
  buildingHeight: number;
  facadeLimit: number;
  windowLimit: number;
  candidates: number;
};

type MetricResult = {
  luminance_avg_cd_m2: number;
  uo: number;
  ul: number;
  ti_pct: number;
  rei: number | null;
  sr?: number | null;
  intrusion_max_lx?: number | null;
};

type PhotometryResult = {
  source?: string;
  declared_flux_lm?: number;
  c_step_deg?: number;
  gamma_step_deg?: number;
  peak_intensity_cd_per_klm?: number;
  peak_c_deg?: number;
  peak_gamma_deg?: number;
  gamma_width_90_deg?: number;
  gamma_fwhm_deg?: number;
  high_angle_flux_fraction?: number;
  upward_flux_fraction?: number;
  backlight_flux_fraction?: number;
  longitudinal_symmetry_error_pct?: number;
  c_angles_deg: number[];
  gamma_angles_deg: number[];
  intensity_cd_per_klm: number[][];
};

type OptimizeResult = {
  status: string;
  compliant: boolean;
  failures: string[];
  metrics: MetricResult;
  optimizer: {
    evaluated_candidates: number;
    score: number;
    maximum_violation: number;
    parameters: Record<string, number>;
  };
  photometry: PhotometryResult;
  road_luminance: {
    x_m: number;
    y_m: number;
    lane_index: number;
    luminance_cd_m2: number;
  }[];
  ldt_text: string;
};

type PhysicalValidationResult = {
  status: string;
  filename: string;
  compliant: boolean;
  failures: string[];
  metrics: MetricResult;
  target_metrics: MetricResult;
  metric_deltas: Record<string, number | null>;
  comparison: {
    normalized_rmse_pct: number;
    normalized_mean_absolute_error_pct: number;
    shape_correlation: number;
    peak_c_shift_deg: number;
    peak_gamma_shift_deg: number;
    gamma_width_90_delta_deg: number;
    gamma_fwhm_delta_deg: number;
    high_angle_flux_delta_pct_points: number;
    upward_flux_delta_pct_points: number;
    backlight_flux_delta_pct_points: number;
  };
  residual_map: {
    c_angles_deg: number[];
    gamma_angles_deg: number[];
    error_pct_of_target_peak: number[][];
    minimum_error_pct: number;
    maximum_error_pct: number;
  };
  compensation: {
    correction_gain: number;
    smoothing_passes: number;
    clipped_low_fraction: number;
    capped_high_fraction: number;
    maximum_adjustment_pct_of_target_peak: number;
    integrated_flux_lm_per_klm: number;
    pre_distortion_rmse_pct: number;
    filename: string;
    ldt_text: string;
    photometry: PhotometryResult;
  };
  photometry: PhotometryResult;
};

const ENGINE_URL =
  process.env.NEXT_PUBLIC_ENGINE_URL || "http://127.0.0.1:5050";

const CLASS_DATA: Record<
  string,
  { l: number; uo: number; ul: number; ti: number; rei: number }
> = {
  M1: { l: 2, uo: 0.4, ul: 0.7, ti: 10, rei: 0.35 },
  M2: { l: 1.5, uo: 0.4, ul: 0.7, ti: 10, rei: 0.35 },
  M3: { l: 1, uo: 0.4, ul: 0.6, ti: 15, rei: 0.3 },
  M4: { l: 0.75, uo: 0.4, ul: 0.6, ti: 15, rei: 0.3 },
  M5: { l: 0.5, uo: 0.35, ul: 0.4, ti: 15, rei: 0.3 },
  M6: { l: 0.3, uo: 0.35, ul: 0.4, ti: 20, rei: 0.3 },
};

const INITIAL_FORM: FormState = {
  projectName: "Avenida urbana · Estudio 01",
  laneWidths: [3.5, 3.5],
  sidewalkLeft: 2,
  sidewalkRight: 2,
  rTable: "R2",
  arrangement: "unilateral",
  unilateralSide: "left",
  spacing: 30,
  height: 8,
  flux: 10000,
  setback: 1,
  overhang: 1,
  tilt: 0,
  lightingClass: "M4",
  customLavg: 0.75,
  customUo: 0.4,
  customUl: 0.6,
  customTi: 15,
  customRei: 0.3,
  maintenanceFactor: 0.8,
  includeRei: true,
  sidewalkTarget: 5,
  evaluateIntrusion: false,
  buildingSide: "right",
  buildingSetback: 6,
  buildingHeight: 12,
  facadeLimit: 5,
  windowLimit: 2,
  candidates: 70,
};

const STEPS = [
  { label: "Geometría", icon: Ruler },
  { label: "Instalación", icon: Lightbulb },
  { label: "Requisitos", icon: CircleGauge },
  { label: "Optimización", icon: Sparkles },
  { label: "Resultados", icon: Layers3 },
];

const ARRANGEMENTS = [
  { id: "unilateral", label: "Unilateral", glyph: "●  ─────" },
  { id: "bilateral_opposite", label: "Bilateral", glyph: "●  ───  ●" },
  { id: "bilateral_staggered", label: "Tresbolillo", glyph: "●  ──  ·  ●" },
  { id: "central_double", label: "Central doble", glyph: "──  ●●  ──" },
];

function Field({
  label,
  value,
  onChange,
  unit,
  min,
  max,
  step,
  info,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  unit?: string;
  min?: number;
  max?: number;
  step?: number;
  info?: MetricInfoKey;
}) {
  return (
    <label className="field">
      <span className="field-label">
        {label}
        {info && <MetricInfo metric={info} />}
      </span>
      <div className="input-wrap">
        <input
          type="number"
          value={value}
          min={min}
          max={max}
          step={step ?? 0.1}
          onChange={(event) => onChange(Number(event.target.value))}
        />
        {unit && <em>{unit}</em>}
      </div>
    </label>
  );
}

function Toggle({
  checked,
  onChange,
  label,
  detail,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  detail: string;
}) {
  return (
    <button
      type="button"
      className={`toggle-row ${checked ? "is-on" : ""}`}
      onClick={() => onChange(!checked)}
    >
      <span className="toggle"><i /></span>
      <span>
        <strong>{label}</strong>
        <small>{detail}</small>
      </span>
    </button>
  );
}

function StreetPreview({ form }: { form: FormState }) {
  const roadWidth = form.laneWidths.reduce((sum, value) => sum + value, 0);
  const total = roadWidth + form.sidewalkLeft + form.sidewalkRight;
  const leftRatio = (form.sidewalkLeft / total) * 100;
  const roadRatio = (roadWidth / total) * 100;
  const laneStart = leftRatio;
  const poles =
    form.arrangement === "unilateral"
      ? [form.unilateralSide]
      : form.arrangement === "central_double"
        ? ["center"]
        : ["left", "right"];
  return (
    <div className="street-preview">
      <div className="preview-label">
        <span>Sección transversal</span>
        <b>{roadWidth.toFixed(1)} m de calzada</b>
      </div>
      <svg viewBox="0 0 720 250" role="img" aria-label="Vista previa de la calle">
        <defs>
          <linearGradient id="road" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0" stopColor="#303941" />
            <stop offset="1" stopColor="#1d252c" />
          </linearGradient>
          <filter id="glow">
            <feGaussianBlur stdDeviation="8" />
          </filter>
        </defs>
        <rect x="0" y="176" width="720" height="74" fill="#d7d5cd" />
        <rect
          x={(leftRatio / 100) * 720}
          y="164"
          width={(roadRatio / 100) * 720}
          height="86"
          fill="url(#road)"
        />
        {form.laneWidths.slice(0, -1).map((_, index) => {
          const before = form.laneWidths
            .slice(0, index + 1)
            .reduce((sum, value) => sum + value, 0);
          const x = ((laneStart + (before / total) * 100) / 100) * 720;
          return (
            <line
              key={index}
              x1={x}
              x2={x}
              y1="170"
              y2="250"
              stroke="#e8e3ca"
              strokeWidth="2"
              strokeDasharray="12 12"
              opacity=".75"
            />
          );
        })}
        {poles.map((side) => {
          const x =
            side === "left"
              ? Math.max(28, (leftRatio / 100) * 720 - 26)
              : side === "right"
                ? Math.min(692, ((leftRatio + roadRatio) / 100) * 720 + 26)
                : ((leftRatio + roadRatio / 2) / 100) * 720;
          const armDirection = side === "right" ? -1 : 1;
          const arm = side === "center" ? 24 : 38;
          return (
            <g key={side}>
              <ellipse
                cx={x + armDirection * arm}
                cy="92"
                rx="76"
                ry="52"
                fill="#f7b84b"
                opacity=".16"
                filter="url(#glow)"
              />
              <line x1={x} x2={x} y1="58" y2="176" stroke="#66737c" strokeWidth="5" />
              <line
                x1={x}
                x2={x + armDirection * arm}
                y1="60"
                y2="60"
                stroke="#66737c"
                strokeWidth="5"
              />
              <rect
                x={x + armDirection * arm - 10}
                y="56"
                width="22"
                height="8"
                rx="4"
                fill="#f4b94f"
              />
            </g>
          );
        })}
        <text x="20" y="228" className="svg-label">ACERA</text>
        <text x="650" y="228" className="svg-label">ACERA</text>
        <text x="330" y="228" className="svg-road-label">{form.laneWidths.length} CARRILES</text>
      </svg>
      <div className="preview-stats">
        <span><Ruler size={14} /> {form.spacing} m interdistancia</span>
        <span><Lightbulb size={14} /> {form.height} m altura</span>
        <span><SunMedium size={14} /> {(form.flux / 1000).toFixed(1)} klm</span>
      </div>
    </div>
  );
}

type MetricInfoKey =
  | "lavg"
  | "uo"
  | "ul"
  | "ti"
  | "rei"
  | "sr"
  | "intrusion";

const METRIC_INFO: Record<
  MetricInfoKey,
  {
    title: string;
    meaning: string;
    formula: string;
    reading: string;
  }
> = {
  lavg: {
    title: "Luminancia media L̄",
    meaning:
      "Promedio de la luminancia de todos los puntos de la calzada para el observador crítico.",
    formula: "L̄ = (1 / N) · Σ Lᵢ",
    reading:
      "Se expresa en cd/m². Debe alcanzar el mínimo de la clase M seleccionada.",
  },
  uo: {
    title: "Uniformidad global Uo",
    meaning:
      "Compara el punto menos luminoso de toda la calzada con la luminancia media.",
    formula: "Uo = Lmín / L̄",
    reading:
      "Es adimensional. Cuanto más próximo a 1, más uniforme es el conjunto de la calzada.",
  },
  ul: {
    title: "Uniformidad longitudinal Ul",
    meaning:
      "Mide la variación de luminancia a lo largo de la línea central del carril y toma el observador más desfavorable.",
    formula: "Ul = mínobs (Lmín,long / Lmáx,long)",
    reading:
      "Es adimensional. Cuanto más próximo a 1, menor alternancia claro–oscuro percibe el conductor.",
  },
  ti: {
    title: "Incremento de umbral TI",
    meaning:
      "Estima la pérdida de visibilidad causada por el deslumbramiento perturbador de las luminarias.",
    formula: "TI = 65 · Lv / L̄⁰·⁸  [%]",
    reading:
      "Lv es la luminancia de velo equivalente. En TI, un valor menor es mejor y no debe superar el máximo de clase.",
  },
  rei: {
    title: "Relación de iluminancia de borde REI / EIR",
    meaning:
      "Comprueba que la luz útil no termine bruscamente en los bordes de la calzada. Se adopta el lado más desfavorable.",
    formula:
      "REI = mín(Eext,izq / Eint,izq ; Eext,der / Eint,der)",
    reading:
      "Es adimensional. Un valor mayor indica mejor continuidad visual en los bordes.",
  },
  sr: {
    title: "Relación de entorno SR",
    meaning:
      "Relaciona la iluminancia media de las bandas exteriores con la de las bandas interiores de la calzada.",
    formula:
      "SR = (Eext,izq + Eext,der) / (Eint,izq + Eint,der)",
    reading:
      "Es el índice histórico de entorno. El perfil actual emplea REI por cada lado.",
  },
  intrusion: {
    title: "Intrusión luminosa máxima",
    meaning:
      "Mayor iluminancia vertical calculada sobre las fachadas o ventanas incluidas en la evaluación.",
    formula: "Emáx = máx(Efachada,k ; Eventana,k)",
    reading:
      "Se expresa en lux. Un valor menor reduce la luz no deseada sobre edificios colindantes.",
  },
};

function MetricInfo({ metric }: { metric: MetricInfoKey }) {
  const id = useId();
  const info = METRIC_INFO[metric];
  return (
    <span className="metric-info">
      <button
        type="button"
        aria-label={`Información sobre ${info.title}`}
        aria-describedby={id}
      >
        <Info size={13} aria-hidden="true" />
      </button>
      <span id={id} role="tooltip" className="metric-info-popover">
        <strong>{info.title}</strong>
        <span>{info.meaning}</span>
        <code>{info.formula}</code>
        <small>{info.reading}</small>
      </span>
    </span>
  );
}

function RequirementMetric({
  label,
  value,
  metric,
}: {
  label: string;
  value: string;
  metric: MetricInfoKey;
}) {
  return (
    <span>
      <span className="requirement-label">
        <small>{label}</small>
        <MetricInfo metric={metric} />
      </span>
      <b>{value}</b>
    </span>
  );
}

function MetricCard({
  label,
  value,
  target,
  pass,
  info,
}: {
  label: string;
  value: string;
  target: string;
  pass: boolean;
  info: MetricInfoKey;
}) {
  return (
    <div className={`metric-card ${pass ? "pass" : "fail"}`}>
      <div>
        <span className="metric-card-label">
          {label}
          <MetricInfo metric={info} />
        </span>
        {pass ? <CheckCircle2 size={17} /> : <AlertTriangle size={17} />}
      </div>
      <strong>{value}</strong>
      <small>{target}</small>
    </div>
  );
}

function Heatmap({ result }: { result: OptimizeResult }) {
  const points = result.road_luminance;
  const values = points.map((item) => item.luminance_cd_m2);
  const max = Math.max(...values, 0.001);
  const rows = Array.from(new Set(points.map((item) => item.lane_index)));
  return (
    <div className="heatmap">
      {rows.map((lane) => (
        <div key={lane}>
          {points
            .filter((point) => point.lane_index === lane)
            .map((point, index) => {
              const ratio = point.luminance_cd_m2 / max;
              const hue = 38 + ratio * 12;
              const light = 18 + ratio * 48;
              return (
                <i
                  key={`${lane}-${index}`}
                  title={`${point.luminance_cd_m2.toFixed(3)} cd/m²`}
                  style={{ background: `hsl(${hue} 88% ${light}%)` }}
                />
              );
            })}
        </div>
      ))}
    </div>
  );
}

function PolarPreview({ result }: { result: OptimizeResult }) {
  const { c_angles_deg: cAngles, gamma_angles_deg: gammaAngles, intensity_cd_per_klm: matrix } =
    result.photometry;
  const nearestRow = (target: number) => {
    let best = 0;
    let distance = Number.POSITIVE_INFINITY;
    cAngles.forEach((angle, index) => {
      const next = Math.abs(((angle - target + 180) % 360) - 180);
      if (next < distance) {
        best = index;
        distance = next;
      }
    });
    return matrix[best];
  };
  const maximum = Math.max(...matrix.flat(), 1);
  const curve = (rightC: number, leftC: number) => {
    const right = nearestRow(rightC);
    const left = nearestRow(leftC);
    const points: string[] = [];
    for (let index = gammaAngles.length - 1; index >= 0; index -= 1) {
      const gamma = (gammaAngles[index] * Math.PI) / 180;
      const radius = (left[index] / maximum) * 96;
      points.push(`${120 - radius * Math.sin(gamma)},${118 - radius * Math.cos(gamma)}`);
    }
    for (let index = 1; index < gammaAngles.length; index += 1) {
      const gamma = (gammaAngles[index] * Math.PI) / 180;
      const radius = (right[index] / maximum) * 96;
      points.push(`${120 + radius * Math.sin(gamma)},${118 - radius * Math.cos(gamma)}`);
    }
    return `M ${points.join(" L ")}`;
  };
  return (
    <svg
      className="polar"
      viewBox="0 0 240 150"
      role="img"
      aria-label="Curvas polares reales C0-C180 y C90-C270 del LDT final"
    >
      {[30, 60, 90].map((radius) => (
        <path
          key={radius}
          d={`M ${120 - radius} 118 A ${radius} ${radius} 0 0 1 ${120 + radius} 118`}
          fill="none"
          stroke="#d8d5ca"
          strokeWidth="1"
        />
      ))}
      <line x1="20" x2="220" y1="118" y2="118" stroke="#a7a59e" />
      <line x1="120" x2="120" y1="15" y2="124" stroke="#d8d5ca" />
      <path d={curve(0, 180)} fill="none" stroke="#e59a1d" strokeWidth="2.5" />
      <path d={curve(90, 270)} fill="none" stroke="#24495f" strokeWidth="2.2" />
      <g className="polar-legend">
        <line x1="42" x2="56" y1="139" y2="139" stroke="#e59a1d" strokeWidth="2.5" />
        <text x="60" y="142">C0–C180</text>
        <line x1="132" x2="146" y1="139" y2="139" stroke="#24495f" strokeWidth="2.5" />
        <text x="150" y="142">C90–C270</text>
      </g>
    </svg>
  );
}

function signedValue(
  value: number | null | undefined,
  digits: number,
  unit = "",
) {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${value >= 0 ? "+" : ""}${value.toFixed(digits)}${unit}`;
}

function AngularResidualHeatmap({
  residual,
}: {
  residual: PhysicalValidationResult["residual_map"];
}) {
  const maximumAbsolute = Math.max(
    Math.abs(residual.minimum_error_pct),
    Math.abs(residual.maximum_error_pct),
    1,
  );
  const color = (value: number) => {
    const intensity = Math.min(Math.abs(value) / maximumAbsolute, 1);
    if (value < 0) {
      return `hsl(207 62% ${96 - intensity * 54}%)`;
    }
    return `hsl(8 67% ${97 - intensity * 53}%)`;
  };

  return (
    <div className="residual-map-block">
      <div className="comparison-section-title">
        <strong>Mapa angular del error físico</strong>
        <span>I físico − I objetivo · % del pico objetivo</span>
      </div>
      <div className="residual-map-shell">
        <span className="residual-axis residual-axis-gamma">γ 90°</span>
        <div className="residual-map">
          {[...residual.gamma_angles_deg].reverse().map((gammaDeg) => {
            const gammaIndex = residual.gamma_angles_deg.indexOf(gammaDeg);
            return (
              <div
                key={gammaDeg}
                style={{
                  gridTemplateColumns: `repeat(${residual.c_angles_deg.length}, minmax(2px, 1fr))`,
                }}
              >
                {residual.c_angles_deg.map((cDeg, cIndex) => {
                  const value =
                    residual.error_pct_of_target_peak[cIndex][gammaIndex];
                  return (
                    <i
                      key={cDeg}
                      title={`C${cDeg.toFixed(0)}° · γ${gammaDeg.toFixed(
                        0,
                      )}° · ${signedValue(value, 2, " %")}`}
                      style={{ background: color(value) }}
                    />
                  );
                })}
              </div>
            );
          })}
        </div>
        <span className="residual-axis residual-axis-zero">γ 0°</span>
        <div className="residual-c-axis">
          <span>C0°</span>
          <span>C90°</span>
          <span>C180°</span>
          <span>C270°</span>
          <span>C360°</span>
        </div>
      </div>
      <div className="residual-legend">
        <span>
          <i className="under" />
          Déficit físico · aumentar en la siguiente iteración
        </span>
        <b>
          {signedValue(residual.minimum_error_pct, 1, " %")} /{" "}
          {signedValue(residual.maximum_error_pct, 1, " %")}
        </b>
        <span>
          Exceso físico · reducir en la siguiente iteración
          <i className="over" />
        </span>
      </div>
    </div>
  );
}

function PhysicalValidationPanel({
  validation,
  loading,
  error,
  onFile,
  correctionGain,
  onCorrectionGain,
  onDownloadCompensated,
  selectedC,
  profileLabel,
}: {
  validation: PhysicalValidationResult | null;
  loading: boolean;
  error: string;
  onFile: (event: ChangeEvent<HTMLInputElement>) => void;
  correctionGain: number;
  onCorrectionGain: (value: number) => void;
  onDownloadCompensated: () => void;
  selectedC: number;
  profileLabel: string;
}) {
  const metricRows = validation
    ? [
        {
          label: "Luminancia media",
          target: validation.target_metrics.luminance_avg_cd_m2,
          physical: validation.metrics.luminance_avg_cd_m2,
          delta: validation.metric_deltas.luminance_avg_cd_m2,
          digits: 3,
          unit: " cd/m²",
        },
        {
          label: "Uniformidad global Uo",
          target: validation.target_metrics.uo,
          physical: validation.metrics.uo,
          delta: validation.metric_deltas.uo,
          digits: 3,
          unit: "",
        },
        {
          label: "Uniformidad longitudinal Ul",
          target: validation.target_metrics.ul,
          physical: validation.metrics.ul,
          delta: validation.metric_deltas.ul,
          digits: 3,
          unit: "",
        },
        {
          label: "Incremento de umbral TI",
          target: validation.target_metrics.ti_pct,
          physical: validation.metrics.ti_pct,
          delta: validation.metric_deltas.ti_pct,
          digits: 2,
          unit: " %",
        },
        {
          label: "Relación de borde REI",
          target: validation.target_metrics.rei,
          physical: validation.metrics.rei,
          delta: validation.metric_deltas.rei,
          digits: 3,
          unit: "",
        },
      ].filter((row) => row.target != null && row.physical != null)
    : [];

  return (
    <div className="panel physical-validation-panel">
      <div className="physical-validation-head">
        <div className="panel-title">
          <Layers3 size={18} />
          <div>
            <strong>Validación del LDT físico</strong>
            <small>
              Photopia o medición · misma calle, disposición, flujo y factor de
              mantenimiento
            </small>
          </div>
        </div>
        <div className="physical-validation-actions">
          <label className="correction-gain">
            <span>
              Ganancia de corrección
              <b>{correctionGain.toFixed(2)}</b>
            </span>
            <input
              type="range"
              min="0.10"
              max="1"
              step="0.05"
              value={correctionGain}
              disabled={loading}
              onChange={(event) =>
                onCorrectionGain(Number(event.target.value))
              }
            />
          </label>
          <label className={`physical-upload ${loading ? "disabled" : ""}`}>
            {loading ? (
              <LoaderCircle className="spin" size={17} />
            ) : (
              <FileDown size={17} />
            )}
            {loading ? "Validando…" : "Cargar LDT físico"}
            <input
              type="file"
              accept=".ldt,text/plain"
              disabled={loading}
              onChange={onFile}
            />
          </label>
        </div>
      </div>

      {error && (
        <div className="physical-validation-error">
          <AlertTriangle size={17} />
          <span>{error}</span>
        </div>
      )}

      {validation &&
        Math.abs(
          correctionGain - validation.compensation.correction_gain,
        ) > 1e-6 && (
          <div className="correction-gain-note">
            <CircleHelp size={15} />
            <span>
              La comparación mostrada usa ganancia{" "}
              {validation.compensation.correction_gain.toFixed(2)}. Vuelve a
              cargar el mismo LDT para aplicar {correctionGain.toFixed(2)}.
            </span>
          </div>
        )}

      {!validation && !loading && (
        <div className="physical-validation-empty">
          <FileDown size={22} />
          <div>
            <strong>Compara la lente obtenida con el objetivo</strong>
            <span>
              El motor reimportará el fichero EULUMDAT y repetirá el cálculo
              completo sin alterar el LDT objetivo.
            </span>
          </div>
        </div>
      )}

      {loading && (
        <div className="physical-validation-empty is-loading">
          <LoaderCircle className="spin" size={22} />
          <div>
            <strong>Evaluando el LDT físico</strong>
            <span>Interpolando la fotometría y recalculando la vía…</span>
          </div>
        </div>
      )}

      {validation && (
        <>
          <div className="physical-validation-summary">
            <div>
              <small>FICHERO VALIDADO</small>
              <strong title={validation.filename}>{validation.filename}</strong>
              <span>
                Evaluado al flujo de instalación. Flujo declarado en fichero:{" "}
                {validation.photometry.declared_flux_lm?.toFixed(0) ?? "—"} lm
              </span>
            </div>
            <div
              className={`compliance-badge ${
                validation.compliant ? "pass" : "fail"
              }`}
            >
              {validation.compliant ? (
                <CheckCircle2 size={18} />
              ) : (
                <AlertTriangle size={18} />
              )}
              <span>
                <b>{validation.compliant ? "CUMPLE" : "NO CUMPLE"}</b>
                <small>{profileLabel}</small>
              </span>
            </div>
          </div>

          <div className="comparison-grid">
            <div>
              <small>ERROR DE FORMA RMSE</small>
              <strong>
                {validation.comparison.normalized_rmse_pct.toFixed(2)} %
              </strong>
              <span>Intensidades normalizadas</span>
            </div>
            <div>
              <small>CORRELACIÓN</small>
              <strong>
                {validation.comparison.shape_correlation.toFixed(4)}
              </strong>
              <span>1,0000 es coincidencia perfecta</span>
            </div>
            <div>
              <small>DESPLAZAMIENTO DEL PICO</small>
              <strong>
                {signedValue(
                  validation.comparison.peak_gamma_shift_deg,
                  1,
                  "° γ",
                )}
              </strong>
              <span>
                C{" "}
                {signedValue(
                  validation.comparison.peak_c_shift_deg,
                  1,
                  "°",
                )}
              </span>
            </div>
            <div>
              <small>ANCHURA DE CRESTA 90 %</small>
              <strong>
                {signedValue(
                  validation.comparison.gamma_width_90_delta_deg,
                  1,
                  "°",
                )}
              </strong>
              <span>
                Δ FWHM{" "}
                {signedValue(
                  validation.comparison.gamma_fwhm_delta_deg,
                  1,
                  "°",
                )}
              </span>
            </div>
          </div>

          <div className="metric-comparison-wrap">
            <div className="comparison-section-title">
              <strong>Efecto sobre la vía</strong>
              <span>Δ = LDT físico − LDT objetivo</span>
            </div>
            <div className="metric-comparison-table">
              <div className="metric-comparison-header">
                <span>Parámetro</span>
                <span>Objetivo</span>
                <span>Físico</span>
                <span>Δ</span>
              </div>
              {metricRows.map((row) => (
                <div key={row.label}>
                  <strong>{row.label}</strong>
                  <span>
                    {Number(row.target).toFixed(row.digits)}
                    {row.unit}
                  </span>
                  <span>
                    {Number(row.physical).toFixed(row.digits)}
                    {row.unit}
                  </span>
                  <b>
                    {signedValue(
                      row.delta,
                      row.digits,
                      row.unit,
                    )}
                  </b>
                </div>
              ))}
            </div>
          </div>

          <div className="physical-descriptors">
            <div>
              <small>PICO FÍSICO</small>
              <strong>
                C{validation.photometry.peak_c_deg?.toFixed(1) ?? "—"}° · γ
                {validation.photometry.peak_gamma_deg?.toFixed(1) ?? "—"}°
              </strong>
            </div>
            <div>
              <small>CRESTA / FWHM</small>
              <strong>
                {validation.photometry.gamma_width_90_deg?.toFixed(1) ?? "—"}° /{" "}
                {validation.photometry.gamma_fwhm_deg?.toFixed(1) ?? "—"}°
              </strong>
            </div>
            <div>
              <small>FLUJO A ÁNGULO ALTO</small>
              <strong>
                {validation.photometry.high_angle_flux_fraction != null
                  ? `${(
                      validation.photometry.high_angle_flux_fraction * 100
                    ).toFixed(2)} %`
                  : "—"}
              </strong>
            </div>
            <div>
              <small>FLUJO SUPERIOR</small>
              <strong>
                {validation.photometry.upward_flux_fraction != null
                  ? `${(
                      validation.photometry.upward_flux_fraction * 100
                    ).toFixed(3)} %`
                  : "—"}
              </strong>
            </div>
            <div>
              <small>ERROR DE SIMETRÍA</small>
              <strong>
                {validation.photometry.longitudinal_symmetry_error_pct?.toFixed(
                  3,
                ) ?? "—"}{" "}
                %
              </strong>
            </div>
          </div>

          <AngularResidualHeatmap residual={validation.residual_map} />

          <div className="compensation-panel">
            <div className="compensation-copy">
              <small>SIGUIENTE ITERACIÓN ÓPTICA</small>
              <strong>LDT objetivo precompensado</strong>
              <p>
                Corrige el {(
                  validation.compensation.correction_gain * 100
                ).toFixed(0)} % del residual medido, con{" "}
                {validation.compensation.smoothing_passes} pasadas de
                regularización, simetría longitudinal y flujo integrado
                conservado.
              </p>
              <div className="compensation-stats">
                <span>
                  <small>AJUSTE MÁXIMO</small>
                  <b>
                    {validation.compensation.maximum_adjustment_pct_of_target_peak.toFixed(
                      1,
                    )}{" "}
                    %
                  </b>
                </span>
                <span>
                  <small>PRE-DISTORSIÓN RMSE</small>
                  <b>
                    {validation.compensation.pre_distortion_rmse_pct.toFixed(
                      2,
                    )}{" "}
                    %
                  </b>
                </span>
                <span>
                  <small>RECORTE A CERO</small>
                  <b>
                    {(
                      validation.compensation.clipped_low_fraction * 100
                    ).toFixed(2)}{" "}
                    %
                  </b>
                </span>
                <span>
                  <small>FLUJO INTEGRADO</small>
                  <b>
                    {validation.compensation.integrated_flux_lm_per_klm.toFixed(
                      1,
                    )}{" "}
                    lm/klm
                  </b>
                </span>
              </div>
              <span className="compensation-note">
                Hipótesis de error aditivo: después de simular la nueva lente,
                vuelve a cargar su LDT para medir la convergencia real.
              </span>
              {validation.compensation
                .maximum_adjustment_pct_of_target_peak > 100 && (
                <span className="compensation-warning">
                  El LDT físico está muy alejado del objetivo en alguna zona
                  angular. Usa este fichero como una iteración conservadora y
                  comprueba el siguiente resultado antes de aumentar la
                  ganancia.
                </span>
              )}
            </div>
            <button
              type="button"
              className="primary-button compensation-download"
              onClick={onDownloadCompensated}
            >
              <Download size={17} />
              Descargar objetivo corregido
            </button>
          </div>

          {validation.failures.length > 0 && (
            <div className="physical-failures">
              <AlertTriangle size={16} />
              <div>
                <strong>Límites incumplidos</strong>
                <span>{validation.failures.join(" · ")}</span>
              </div>
            </div>
          )}

          <div className="physical-ldt-viewer">
            <div className="comparison-section-title">
              <strong>Cuerpo fotométrico físico</strong>
              <span>
                C {validation.photometry.c_step_deg ?? "—"}° · γ{" "}
                {validation.photometry.gamma_step_deg ?? "—"}°
              </span>
            </div>
            <Ldt3DViewer
              photometry={validation.photometry}
              selectedC={selectedC}
            />
          </div>
        </>
      )}
    </div>
  );
}

export default function Home() {
  const [form, setForm] = useState<FormState>(INITIAL_FORM);
  const [activeStep, setActiveStep] = useState(0);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState<OptimizeResult | null>(null);
  const [physicalValidation, setPhysicalValidation] =
    useState<PhysicalValidationResult | null>(null);
  const [validatingPhysical, setValidatingPhysical] = useState(false);
  const [physicalValidationError, setPhysicalValidationError] = useState("");
  const [correctionGain, setCorrectionGain] = useState(0.6);
  const [selectedC, setSelectedC] = useState(0);
  const [engineStatus, setEngineStatus] = useState<
    "checking" | "connected" | "offline"
  >("checking");
  const roadWidth = useMemo(
    () => form.laneWidths.reduce((sum, value) => sum + value, 0),
    [form.laneWidths],
  );
  const isCustomClass = form.lightingClass === "CUSTOM";
  const target = isCustomClass
    ? {
        l: form.customLavg,
        uo: form.customUo,
        ul: form.customUl,
        ti: form.customTi,
        rei: form.customRei,
      }
    : CLASS_DATA[form.lightingClass] ?? CLASS_DATA.M4;

  useEffect(() => {
    let active = true;
    let controller: AbortController | null = null;
    let timeout: number | null = null;

    const checkEngine = () => {
      controller?.abort();
      const requestController = new AbortController();
      controller = requestController;
      const requestTimeout = window.setTimeout(
        () => requestController.abort(),
        2500,
      );
      timeout = requestTimeout;
      fetch(`${ENGINE_URL}/api/health`, {
        signal: requestController.signal,
        cache: "no-store",
      })
        .then((response) => {
          if (!response.ok) throw new Error("Motor no disponible");
          if (active) setEngineStatus("connected");
        })
        .catch(() => {
          if (active) setEngineStatus("offline");
        })
        .finally(() => {
          window.clearTimeout(requestTimeout);
          if (timeout === requestTimeout) timeout = null;
        });
    };

    checkEngine();
    const interval = window.setInterval(checkEngine, 4000);
    window.addEventListener("focus", checkEngine);
    return () => {
      active = false;
      controller?.abort();
      if (timeout != null) window.clearTimeout(timeout);
      window.clearInterval(interval);
      window.removeEventListener("focus", checkEngine);
    };
  }, []);

  const update = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((current) => ({ ...current, [key]: value }));

  const payload = () => ({
    project_name: form.projectName,
    geometry: {
      lane_widths_m: form.laneWidths,
      calculation_length_m: form.spacing,
      longitudinal_points: 10,
      transverse_points_per_lane: 3,
      r_table: form.rTable,
      sidewalk_left_m: form.sidewalkLeft,
      sidewalk_right_m: form.sidewalkRight,
      sidewalk_target_min_lx: form.sidewalkTarget || null,
      building_left_enabled: form.evaluateIntrusion && form.buildingSide === "left",
      building_right_enabled: form.evaluateIntrusion && form.buildingSide === "right",
      [`building_${form.buildingSide}_setback_m`]: form.buildingSetback,
      [`building_${form.buildingSide}_height_m`]: form.buildingHeight,
      facade_limit_lx: form.facadeLimit,
      window_limit_lx: form.windowLimit,
    },
    installation: {
      arrangement_type: form.arrangement,
      unilateral_side: form.unilateralSide,
      spacing_m: form.spacing,
      mounting_height_m: form.height,
      flux_lm: form.flux,
      pole_setback_m: form.setback,
      overhang_m: form.overhang,
      tilt_deg: form.tilt,
    },
    requirements: {
      lighting_class: form.lightingClass,
      custom_targets: {
        luminance_avg_min_cd_m2: form.customLavg,
        uo_min: form.customUo,
        ul_min: form.customUl,
        ti_max_pct: form.customTi,
        rei_min: form.customRei,
      },
      maintenance_factor: form.maintenanceFactor,
      include_rei: form.includeRei,
      evaluate_intrusion: form.evaluateIntrusion,
      facade_limit_lx: form.facadeLimit,
      window_limit_lx: form.windowLimit,
    },
    optimizer: { max_candidates: form.candidates },
  });

  const runOptimization = async () => {
    if (engineStatus !== "connected") {
      window.alert(
        "El motor fotométrico no está conectado. Ejecuta arrancar_road_ldt.bat y vuelve a intentarlo.",
      );
      return;
    }
    setRunning(true);
    setResult(null);
    setPhysicalValidation(null);
    setPhysicalValidationError("");
    setActiveStep(3);
    setProgress(8);
    const timer = window.setInterval(
      () => setProgress((value) => Math.min(92, value + 7)),
      260,
    );
    try {
      const response = await fetch(`${ENGINE_URL}/api/optimize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload()),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.message || "No se pudo optimizar");
      const responseData: OptimizeResult = body;
      setProgress(100);
      setResult(responseData);
      setSelectedC(responseData.photometry.peak_c_deg ?? 0);
      window.setTimeout(() => setActiveStep(4), 320);
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "Error de optimización");
    } finally {
      window.clearInterval(timer);
      setRunning(false);
    }
  };

  const validatePhysicalLdt = async (
    event: ChangeEvent<HTMLInputElement>,
  ) => {
    const input = event.currentTarget;
    const file = input.files?.[0];
    input.value = "";
    if (!file || !result) return;
    if (engineStatus !== "connected") {
      setPhysicalValidationError(
        "El motor fotométrico debe estar conectado para validar el LDT.",
      );
      return;
    }
    if (file.size > 8 * 1024 * 1024) {
      setPhysicalValidationError("El fichero LDT supera el límite de 8 MB.");
      return;
    }

    setValidatingPhysical(true);
    setPhysicalValidation(null);
    setPhysicalValidationError("");
    try {
      const physicalText = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result ?? ""));
        reader.onerror = () => reject(new Error("No se pudo leer el fichero LDT"));
        reader.readAsText(file, "windows-1252");
      });
      const response = await fetch(`${ENGINE_URL}/api/validate-ldt`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...payload(),
          physical_filename: file.name,
          physical_ldt_text: physicalText,
          target_ldt_text: result.ldt_text,
          correction_gain: correctionGain,
        }),
      });
      const body = await response.json();
      if (!response.ok) {
        throw new Error(body.message || "No se pudo validar el LDT físico");
      }
      setPhysicalValidation(body);
    } catch (error) {
      setPhysicalValidationError(
        error instanceof Error ? error.message : "Error de validación",
      );
    } finally {
      setValidatingPhysical(false);
    }
  };

  const downloadLdt = () => {
    if (!result) return;
    const blob = new Blob([result.ldt_text], { type: "text/plain;charset=iso-8859-1" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `${form.projectName.replace(/[^a-z0-9]+/gi, "_")}.ldt`;
    link.click();
    URL.revokeObjectURL(link.href);
  };

  const downloadCompensatedLdt = () => {
    if (!physicalValidation) return;
    const blob = new Blob([physicalValidation.compensation.ldt_text], {
      type: "text/plain;charset=iso-8859-1",
    });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = physicalValidation.compensation.filename;
    link.click();
    URL.revokeObjectURL(link.href);
  };

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">S</span>
          <div><strong>SALVI STUDIO</strong><small>ROAD · LDT DESIGNER</small></div>
        </div>
        <div className="project-title">
          <input
            value={form.projectName}
            onChange={(event) => update("projectName", event.target.value)}
            aria-label="Nombre del proyecto"
          />
          <span>Guardado localmente</span>
        </div>
        <div className="standard-context">
          <ShieldCheck size={16} />
          <span><small>NORMA ACTIVA</small><b>EN 13201:2015</b></span>
        </div>
        <div className="top-actions">
          <span className={`engine-pill ${engineStatus === "connected" ? "live" : ""}`}>
            <i />{" "}
            {engineStatus === "connected"
              ? "Motor conectado"
              : engineStatus === "checking"
                ? "Comprobando motor"
                : "Motor desconectado"}
          </span>
          <button className="language-button" title="Idioma"><Languages size={15} /> ES</button>
          <button className="icon-button" title="Ayuda"><CircleHelp size={17} /></button>
          <button className="user-button" title="Usuario"><UserRound size={15} /></button>
        </div>
      </header>

      <aside className="sidebar">
        <div className="module-context">
          <span>SR</span>
          <div><small>MÓDULO ACTIVO</small><b>SALVI Road</b></div>
        </div>
        <div className="workflow-label">PROYECTO · FLUJO DE DISEÑO</div>
        <nav>
          {STEPS.map((step, index) => {
            const Icon = step.icon;
            const done = index < activeStep || (index === 4 && result);
            return (
              <button
                key={step.label}
                className={`${activeStep === index ? "active" : ""} ${done ? "done" : ""}`}
                onClick={() => setActiveStep(index)}
                disabled={index === 4 && !result}
              >
                <span>{done ? <Check size={16} /> : <Icon size={17} />}</span>
                <b>{step.label}</b>
                <small>0{index + 1}</small>
              </button>
            );
          })}
        </nav>
        <div className="sidebar-note">
          <Waypoints size={20} />
          <strong>EN 13201:2015</strong>
          <span>Motor viario independiente · v0.1</span>
        </div>
      </aside>

      <section className="workspace">
        <div className="content-column">
          {activeStep === 0 && (
            <>
              <div className="section-heading">
                <span>PASO 01</span>
                <h1>Define la sección de la vía</h1>
                <p>Cada zona se incorpora a su malla de cálculo correspondiente.</p>
              </div>
              <div className="panel">
                <div className="panel-title"><Map size={18} /><div><strong>Calzada</strong><small>{roadWidth.toFixed(1)} m totales</small></div></div>
                <div className="lane-list">
                  {form.laneWidths.map((width, index) => (
                    <div className="lane-row" key={index}>
                      <span className="lane-index">{index + 1}</span>
                      <b>Carril {index + 1}</b>
                      <div className="input-wrap compact">
                        <input
                          type="number"
                          value={width}
                          step=".1"
                          onChange={(event) => {
                            const widths = [...form.laneWidths];
                            widths[index] = Number(event.target.value);
                            update("laneWidths", widths);
                          }}
                        />
                        <em>m</em>
                      </div>
                      {form.laneWidths.length > 1 && (
                        <button
                          className="remove-lane"
                          onClick={() =>
                            update("laneWidths", form.laneWidths.filter((_, i) => i !== index))
                          }
                        >×</button>
                      )}
                    </div>
                  ))}
                </div>
                <button
                  className="text-button"
                  onClick={() => update("laneWidths", [...form.laneWidths, 3.5])}
                >+ Añadir carril</button>
              </div>
              <div className="panel">
                <div className="panel-title"><Layers3 size={18} /><div><strong>Bandas laterales</strong><small>Aceras y zonas de borde</small></div></div>
                <div className="form-grid two">
                  <Field label="Acera izquierda" value={form.sidewalkLeft} onChange={(v) => update("sidewalkLeft", v)} unit="m" min={0} />
                  <Field label="Acera derecha" value={form.sidewalkRight} onChange={(v) => update("sidewalkRight", v)} unit="m" min={0} />
                  <Field label="Iluminancia mínima" value={form.sidewalkTarget} onChange={(v) => update("sidewalkTarget", v)} unit="lx" min={0} />
                  <label className="field">
                    <span>Tabla de pavimento</span>
                    <div className="select-wrap">
                      <select value={form.rTable} onChange={(e) => update("rTable", e.target.value)}>
                        {["R1", "R2", "R3", "R4"].map((item) => <option key={item}>{item}</option>)}
                      </select>
                      <ChevronDown size={15} />
                    </div>
                  </label>
                </div>
              </div>
            </>
          )}

          {activeStep === 1 && (
            <>
              <div className="section-heading">
                <span>PASO 02</span>
                <h1>Configura la instalación</h1>
                <p>La geometría se repetirá como una celda longitudinal periódica.</p>
              </div>
              <div className="panel">
                <div className="panel-title"><Waypoints size={18} /><div><strong>Disposición</strong><small>Selecciona el patrón base</small></div></div>
                <div className="arrangement-grid">
                  {ARRANGEMENTS.map((item) => (
                    <button
                      key={item.id}
                      className={form.arrangement === item.id ? "selected" : ""}
                      onClick={() => update("arrangement", item.id)}
                    >
                      <span>{item.glyph}</span><b>{item.label}</b>
                      {form.arrangement === item.id && <CheckCircle2 size={16} />}
                    </button>
                  ))}
                </div>
                {form.arrangement === "unilateral" && (
                  <div className="segmented">
                    <button className={form.unilateralSide === "left" ? "active" : ""} onClick={() => update("unilateralSide", "left")}>Lado izquierdo</button>
                    <button className={form.unilateralSide === "right" ? "active" : ""} onClick={() => update("unilateralSide", "right")}>Lado derecho</button>
                  </div>
                )}
              </div>
              <div className="panel">
                <div className="panel-title"><Lightbulb size={18} /><div><strong>Luminaria y soporte</strong><small>Centro fotométrico y brazo</small></div></div>
                <div className="form-grid three">
                  <Field label="Interdistancia" value={form.spacing} onChange={(v) => update("spacing", v)} unit="m" min={5} />
                  <Field label="Altura" value={form.height} onChange={(v) => update("height", v)} unit="m" min={2} />
                  <Field label="Flujo útil" value={form.flux} onChange={(v) => update("flux", v)} unit="lm" min={1000} step={100} />
                  <Field label="Retranqueo poste" value={form.setback} onChange={(v) => update("setback", v)} unit="m" min={0} />
                  <Field label="Longitud de brazo" value={form.overhang} onChange={(v) => update("overhang", v)} unit="m" min={0} />
                  <Field label="Inclinación" value={form.tilt} onChange={(v) => update("tilt", v)} unit="°" step={0.5} />
                </div>
              </div>
            </>
          )}

          {activeStep === 2 && (
            <>
              <div className="section-heading">
                <span>PASO 03</span>
                <h1>Fija los requisitos</h1>
                <p>La clase define las restricciones duras de la optimización.</p>
              </div>
              <div className="panel">
                <div className="panel-title"><Gauge size={18} /><div><strong>Clase luminotécnica</strong><small>{isCustomClass ? "Objetivos definidos por el usuario" : "EN 13201-2:2015 · calzada seca"}</small></div></div>
                <div className="class-grid">
                  {[...Object.keys(CLASS_DATA), "CUSTOM"].map((item) => (
                    <button
                      key={item}
                      className={`${form.lightingClass === item ? "selected" : ""} ${item === "CUSTOM" ? "custom-class" : ""}`}
                      onClick={() => update("lightingClass", item)}
                    >
                      <b>{item}</b>
                      <span>
                        {item === "CUSTOM"
                          ? "Valores manuales"
                          : `${CLASS_DATA[item].l.toFixed(2)} cd/m²`}
                      </span>
                    </button>
                  ))}
                </div>
                {isCustomClass && (
                  <div className="custom-targets-editor">
                    <div>
                      <SlidersHorizontal size={16} />
                      <span>
                        <strong>Límites personalizados</strong>
                        <small>
                          Se usarán como restricciones duras del optimizador.
                        </small>
                      </span>
                    </div>
                    <div className="custom-target-grid">
                      <Field
                        label="Luminancia media mínima"
                        value={form.customLavg}
                        onChange={(value) => update("customLavg", value)}
                        unit="cd/m²"
                        min={0.05}
                        step={0.05}
                        info="lavg"
                      />
                      <Field
                        label="Uo mínima"
                        value={form.customUo}
                        onChange={(value) => update("customUo", value)}
                        min={0}
                        max={1}
                        step={0.01}
                        info="uo"
                      />
                      <Field
                        label="Ul mínima"
                        value={form.customUl}
                        onChange={(value) => update("customUl", value)}
                        min={0}
                        max={1}
                        step={0.01}
                        info="ul"
                      />
                      <Field
                        label="TI máximo"
                        value={form.customTi}
                        onChange={(value) => update("customTi", value)}
                        unit="%"
                        min={0}
                        step={0.5}
                        info="ti"
                      />
                      <Field
                        label="REI mínimo"
                        value={form.customRei}
                        onChange={(value) => update("customRei", value)}
                        min={0}
                        step={0.01}
                        info="rei"
                      />
                    </div>
                    {!form.includeRei && (
                      <small className="custom-target-note">
                        El valor REI se conserva, pero no se evaluará mientras
                        la iluminación de borde esté desactivada.
                      </small>
                    )}
                  </div>
                )}
                <div className="requirements-strip">
                  <RequirementMetric label="Lavg ≥" value={target.l.toFixed(2)} metric="lavg" />
                  <RequirementMetric label="Uo ≥" value={target.uo.toFixed(2)} metric="uo" />
                  <RequirementMetric label="Ul ≥" value={target.ul.toFixed(2)} metric="ul" />
                  <RequirementMetric label="TI ≤" value={`${target.ti}%`} metric="ti" />
                  <RequirementMetric label="REI ≥" value={target.rei.toFixed(2)} metric="rei" />
                </div>
              </div>
              <div className="panel">
                <div className="panel-title"><SlidersHorizontal size={18} /><div><strong>Alcance de evaluación</strong><small>Activa solo lo necesario</small></div></div>
                <div className="option-stack">
                  <Toggle
                    checked={form.includeRei}
                    onChange={(v) => update("includeRei", v)}
                    label="Evaluar iluminación de borde REI"
                    detail="Desactívalo si las áreas adyacentes tienen requisitos propios."
                  />
                  <Toggle
                    checked={form.evaluateIntrusion}
                    onChange={(v) => update("evaluateIntrusion", v)}
                    label="Evaluar fachadas, ventanas e intrusión"
                    detail="Genera mallas verticales y añade sus límites al cumplimiento."
                  />
                </div>
                <div className="form-grid two maintenance-row">
                  <Field label="Factor de mantenimiento" value={form.maintenanceFactor} onChange={(v) => update("maintenanceFactor", v)} min={0.1} step={0.05} />
                </div>
              </div>
              {form.evaluateIntrusion && (
                <div className="panel intrusion-panel">
                  <div className="panel-title"><Building2 size={18} /><div><strong>Edificio colindante</strong><small>Evaluación opcional activada</small></div></div>
                  <div className="segmented">
                    <button className={form.buildingSide === "left" ? "active" : ""} onClick={() => update("buildingSide", "left")}>Izquierda</button>
                    <button className={form.buildingSide === "right" ? "active" : ""} onClick={() => update("buildingSide", "right")}>Derecha</button>
                  </div>
                  <div className="form-grid two">
                    <Field label="Retranqueo fachada" value={form.buildingSetback} onChange={(v) => update("buildingSetback", v)} unit="m" min={0} />
                    <Field label="Altura fachada" value={form.buildingHeight} onChange={(v) => update("buildingHeight", v)} unit="m" min={1} />
                    <Field label="Límite fachada" value={form.facadeLimit} onChange={(v) => update("facadeLimit", v)} unit="lx" min={0} />
                    <Field label="Límite ventanas" value={form.windowLimit} onChange={(v) => update("windowLimit", v)} unit="lx" min={0} />
                  </div>
                </div>
              )}
            </>
          )}

          {activeStep === 3 && (
            <>
              <div className="section-heading">
                <span>PASO 04</span>
                <h1>Diseña la distribución</h1>
                <p>Exploración progresiva de una familia fotométrica simétrica.</p>
              </div>
              <div className="panel optimization-panel">
                <div className="optimization-hero">
                  <span><Sparkles size={26} /></span>
                  <div>
                    <strong>{running ? "Optimizando LDT…" : result ? "Optimización terminada" : "Preparado para optimizar"}</strong>
                    <small>{form.candidates} candidatos · salida angular 1° × 1°</small>
                  </div>
                </div>
                <div className="resolution-flow">
                  {[
                    ["Gruesa", "C 10° · γ 5°", 25],
                    ["Media", "C 5° · γ 2,5°", 55],
                    ["Fina", "C 2,5° · γ 1°", 82],
                    ["Exportación", "C 1° · γ 1°", 100],
                  ].map(([name, detail, threshold], index) => (
                    <div className={progress >= Number(threshold) ? "done" : progress > (index * 25) ? "active" : ""} key={String(name)}>
                      <i>{progress >= Number(threshold) ? <Check size={14} /> : index + 1}</i>
                      <span><b>{name}</b><small>{detail}</small></span>
                    </div>
                  ))}
                </div>
                <div className="progress-track"><i style={{ width: `${progress}%` }} /></div>
                <div className="optimizer-controls">
                  <Field label="Presupuesto de candidatos" value={form.candidates} onChange={(v) => update("candidates", Math.round(v))} min={3} step={1} />
                  <button
                    className="primary-button large"
                    disabled={running || engineStatus !== "connected"}
                    onClick={runOptimization}
                  >
                    {running ? <LoaderCircle className="spin" size={18} /> : <Play size={17} />}
                    {running ? "Calculando…" : result ? "Optimizar de nuevo" : "Iniciar optimización"}
                  </button>
                </div>
                {engineStatus !== "connected" && (
                  <div className="demo-callout">
                    <AlertTriangle size={17} />
                    <span>
                      {engineStatus === "checking"
                        ? "Comprobando la conexión con el motor fotométrico…"
                        : "Para calcular resultados reales, ejecuta arrancar_road_ldt.bat. La aplicación no genera resultados simulados."}
                    </span>
                    {engineStatus === "offline" && (
                      <button type="button" onClick={() => window.location.reload()}>
                        Reintentar conexión
                      </button>
                    )}
                  </div>
                )}
              </div>
            </>
          )}

          {activeStep === 4 && result && (
            <>
              <div className="section-heading results-heading">
                <div>
                  <span>PASO 05</span>
                  <h1>Resultado fotométrico</h1>
                  <p>{result.optimizer.evaluated_candidates} candidatos evaluados y LDT reimportado.</p>
                </div>
                <div className={`compliance-badge ${result.compliant ? "pass" : "fail"}`}>
                  {result.compliant ? <CheckCircle2 size={20} /> : <AlertTriangle size={20} />}
                  <span>
                    <b>{result.compliant ? "CUMPLE" : "NO CUMPLE"}</b>
                    <small>
                      {isCustomClass
                        ? "CUSTOM · objetivos personalizados"
                        : `${form.lightingClass} · EN 13201`}
                    </small>
                  </span>
                </div>
              </div>
              <div className="metrics-grid">
                <MetricCard label="Luminancia media" value={`${result.metrics.luminance_avg_cd_m2.toFixed(3)} cd/m²`} target={`mín. ${target.l.toFixed(2)}`} pass={result.metrics.luminance_avg_cd_m2 >= target.l} info="lavg" />
                <MetricCard label="Uniformidad global" value={result.metrics.uo.toFixed(3)} target={`mín. ${target.uo.toFixed(2)}`} pass={result.metrics.uo >= target.uo} info="uo" />
                <MetricCard label="Uniformidad long." value={result.metrics.ul.toFixed(3)} target={`mín. ${target.ul.toFixed(2)}`} pass={result.metrics.ul >= target.ul} info="ul" />
                <MetricCard label="Incremento TI" value={`${result.metrics.ti_pct.toFixed(2)} %`} target={`máx. ${target.ti}%`} pass={result.metrics.ti_pct <= target.ti} info="ti" />
                {form.includeRei && result.metrics.rei !== null && (
                  <MetricCard label="Relación de borde" value={result.metrics.rei.toFixed(3)} target={`mín. ${target.rei.toFixed(2)}`} pass={result.metrics.rei >= target.rei} info="rei" />
                )}
                {form.evaluateIntrusion && result.metrics.intrusion_max_lx != null && (
                  <MetricCard label="Intrusión máxima" value={`${result.metrics.intrusion_max_lx.toFixed(2)} lx`} target={`máx. ${form.facadeLimit} lx`} pass={result.metrics.intrusion_max_lx <= form.facadeLimit} info="intrusion" />
                )}
              </div>
              <div className="result-panels">
                <div className="panel visual-panel">
                  <div className="panel-title"><Map size={18} /><div><strong>Mapa de luminancias</strong><small>Observador crítico</small></div></div>
                  <Heatmap result={result} />
                  <div className="heat-legend"><span>mínimo</span><i /><span>máximo</span></div>
                </div>
                <div className="panel visual-panel">
                  <div className="panel-title">
                    <SunMedium size={18} />
                    <div>
                      <strong>Distribución polar</strong>
                      <small>
                        Máx. C{result.photometry.peak_c_deg?.toFixed(0) ?? "—"}° /
                        γ{result.photometry.peak_gamma_deg?.toFixed(0) ?? "—"}° ·
                        cresta 90% {result.photometry.gamma_width_90_deg?.toFixed(0) ?? "—"}° ·
                        FWHM {result.photometry.gamma_fwhm_deg?.toFixed(0) ?? "—"}°
                      </small>
                    </div>
                  </div>
                  <PolarPreview result={result} />
                </div>
              </div>
              <div className="ldt-analysis-grid">
                <div className="panel visual-panel ldt-3d-panel">
                  <div className="panel-title">
                    <Layers3 size={18} />
                    <div>
                      <strong>Cuerpo fotométrico tridimensional</strong>
                      <small>
                        Superficie I(C,γ) del fichero final · C {result.photometry.c_step_deg ?? 1}° · γ {result.photometry.gamma_step_deg ?? 1}°
                      </small>
                    </div>
                  </div>
                  <Ldt3DViewer
                    photometry={result.photometry}
                    selectedC={selectedC}
                  />
                </div>
                <div className="panel visual-panel ldt-section-panel">
                  <div className="panel-title">
                    <SunMedium size={18} />
                    <div>
                      <strong>Cortes fotométricos por plano C</strong>
                      <small>
                        Diagrama polar I(γ) sincronizado con el cuerpo 3D
                      </small>
                    </div>
                  </div>
                  <LdtSectionViewer
                    target={result.photometry}
                    physical={physicalValidation?.photometry}
                    compensated={physicalValidation?.compensation.photometry}
                    selectedC={selectedC}
                    peakC={result.photometry.peak_c_deg}
                    onSelectedC={setSelectedC}
                  />
                </div>
              </div>
              <PhysicalValidationPanel
                validation={physicalValidation}
                loading={validatingPhysical}
                error={physicalValidationError}
                onFile={validatePhysicalLdt}
                correctionGain={correctionGain}
                onCorrectionGain={setCorrectionGain}
                onDownloadCompensated={downloadCompensatedLdt}
                selectedC={selectedC}
                profileLabel={
                  isCustomClass
                    ? "LDT físico · objetivos CUSTOM"
                    : `LDT físico · ${form.lightingClass} · EN 13201`
                }
              />
              <div className="panel export-panel">
                <div>
                  <span className="file-icon"><FileDown size={24} /></span>
                  <div><strong>LDT objetivo listo</strong><small>Tabla completa · C 1° · γ 1° · simetría longitudinal validada</small></div>
                </div>
                <button className="primary-button" onClick={downloadLdt}><Download size={17} /> Descargar .LDT</button>
              </div>
            </>
          )}

          <div className="step-footer">
            <button
              className="secondary-button"
              disabled={activeStep === 0}
              onClick={() => setActiveStep((value) => Math.max(0, value - 1))}
            ><ArrowLeft size={16} /> Anterior</button>
            {activeStep < 3 && (
              <button className="primary-button" onClick={() => setActiveStep((value) => value + 1)}>
                Continuar <ArrowRight size={16} />
              </button>
            )}
            {activeStep === 3 && !running && (
              <button className="secondary-button" onClick={() => {
                setForm(INITIAL_FORM);
                setResult(null);
                setPhysicalValidation(null);
                setPhysicalValidationError("");
                setCorrectionGain(0.6);
                setSelectedC(0);
                setProgress(0);
              }}>
                <RotateCcw size={16} /> Restablecer
              </button>
            )}
          </div>
        </div>

        <aside className="preview-column">
          <div className="canvas-heading">
            <span>MAIN CANVAS</span>
            <div>
              <b>Sección y disposición</b>
              <small>Vista técnica vinculada a los parámetros</small>
            </div>
          </div>
          <StreetPreview form={form} />
          <div className={`decision-card ${result ? (result.compliant ? "pass" : "fail") : "pending"}`}>
            <div className="decision-card-head">
              <span><ShieldCheck size={18} /></span>
              <div><small>DECISIÓN TÉCNICA</small><b>{result ? (result.compliant ? "Cumple la clase requerida" : "Requiere ajustes") : "Pendiente de cálculo"}</b></div>
            </div>
            <p>
              {result
                ? result.compliant
                  ? isCustomClass
                    ? "La solución satisface todos los objetivos personalizados definidos."
                    : `La solución satisface ${form.lightingClass} según EN 13201 con la versión actual del cálculo.`
                  : `La solución no satisface todos los límites de ${form.lightingClass}.`
                : "Completa la geometría, la instalación y los requisitos antes de ejecutar la optimización."}
            </p>
            <div className="recommended-action">
              <small>ACCIÓN RECOMENDADA</small>
              <b>{result ? (result.compliant ? "Validar el LDT y preparar la óptica" : "Revisar interdistancia, altura o flujo") : "Continuar con el flujo de proyecto"}</b>
            </div>
          </div>
          <div className="summary-card">
            <div className="summary-title"><span>RESUMEN DEL PROYECTO</span><SlidersHorizontal size={16} /></div>
            <dl>
              <div><dt>Calzada</dt><dd>{form.laneWidths.length} carriles · {roadWidth.toFixed(1)} m</dd></div>
              <div><dt>Disposición</dt><dd>{ARRANGEMENTS.find((item) => item.id === form.arrangement)?.label}</dd></div>
              <div><dt>Montaje</dt><dd>{form.height} m · {form.spacing} m</dd></div>
              <div><dt>Clase</dt><dd><b>{form.lightingClass}</b> · {target.l.toFixed(2)} cd/m²</dd></div>
              <div><dt>Intrusión</dt><dd>{form.evaluateIntrusion ? "Activada" : "No evaluada"}</dd></div>
            </dl>
            <div className="symmetry-note"><Waypoints size={16} /><span><b>Simetría longitudinal</b>Plano perpendicular a la vía</span></div>
          </div>
        </aside>
      </section>
      <footer className="context-bar">
        <span className="context-status"><i /> Sin errores críticos</span>
        <span>Unidades: SI</span>
        <span>Cálculo: Road LDT Engine v0.1</span>
        <span>Simetría longitudinal activa</span>
        <button><Bot size={16} /> Asistente contextual</button>
      </footer>
    </main>
  );
}
