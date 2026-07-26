import { describe, it, expect, beforeEach } from 'vitest';
import { useConfigStore } from '../src/store/useConfigStore';

const initialState = useConfigStore.getInitialState();

beforeEach(() => {
  useConfigStore.setState(initialState);
});

describe('useConfigStore — road elements', () => {
  it('setRoadElements normalizes and derives flat fields', () => {
    useConfigStore.getState().setRoadElements([
      { type: 'sidewalk', width: 2, pedestrian_class: 'P4' },
      { type: 'carriageway', width: 7, lanes: 2, lighting_class: 'M3' },
      { type: 'sidewalk', width: 1.5, pedestrian_class: 'P5' },
    ]);
    const s = useConfigStore.getState();
    expect(s.road_width).toBe(10.5);
    expect(s.sidewalk_left).toBe(2);
    expect(s.sidewalk_right).toBe(1.5);
    expect(s.lanes).toBe(2);
    expect(s.roadElements).toHaveLength(3);
  });

  it('addRoadElement inserts before first carriageway by default', () => {
    useConfigStore.getState().setRoadElements([
      { type: 'carriageway', width: 7, lanes: 2, lighting_class: 'M3' },
    ]);
    useConfigStore.getState().addRoadElement({ type: 'sidewalk', width: 1.5, pedestrian_class: 'P4' });
    const s = useConfigStore.getState();
    expect(s.roadElements[0].type).toBe('sidewalk');
    expect(s.roadElements[1].type).toBe('carriageway');
  });

  it('removeRoadElement ensures at least one carriageway exists', () => {
    useConfigStore.getState().setRoadElements([
      { type: 'sidewalk', width: 1.5, pedestrian_class: 'P4' },
    ]);
    useConfigStore.getState().removeRoadElement(0);
    const s = useConfigStore.getState();
    expect(s.roadElements).toHaveLength(1);
    expect(s.roadElements[0].type).toBe('carriageway');
  });

  it('moveRoadElement swaps elements correctly', () => {
    useConfigStore.getState().setRoadElements([
      { type: 'sidewalk', width: 1.5, pedestrian_class: 'P4' },
      { type: 'carriageway', width: 7, lanes: 2, lighting_class: 'M3' },
      { type: 'sidewalk', width: 2, pedestrian_class: 'P5' },
    ]);
    useConfigStore.getState().moveRoadElement(0, 2);
    const s = useConfigStore.getState();
    expect(s.roadElements[0].type).toBe('carriageway');
    expect(s.roadElements[2].type).toBe('sidewalk');
  });
});

describe('useConfigStore — dirty tracking', () => {
  it('setting a field marks dirty = true', () => {
    expect(useConfigStore.getState().dirty).toBe(false);
    useConfigStore.getState().setHeight(10);
    expect(useConfigStore.getState().dirty).toBe(true);
  });

  it('markSaved resets dirty and stores snapshot', () => {
    useConfigStore.getState().setHeight(10);
    useConfigStore.getState().markSaved({ configJson: '{}', resultJson: null });
    const s = useConfigStore.getState();
    expect(s.dirty).toBe(false);
    expect(s.lastSavedSnapshot?.configJson).toBe('{}');
  });

  it('setResults does not mark dirty (direct state update)', () => {
    useConfigStore.getState().setResults({ compliant: true } as any);
    expect(useConfigStore.getState().dirty).toBe(false);
  });
});

describe('useConfigStore — reset', () => {
  it('reset restores all fields to initial state', () => {
    useConfigStore.getState().setRoadWidth(99);
    useConfigStore.getState().setHeight(99);
    useConfigStore.getState().setResults({ compliant: true } as any);
    useConfigStore.getState().reset();
    const s = useConfigStore.getState();
    expect(s.road_width).toBe(initialState.road_width);
    expect(s.height).toBe(initialState.height);
    expect(s.results).toBeNull();
    expect(s.dirty).toBe(false);
  });
});
