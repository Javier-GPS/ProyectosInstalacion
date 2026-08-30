/** Catálogo de objetos colocables en el editor de ciudad (estilo theme-park).
 *  Cada tipo es editable: dimensiones (ancho/largo/alto), rotación, color y
 *  atributos específicos. El inspector renderiza los campos de forma genérica. */

export type EditorAttrType = 'number' | 'text' | 'color' | 'select';

export interface EditorAttrDef {
  key: string;
  labelKey: string;
  type: EditorAttrType;
  min?: number;
  max?: number;
  step?: number;
  options?: { value: string; labelKey: string }[];
  default: string | number;
}

export interface EditorObjectType {
  key: string;
  labelKey: string;
  icon: string;
  color: string;
  defaults: { width: number; length: number; height: number; rotation: number };
  attrs: EditorAttrDef[];
}

export interface EditorObject {
  id: string;
  type: string;
  lng: number;
  lat: number;
  rotation: number;
  width: number;
  length: number;
  height: number;
  color: string;
  label?: string;
  attrs: Record<string, string | number>;
  /** id de la luminaria real creada al sincronizar (para evitar duplicados). */
  lumId?: number | null;
}

export const EDITOR_OBJECT_TYPES: EditorObjectType[] = [
  {
    key: 'farola',
    labelKey: 'editor.obj.farola',
    icon: '💡',
    color: '#FACC15',
    defaults: { width: 0.4, length: 0.4, height: 9, rotation: 0 },
    attrs: [
      { key: 'watts', labelKey: 'editor.attr.watts', type: 'number', min: 0, max: 400, step: 5, default: 60 },
      { key: 'armLength', labelKey: 'editor.attr.armLength', type: 'number', min: 0, max: 4, step: 0.1, default: 1.2 },
      { key: 'tilt', labelKey: 'editor.attr.tilt', type: 'number', min: 0, max: 45, step: 1, default: 15 },
    ],
  },
  {
    key: 'arbol',
    labelKey: 'editor.obj.arbol',
    icon: '🌳',
    color: '#2E7D32',
    defaults: { width: 1.2, length: 1.2, height: 6, rotation: 0 },
    attrs: [
      { key: 'species', labelKey: 'editor.attr.species', type: 'text', default: '' },
      { key: 'canopy', labelKey: 'editor.attr.canopy', type: 'number', min: 1, max: 14, step: 0.5, default: 4 },
    ],
  },
  {
    key: 'banco',
    labelKey: 'editor.obj.banco',
    icon: '🪑',
    color: '#8B5A2B',
    defaults: { width: 1.8, length: 0.6, height: 0.45, rotation: 0 },
    attrs: [
      { key: 'seats', labelKey: 'editor.attr.seats', type: 'number', min: 1, max: 8, step: 1, default: 3 },
    ],
  },
  {
    key: 'obstaculo',
    labelKey: 'editor.obj.obstaculo',
    icon: '⛔',
    color: '#B42318',
    defaults: { width: 1, length: 1, height: 1, rotation: 0 },
    attrs: [
      {
        key: 'kind', labelKey: 'editor.attr.kind', type: 'select',
        options: [
          { value: 'barrera', labelKey: 'editor.opt.barrera' },
          { value: 'bolardo', labelKey: 'editor.opt.bolardo' },
          { value: 'contenedor', labelKey: 'editor.opt.contenedor' },
          { value: 'hidrante', labelKey: 'editor.opt.hidrante' },
          { value: 'otra', labelKey: 'editor.opt.otra' },
        ],
        default: 'bolardo',
      },
    ],
  },
  {
    key: 'senal',
    labelKey: 'editor.obj.senal',
    icon: '🚸',
    color: '#1D4ED8',
    defaults: { width: 0.4, length: 0.4, height: 2.2, rotation: 0 },
    attrs: [
      {
        key: 'signType', labelKey: 'editor.attr.signType', type: 'select',
        options: [
          { value: 'stop', labelKey: 'editor.opt.stop' },
          { value: 'ceda', labelKey: 'editor.opt.ceda' },
          { value: 'cuidado', labelKey: 'editor.opt.cuidado' },
          { value: 'limite', labelKey: 'editor.opt.limite' },
          { value: 'otra', labelKey: 'editor.opt.otra' },
        ],
        default: 'stop',
      },
    ],
  },
  {
    key: 'contenedor',
    labelKey: 'editor.obj.contenedor',
    icon: '🗑️',
    color: '#475569',
    defaults: { width: 1.2, length: 0.8, height: 1.4, rotation: 0 },
    attrs: [],
  },
  {
    key: 'fuente',
    labelKey: 'editor.obj.fuente',
    icon: '⛲',
    color: '#0EA5E9',
    defaults: { width: 3, length: 3, height: 0.8, rotation: 0 },
    attrs: [],
  },
  {
    key: 'jardinera',
    labelKey: 'editor.obj.jardinera',
    icon: '🪴',
    color: '#15803D',
    defaults: { width: 2, length: 0.8, height: 0.6, rotation: 0 },
    attrs: [],
  },
  {
    key: 'papelera',
    labelKey: 'editor.obj.papelera',
    icon: '🚮',
    color: '#16A34A',
    defaults: { width: 0.5, length: 0.5, height: 1, rotation: 0 },
    attrs: [],
  },
  {
    key: 'parada',
    labelKey: 'editor.obj.parada',
    icon: '🚏',
    color: '#7C3AED',
    defaults: { width: 2, length: 1, height: 3, rotation: 0 },
    attrs: [],
  },
];

const TYPE_MAP: Record<string, EditorObjectType> = Object.fromEntries(
  EDITOR_OBJECT_TYPES.map(t => [t.key, t]),
);

export const getEditorType = (key: string): EditorObjectType | undefined => TYPE_MAP[key];

export const makeEditorObject = (typeKey: string, lng: number, lat: number): EditorObject => {
  const def = TYPE_MAP[typeKey];
  const base = def ?? EDITOR_OBJECT_TYPES[0];
  const id = (typeof crypto !== 'undefined' && crypto.randomUUID)
    ? crypto.randomUUID()
    : `obj-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const attrs: Record<string, string | number> = {};
  for (const a of base.attrs) attrs[a.key] = a.default;
  return {
    id,
    type: base.key,
    lng,
    lat,
    rotation: base.defaults.rotation,
    width: base.defaults.width,
    length: base.defaults.length,
    height: base.defaults.height,
    color: base.color,
    attrs,
  };
};
