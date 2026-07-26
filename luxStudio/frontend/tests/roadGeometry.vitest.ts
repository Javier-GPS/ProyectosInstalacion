import { describe, expect, it } from 'vitest';
import { luminaireLocationLabels, roadElementLabel } from '../src/lib/roadGeometry';

describe('road geometry labels', () => {
  it('keeps the cross-section index in SW/RD labels', () => {
    expect(roadElementLabel({ type: 'sidewalk', width: 1 }, 2)).toBe('SW 3');
    expect(roadElementLabel({ type: 'carriageway', width: 7 }, 1)).toBe('RD 2');
  });

  it('maps bilateral luminaires to the actual outer sidewalks', () => {
    expect(luminaireLocationLabels({
      arrangement: 'Bilateral',
      road_elements: [
        { type: 'sidewalk', width: 2 },
        { type: 'carriageway', width: 7 },
        { type: 'sidewalk', width: 1 },
        { type: 'carriageway', width: 7 },
        { type: 'sidewalk', width: 2 },
      ],
    })).toEqual(['SW 1', 'SW 5']);
  });

  it('identifies a central median sidewalk', () => {
    expect(luminaireLocationLabels({
      arrangement: 'Central Doble',
      road_elements: [
        { type: 'carriageway', width: 7 },
        { type: 'sidewalk', width: 2 },
        { type: 'carriageway', width: 7 },
      ],
    })).toEqual(['SW 2']);
  });
});
