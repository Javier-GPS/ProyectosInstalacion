import type { RoadElement } from '../types';

type ConfigGeometry = {
  road_elements?: RoadElement[];
  arrangement?: string;
  pole_side?: 'left' | 'right';
};

type PositionedElement = RoadElement & { index: number; start: number; end: number };

export function roadElementLabel(element: RoadElement, index: number): string {
  return `${element.type === 'sidewalk' ? 'SW' : 'RD'} ${index + 1}`;
}

export function luminaireLocationLabels(config: ConfigGeometry): string[] {
  const elements = config.road_elements;
  if (!Array.isArray(elements) || !elements.length) {
    return [config.pole_side === 'right' ? 'Acera derecha' : 'Acera izquierda'];
  }

  const positioned: PositionedElement[] = [];
  let start = 0;
  elements.forEach((element, index) => {
    const end = start + element.width;
    positioned.push({ ...element, index, start, end });
    start = end;
  });
  const carriageways = positioned.filter(element => element.type === 'carriageway');
  const first = carriageways[0];
  const last = carriageways[carriageways.length - 1];
  if (!first || !last) return [];

  const adjacent = {
    left: positioned[first.index - 1],
    right: positioned[last.index + 1],
  };
  const label = (element: PositionedElement | undefined, side: 'left' | 'right' | 'center') =>
    element ? roadElementLabel(element, element.index) : `Borde calzada ${side}`;

  if (config.arrangement === 'Central Doble' || config.arrangement === 'En Isleta') {
    const center = start / 2;
    const element = positioned.find(item => center >= item.start && (center < item.end || item.end === start));
    return element ? [roadElementLabel(element, element.index)] : ['Calzada central'];
  }
  if (config.arrangement === 'Lineal') {
    return [label(adjacent[config.pole_side === 'right' ? 'right' : 'left'], config.pole_side === 'right' ? 'right' : 'left')];
  }
  return [label(adjacent.left, 'left'), label(adjacent.right, 'right')].filter((value, index, values) => values.indexOf(value) === index);
}
