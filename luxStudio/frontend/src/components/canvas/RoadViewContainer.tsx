import React, { lazy, Suspense, useState } from 'react';
import { Cuboid, Map as MapIcon, Eye } from 'lucide-react';
import { useI18n } from '../../i18n';
import RoadIsometricOverview from './RoadIsometricOverview';
const RoadScene3D = lazy(() => import('./RoadScene3D'));

type ViewMode = '2d' | '3d' | 'driver';

const RoadViewContainer: React.FC = () => {
  const { t } = useI18n();
  const [mode, setMode] = useState<ViewMode>('2d');
  const [speedKmh, setSpeedKmh] = useState(60);

  return (
    <section className="road-command-shell flex min-h-[560px] flex-col overflow-hidden rounded-xl lg:h-[calc(100vh-14rem)] lg:max-h-[680px]">
      <div className="flex items-center justify-between border-b border-[#E8E2D8] bg-[#FFFFFF]/90 px-3 py-2">
        <div className="flex items-center gap-1 rounded-lg border border-[#E8E2D8] bg-[#FFFFFF]/80 p-1 shadow-sm">
          <button
            type="button"
            onClick={() => setMode('2d')}
            aria-pressed={mode === '2d'}
            className={`flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-semibold transition-all ${
              mode === '2d'
                ? 'bg-[#1E1E1E] text-white shadow-sm'
                : 'text-[#A09A91] hover:bg-[#FFFFFF] hover:text-[#1E1E1E]'
            }`}
          >
            <MapIcon className="h-4 w-4" aria-hidden="true" />
            {t('roadView.plant')}
          </button>
          <button
            type="button"
            onClick={() => setMode('3d')}
            aria-pressed={mode === '3d'}
            className={`flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-semibold transition-all ${
              mode === '3d'
                ? 'bg-[#1E1E1E] text-white shadow-sm'
                : 'text-[#A09A91] hover:bg-[#FFFFFF] hover:text-[#1E1E1E]'
            }`}
          >
            <Cuboid className="h-4 w-4" aria-hidden="true" />
            {t('roadView.threeD')}
          </button>
          <button
            type="button"
            onClick={() => setMode(mode === 'driver' ? '3d' : 'driver')}
            aria-pressed={mode === 'driver'}
            className={`flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-semibold transition-all ${
              mode === 'driver'
                ? 'bg-amber-600 text-white shadow-sm'
                : 'text-[#A09A91] hover:bg-[#FFFFFF] hover:text-[#1E1E1E]'
            }`}
          >
            <Eye className="h-4 w-4" aria-hidden="true" />
            Driver
          </button>
        </div>
        <div className="hidden text-[11px] font-semibold uppercase tracking-[0.18em] text-[#6a6a6a] sm:block">
          {mode === '2d' ? t('roadView.plantAndSection') : mode === '3d' ? t('roadView.threeDScene') : 'Driver view'}
        </div>
      </div>
      <div className="flex-1 overflow-hidden">
        {mode === '2d' ? (
          <div className="h-full min-h-0 overflow-hidden p-2">
            <RoadIsometricOverview />
          </div>
        ) : (
          <Suspense fallback={<div className="flex h-full min-h-[420px] items-center justify-center text-sm text-[#A09A91]">Cargando vista 3D…</div>}>
            <RoadScene3D
              variant="inline"
              onClose={() => setMode('2d')}
              viewMode={mode === 'driver' ? 'driver' : 'orbit'}
              speedKmh={speedKmh}
              carCount={0}
              onViewModeChange={(m) => setMode(m === 'driver' ? 'driver' : '3d')}
              onSpeedChange={setSpeedKmh}
            />
          </Suspense>
        )}
      </div>
    </section>
  );
};

export default RoadViewContainer;
