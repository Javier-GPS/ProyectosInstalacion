import {
  normalize,
  scoreCandidate,
  tokenizeWithSeparators,
  type MatchScore,
} from './tramosExcelMatching';

const loadXlsx = () => import('xlsx');

export type TramoParamType = 'number' | 'integer' | 'text' | 'enum';

export interface TramoParamDef {
  key: string;
  label: string;
  type: TramoParamType;
  required?: boolean;
  enumValues?: string[];
  /** Optional alias the FE uses when persisting (e.g. arm_length -> armLength). */
  aliases?: string[];
  /** Bilingual synonyms used by the auto-mapper. */
  synonyms?: string[];
  group: 'identification' | 'road' | 'luminaire' | 'optics' | 'conditions';
  description?: string;
}

export const TRAMO_PARAM_DEFS: TramoParamDef[] = [
  {
    key: 'name',
    label: 'Nombre del tramo',
    type: 'text',
    required: false,
    group: 'identification',
    synonyms: ['name', 'nombre', 'tramo', 'section', 'seccion', 'id', 'identifier', 'identificador'],
    description: 'Si no se mapea, se generará "Tramo N" automáticamente.',
  },
  {
    key: 'description',
    label: 'Descripción',
    type: 'text',
    group: 'identification',
    synonyms: ['description', 'descripcion', 'desc', 'notas', 'notes', 'comentarios', 'comments', 'observaciones', 'remarks'],
  },
  {
    key: 'road_width',
    label: 'Anchura de calzada',
    type: 'number',
    required: true,
    group: 'road',
    synonyms: [
      'anchura de calzada', 'ancho de calzada', 'anchura calzada', 'ancho calzada',
      'anchura de via', 'ancho de via', 'anchura via', 'ancho via',
      'anchura de la calzada', 'ancho de la calzada',
      'road width', 'roadwidth', 'carriageway width', 'street width', 'platform width',
      'anchura', 'ancho', 'calzada', 'width', 'carriageway', 'road', 'via', 'platform',
      'rw', 'road_w', 'r width',
    ],
  },
  {
    key: 'sidewalk_left',
    label: 'Acera izquierda',
    type: 'number',
    group: 'road',
    synonyms: [
      'anchura de acera izquierda', 'ancho de acera izquierda',
      'anchura acera izquierda', 'ancho acera izquierda',
      'anchura de la acera izquierda', 'ancho de la acera izquierda',
      'acera izquierda', 'acerado izquierdo', 'acera izq', 'sidewalk l',
      'sidewalk left', 'left sidewalk', 'left verge', 'verge left',
      'anchura acera', 'ancho acera', 'anchura de acera', 'ancho de acera',
      'acera', 'sidewalk',
    ],
  },
  {
    key: 'sidewalk_right',
    label: 'Acera derecha',
    type: 'number',
    group: 'road',
    synonyms: [
      'anchura de acera derecha', 'ancho de acera derecha',
      'anchura acera derecha', 'ancho acera derecha',
      'anchura de la acera derecha', 'ancho de la acera derecha',
      'acera derecha', 'acerado derecho', 'acera der', 'sidewalk r',
      'sidewalk right', 'right sidewalk', 'right verge', 'verge right',
      'anchura acera', 'ancho acera', 'anchura de acera', 'ancho de acera',
      'acera', 'sidewalk',
    ],
  },
  {
    key: 'lanes',
    label: 'Número de carriles',
    type: 'integer',
    group: 'road',
    enumValues: ['1', '2', '3', '4', '5', '6'],
    synonyms: ['lanes', 'carriles', 'numero carriles', 'numero de carriles', 'num carriles', 'number of lanes', 'lane count', 'carril', 'lane'],
  },
  {
    key: 'median_width',
    label: 'Medianera',
    type: 'number',
    group: 'road',
    synonyms: ['median', 'medianera', 'median width', 'anchura mediana', 'anchura medianera', 'mediana', 'central reservation'],
  },
  {
    key: 'arrangement',
    label: 'Disposición',
    type: 'enum',
    group: 'road',
    synonyms: ['arrangement', 'disposicion', 'layout', 'configuration', 'configuracion', 'tipo disposicion', 'scheme'],
    enumValues: ['Lineal', 'Bilateral', 'Bilateral Alternada', 'Central Doble', 'En Isleta'],
  },
  {
    key: 'height',
    label: 'Altura de poste',
    type: 'number',
    required: true,
    group: 'road',
    synonyms: ['height', 'altura', 'h', 'pole height', 'altura poste', 'altura del poste', 'h poste', 'mounting height', 'altura montaje', 'altura baculo', 'baculo', 'columna', 'altura báculo', 'altura columna'],
  },
  {
    key: 'spacing',
    label: 'Interdistancia',
    type: 'number',
    required: true,
    group: 'road',
    synonyms: ['spacing', 'interdistancia', 'distancia postes', 'separacion', 's', 'pole spacing', 'interpole', 'pole distance', 'distance', 'separacion postes', 'separacion entre postes'],
  },
  {
    key: 'arm_length',
    label: 'Longitud de brazo',
    type: 'number',
    group: 'road',
    aliases: ['armLength'],
    synonyms: [
      'arm length', 'armlength', 'longitud brazo', 'largo brazo', 'brazo', 'arm', 'saliente', 'projection',
      'longitud del brazo', 'largo del brazo', 'longitud de brazo', 'salida brazo', 'brazo largo',
      'long. brazo', 'longitud_brazo', 'largo_brazo', 'longitudbrazo', 'largobrazo',
    ],
  },
  {
    key: 'pole_offset',
    label: 'Retranqueo del poste',
    type: 'number',
    group: 'road',
    synonyms: ['pole offset', 'offset', 'retranqueo', 'retranqueo poste', 'setback', 'distancia borde', 'distance from edge', 'edge distance'],
  },
  {
    key: 'pole_side',
    label: 'Lado del poste',
    type: 'enum',
    enumValues: ['left', 'right'],
    group: 'road',
    synonyms: ['pole side', 'side', 'lado', 'lado poste', 'izquierda', 'derecha', 'left', 'right'],
  },
  {
    key: 'tilt',
    label: 'Inclinación',
    type: 'number',
    group: 'road',
    aliases: ['armTiltAngle'],
    enumValues: ['0', '5', '10', '15', '20', '25'],
    synonyms: ['tilt', 'inclinacion', 'inclinacion brazo', 'angulo brazo', 'arm tilt', 'tilt angle', 'angle', 'angulo'],
  },
  {
    key: 'manufacturer',
    label: 'Fabricante',
    type: 'text',
    group: 'luminaire',
    synonyms: ['manufacturer', 'fabricante', 'marca', 'brand', 'vendor', 'proveedor', 'make', 'mfr', 'mfg', 'mfa'],
  },
  {
    key: 'gama',
    label: 'Gama',
    type: 'text',
    group: 'luminaire',
    synonyms: ['gama', 'range', 'line', 'product line', 'familia', 'series', 'serie', 'tipo clap', 'tipo luminaria', 'clap', 'modelo'],
  },
  {
    key: 'difusor',
    label: 'Difusor',
    type: 'text',
    group: 'luminaire',
    synonyms: ['difusor', 'diffuser', 'diffusor', 'cubierta', 'cover'],
  },
  {
    key: 'lente',
    label: 'Lente / Óptica',
    type: 'text',
    group: 'luminaire',
    synonyms: [
      'lente', 'lens', 'lens optic', 'optica', 'optic', 'optics', 'lente optica',
      'optic family', 'fotometria', 'photometry', 'distribution', 'distribucion',
    ],
  },
  {
    key: 'led_type',
    label: 'Tipo de LED',
    type: 'text',
    group: 'luminaire',
    synonyms: ['led type', 'tipo led', 'led', 'tipo de led', 'led module', 'modulo led', 'chip'],
  },
  {
    key: 'power',
    label: 'Potencia',
    type: 'number',
    required: true,
    group: 'luminaire',
    synonyms: ['power', 'potencia', 'w', 'watts', 'wattage', 'consumption', 'consumo', 'p', 'potencia w', 'rated power', 'pot'],
  },
  {
    key: 'cct',
    label: 'Temperatura (K)',
    type: 'integer',
    group: 'optics',
    enumValues: ['1000', '1200', '1500', '1800', '2200', '2700', '3500', '4000'],
    synonyms: ['cct', 'color temperature', 'temperatura', 'temperatura color', 'k', 'kelvin', 'temp color', 'color temp'],
  },
  {
    key: 'cri',
    label: 'CRI',
    type: 'integer',
    group: 'optics',
    enumValues: ['70', '80', '90'],
    synonyms: ['cri', 'ra', 'color rendering', 'indice reproduccion cromatica', 'irc', 'reproduccion cromatica', 'color rendering index'],
  },
  {
    key: 'lighting_class',
    label: 'Clase de alumbrado',
    type: 'enum',
    group: 'conditions',
    synonyms: ['lighting class', 'class', 'clase', 'clase alumbrado', 'clase de alumbrado', 'clase iluminacion', 'en 13201 class', 'categoria', 'lighting class2', 'class2'],
    enumValues: ['M1', 'M2', 'M3', 'M4', 'M5', 'M6', 'P1', 'P2', 'P3', 'P4', 'P5', 'P6'],
  },
  {
    key: 'mf',
    label: 'Factor de mantenimiento',
    type: 'number',
    group: 'conditions',
    synonyms: ['maintenance factor', 'mf', 'factor mantenimiento', 'factor de mantenimiento', 'fm', 'maintenance', 'mantenimiento'],
  },
  {
    key: 'pavement',
    label: 'Pavimento',
    type: 'enum',
    enumValues: ['R1', 'R2', 'R3', 'R4'],
    group: 'conditions',
    synonyms: ['pavement', 'pavimento', 'asphalt', 'asfalto', 'superficie', 'surface', 'r class', 'clase r'],
  },
];

export const TRAMO_PARAM_GROUPS: Array<{ key: TramoParamDef['group']; label: string }> = [
  { key: 'identification', label: 'Identificación' },
  { key: 'road', label: 'Vía y geometría' },
  { key: 'luminaire', label: 'Luminaria' },
  { key: 'optics', label: 'Óptica y luz' },
  { key: 'conditions', label: 'Condiciones' },
];

export type ColumnMapping = Record<string, string | null>;
export type ManualValues = Record<string, string>;

export interface ParsedSheet {
  headers: string[];
  rows: string[][];
  totalRows: number;
}

export const parseExcelFile = async (file: File): Promise<ParsedSheet> => {
  const XLSX = await loadXlsx();
  const buffer = await file.arrayBuffer();
  const workbook = XLSX.read(buffer, { type: 'array' });
  const firstSheetName = workbook.SheetNames[0];
  if (!firstSheetName) {
    throw new Error('El archivo no contiene hojas.');
  }
  const sheet = workbook.Sheets[firstSheetName];
  const aoa = XLSX.utils.sheet_to_json<string[]>(sheet, {
    header: 1,
    raw: false,
    blankrows: false,
    defval: '',
  });
  if (aoa.length === 0) {
    throw new Error('El archivo está vacío.');
  }
  const [headerRow, ...dataRows] = aoa;
  const headers = (headerRow as unknown[]).map(cell => (cell == null ? '' : String(cell).trim()));
  const rows = (dataRows as unknown[][]).map(row =>
    (row as unknown[]).map(cell => (cell == null ? '' : String(cell).trim())),
  );
  return {
    headers,
    rows,
    totalRows: rows.length,
  };
};

const parseNumericCell = (raw: string, type: 'number' | 'integer'): number | null => {
  if (raw == null) return null;
  const trimmed = String(raw).trim();
  if (!trimmed) return null;
  const normalized = trimmed.replace(/\s+/g, '').replace(',', '.');
  const cleaned = normalized.replace(/[^0-9.+-]/g, '');
  if (!cleaned || cleaned === '+' || cleaned === '.') return null;
  if (cleaned === '-') return 0;
  const num = Number(cleaned);
  if (Number.isNaN(num)) return null;
  return type === 'integer' ? Math.trunc(num) : num;
};

const parseEnumCell = (raw: string, allowed: string[]): string | null => {
  if (raw == null) return null;
  const trimmed = String(raw).trim();
  if (!trimmed) return null;
  const lower = trimmed.replace(/\s+/g, '').toLowerCase();
  for (const candidate of allowed) {
    if (candidate.replace(/\s+/g, '').toLowerCase() === lower) return candidate;
  }
  return null;
};

const parseTextCell = (raw: string): string | null => {
  if (raw == null) return null;
  const trimmed = String(raw).trim();
  return trimmed === '' ? null : trimmed;
};

const splitByAliases = (key: string, value: any, target: Record<string, any>) => {
  const def = TRAMO_PARAM_DEFS.find(d => d.key === key);
  if (!def) {
    target[key] = value;
    return;
  }
  if (def.aliases && def.aliases.length > 0) {
    target[key] = value;
    target[def.aliases[0]] = value;
  } else {
    target[key] = value;
  }
};

export interface BuildConfigOptions {
  sheet: ParsedSheet;
  mapping: ColumnMapping;
  manualValues?: ManualValues;
  defaults: Record<string, any>;
  /** When set, only process the first `rowLimit` rows (used for cheap previews). */
  rowLimit?: number;
  /** When set, performs catalog value resolution (fuzzy matching) for dim fields. */
  catalogOptions?: Record<string, string[]>;
}

export interface BuiltRow {
  rowIndex: number;
  name: string | null;
  description?: string;
  config: Record<string, any>;
  errors: string[];
  errorsByParam: Record<string, string[]>;
  sourceByParam: Record<string, ValueSource>;
  dimMatch: Record<string, DimMatchResult>;
}

export type ValueSource = 'column' | 'manual' | 'default';

export interface DimMatchResult {
  status: 'exact' | 'auto' | 'ambiguous' | 'not_found';
  resolved: string | null;
  candidates: string[];
}

/** Fields whose values should be uppercased to match the DB catalog normalization. */
export const NORM_UPPER_FIELDS = ['gama', 'difusor', 'lente', 'led_type'];
export const DIM_PARAM_KEYS = ['gama', 'difusor', 'lente', 'led_type'];

function _levenshtein(a: string, b: string): number {
  if (a.length === 0) return b.length;
  if (b.length === 0) return a.length;
  const m: number[][] = [];
  for (let i = 0; i <= b.length; i++) m[i] = [i];
  for (let j = 0; j <= a.length; j++) m[0][j] = j;
  for (let i = 1; i <= b.length; i++) {
    for (let j = 1; j <= a.length; j++) {
      const cost = a[j - 1] === b[i - 1] ? 0 : 1;
      m[i][j] = Math.min(m[i - 1][j] + 1, m[i][j - 1] + 1, m[i - 1][j - 1] + cost);
    }
  }
  return m[b.length][a.length];
}

export function resolveDimValue(value: string, options: string[] | undefined): DimMatchResult {
  if (!options || options.length === 0) return { status: 'not_found', resolved: null, candidates: [] };
  const normed = value.trim().toUpperCase();

  const exact = options.find(o => o === normed);
  if (exact) return { status: 'exact', resolved: exact, candidates: [] };

  const contains = options.filter(o => o.includes(normed) || normed.includes(o));
  if (contains.length === 1) return { status: 'auto', resolved: contains[0], candidates: [] };
  if (contains.length > 1) return { status: 'ambiguous', resolved: null, candidates: contains };

  const starts = options.filter(o => o.startsWith(normed) || normed.startsWith(o));
  if (starts.length === 1) return { status: 'auto', resolved: starts[0], candidates: [] };
  if (starts.length > 1) return { status: 'ambiguous', resolved: null, candidates: starts };

  const scored = options.map(o => ({ option: o, dist: _levenshtein(normed, o) })).sort((a, b) => a.dist - b.dist);
  const best = scored[0];
  if (best && best.dist <= 2) {
    const ties = scored.filter(s => s.dist === best.dist);
    if (ties.length === 1) return { status: 'auto', resolved: ties[0].option, candidates: [] };
    return { status: 'ambiguous', resolved: null, candidates: ties.map(t => t.option) };
  }

  return { status: 'not_found', resolved: null, candidates: [] };
}

const cellAt = (row: string[], index: number): string => (row[index] ?? '').toString();

export const buildConfigsFromSheet = ({
  sheet,
  mapping,
  manualValues,
  defaults,
  rowLimit,
  catalogOptions,
}: BuildConfigOptions): BuiltRow[] => {
  const rows = rowLimit != null && rowLimit >= 0 ? sheet.rows.slice(0, rowLimit) : sheet.rows;
  return rows.map((row, idx) => {
    const config: Record<string, any> = { ...defaults };
    const errors: string[] = [];
    const errorsByParam: Record<string, string[]> = {};
    const sourceByParam: Record<string, ValueSource> = {};
    let name: string | null = null;
    let description: string | undefined;

    const pushError = (paramKey: string, message: string) => {
      errors.push(message);
      if (!errorsByParam[paramKey]) errorsByParam[paramKey] = [];
      errorsByParam[paramKey].push(message);
    };

    for (const def of TRAMO_PARAM_DEFS) {
      if (def.key === 'name') {
        const colIndex = mapping[def.key];
        const cell = colIndex != null ? cellAt(row, Number(colIndex)) : '';
        if (cell) {
          const value = parseTextCell(cell);
          if (value) {
            name = value;
            sourceByParam[def.key] = 'column';
          }
        }
        if (!name && manualValues?.[def.key]) {
          const value = parseTextCell(manualValues[def.key]);
          if (value) {
            name = value;
            sourceByParam[def.key] = sourceByParam[def.key] ?? 'manual';
          }
        }
        continue;
      }
      if (def.key === 'description') {
        const colIndex = mapping[def.key];
        const cell = colIndex != null ? cellAt(row, Number(colIndex)) : '';
        if (cell) {
          const value = parseTextCell(cell);
          if (value) {
            description = value;
            sourceByParam[def.key] = 'column';
          }
        }
        if (!description && manualValues?.[def.key]) {
          const value = parseTextCell(manualValues[def.key]);
          if (value) {
            description = value;
            sourceByParam[def.key] = sourceByParam[def.key] ?? 'manual';
          }
        }
        continue;
      }

      const colIndex = mapping[def.key];
      const cell = colIndex != null ? cellAt(row, Number(colIndex)) : '';
      const manualRaw = manualValues?.[def.key]?.trim() ?? '';
      const hasCell = cell !== '';
      const hasManual = manualRaw !== '';

      if (!hasCell && !hasManual) continue;

      const applyValue = (raw: string, source: ValueSource) => {
        if (def.type === 'number' || def.type === 'integer') {
          const num = parseNumericCell(raw, def.type);
          if (num == null) {
            pushError(def.key, `${def.label}: valor no numérico "${raw}"`);
            return;
          }
          splitByAliases(def.key, num, config);
          sourceByParam[def.key] = source;
        } else if (def.type === 'enum' && def.enumValues) {
          const enumValue = parseEnumCell(raw, def.enumValues);
          if (enumValue == null) {
            pushError(def.key, `${def.label}: valor no permitido "${raw}"`);
            return;
          }
          splitByAliases(def.key, enumValue, config);
          sourceByParam[def.key] = source;
        } else {
          const value = parseTextCell(raw);
          if (value != null) {
            splitByAliases(def.key, value, config);
            sourceByParam[def.key] = source;
          }
        }
      };

      if (hasCell) {
        applyValue(cell, 'column');
      } else if (hasManual) {
        applyValue(manualRaw, 'manual');
      }
    }

    for (const f of NORM_UPPER_FIELDS) {
      if (config[f] && typeof config[f] === 'string') config[f] = config[f].trim().toUpperCase();
    }

    if (config.lente) config.optic_family = config.lente;

    const dimMatch: Record<string, DimMatchResult> = {};
    if (catalogOptions) {
      for (const k of DIM_PARAM_KEYS) {
        const val = config[k];
        if (val && typeof val === 'string') {
          dimMatch[k] = resolveDimValue(val, catalogOptions[k]);
        }
      }
    }

    return { rowIndex: idx + 1, name, description, config, errors, errorsByParam, sourceByParam, dimMatch };
  });
};

export interface AutoMapResult {
  mapping: ColumnMapping;
  /** Confidence score in [0, 1] for each auto-assigned pair. */
  scores: Record<string, number>;
  /** Headers that were too ambiguous to assign confidently. */
  unmatchedHeaders: Array<{ header: string; bestScore: number }>;
}

const MATCH_THRESHOLD = 0.45;

const EXAMPLE_ROW: Record<string, string> = {
  name: 'Tramo ejemplo',
  description: 'Descripción opcional',
  road_width: '8.5',
  sidewalk_left: '1.2',
  sidewalk_right: '1.2',
  lanes: '2',
  median_width: '0',
  arrangement: 'Lineal',
  height: '10',
  spacing: '30',
  arm_length: '1.5',
  pole_offset: '1',
  pole_side: 'left',
  tilt: '5',
  manufacturer: 'Ejemplo',
  gama: 'GAMA-X',
  difusor: 'PLANO',
  lente: 'M3',
  led_type: 'SMD5050',
  power: '150',
  cct: '4000',
  cri: '80',
  lighting_class: 'M3',
  mf: '0.8',
  pavement: 'R3',
};

export async function downloadTemplate(): Promise<void> {
  const XLSX = await loadXlsx();
  const headers = TRAMO_PARAM_DEFS.map(d => `${d.label} (${d.key})${d.required ? ' *' : ''}`);
  const example = TRAMO_PARAM_DEFS.map(d => EXAMPLE_ROW[d.key] ?? '');
  const ws = XLSX.utils.aoa_to_sheet([headers, example]);
  ws['!cols'] = TRAMO_PARAM_DEFS.map(d => ({ wch: Math.max(d.label.length + 5, 18) }));
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, 'Plantilla');
  XLSX.writeFile(wb, 'plantilla_importacion_tramos.xlsx');
}

export const autoSuggestMapping = (headers: string[]): ColumnMapping => {
  return autoSuggestMappingDetailed(headers).mapping;
};

export const autoSuggestMappingDetailed = (headers: string[]): AutoMapResult => {
  const usedHeaders = new Set<number>();
  const usedParams = new Set<string>();
  const scores: Record<string, number> = {};
  const unmatchedHeaders: Array<{ header: string; bestScore: number }> = [];

  interface Candidate {
    headerIdx: number;
    paramKey: string;
    score: MatchScore;
  }
  const candidates: Candidate[] = [];

  headers.forEach((rawHeader, headerIdx) => {
    const header = rawHeader?.trim() ?? '';
    if (!header) return;
    const headerTokens = tokenizeWithSeparators(header);
    if (!headerTokens.length) return;

    const headerBest: Array<{ paramKey: string; score: number }> = [];

    for (const def of TRAMO_PARAM_DEFS) {
      const allAliasStrings = [def.key, def.label, ...(def.aliases ?? []), ...(def.synonyms ?? [])];
      const paramTokens = tokenizeWithSeparators(allAliasStrings.join(' '));
      const aliasTokensList = allAliasStrings.map(s => tokenizeWithSeparators(s));
      const aliasesNormalized = allAliasStrings.map(s => normalize(s));
      const paramNormalized = normalize(`${def.key} ${def.label}`);

      const score = scoreCandidate(header, headerTokens, aliasTokensList, aliasesNormalized, paramTokens, paramNormalized);

      if (score.combined >= MATCH_THRESHOLD) {
        candidates.push({ headerIdx, paramKey: def.key, score });
        headerBest.push({ paramKey: def.key, score: score.combined });
      }
    }
    headerBest.sort((a, b) => b.score - a.score);
    if (!headerBest.length) {
      unmatchedHeaders.push({ header, bestScore: 0 });
    }
  });

  candidates.sort((a, b) => b.score.combined - a.score.combined);

  const mapping: ColumnMapping = {};
  for (const cand of candidates) {
    if (usedHeaders.has(cand.headerIdx)) continue;
    if (usedParams.has(cand.paramKey)) continue;
    usedHeaders.add(cand.headerIdx);
    usedParams.add(cand.paramKey);
    mapping[cand.paramKey] = String(cand.headerIdx);
    scores[cand.paramKey] = cand.score.combined;
  }

  headers.forEach((rawHeader, headerIdx) => {
    if (usedHeaders.has(headerIdx)) return;
    const header = rawHeader?.trim() ?? '';
    if (!header) return;
    const headerTokens = tokenizeWithSeparators(header);
    if (!headerTokens.length) return;
    let best = 0;
    for (const def of TRAMO_PARAM_DEFS) {
      const allAliasStrings = [def.key, def.label, ...(def.aliases ?? []), ...(def.synonyms ?? [])];
      const paramTokens = tokenizeWithSeparators(allAliasStrings.join(' '));
      const aliasTokensList = allAliasStrings.map(s => tokenizeWithSeparators(s));
      const aliasesNormalized = allAliasStrings.map(s => normalize(s));
      const paramNormalized = normalize(`${def.key} ${def.label}`);
      const s = scoreCandidate(header, headerTokens, aliasTokensList, aliasesNormalized, paramTokens, paramNormalized);
      if (s.combined > best) best = s.combined;
    }
    unmatchedHeaders.push({ header, bestScore: best });
  });

  return { mapping, scores, unmatchedHeaders };
};
