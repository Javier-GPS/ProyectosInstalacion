import React, { useEffect, useMemo, useState } from 'react';
import { useI18n } from '../i18n';
import { useGisStore } from '../store/useGisStore';
import { deleteZone, getProjectZonesSummary } from '../lib/api';
import { useApi } from '../hooks/useApi';
import type { GisZoneSummary } from '../types';
import Button from '../components/ui/Button';

const JOB_LABEL: Record<string, string> = {
  queued: 'En cola',
  running: 'Calculando',
  succeeded: 'Completado',
  partial: 'Parcial',
  failed: 'Fallido',
  cancelled: 'Cancelado',
  unknown: 'Desconocido',
};

const JOB_STYLE: Record<string, string> = {
  succeeded: 'bg-[#1F7A4D]/10 text-[#1F7A4D]',
  partial: 'bg-amber-100 text-amber-800',
  failed: 'bg-[#B42318]/10 text-[#B42318]',
  queued: 'bg-[#4A5568]/10 text-[#4A5568]',
  running: 'bg-[#4A5568]/10 text-[#4A5568]',
  cancelled: 'bg-salvi-surface text-salvi-grey',
};

const formatDate = (iso: string | null | undefined): string => {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleDateString('es', { day: '2-digit', month: 'short', year: 'numeric' });
};

interface ProjectDetailPageProps {
  onOpenZone: (zoneId: string) => void;
  onCreateZone: () => void;
  onBack: () => void;
}

const ProjectDetailPage: React.FC<ProjectDetailPageProps> = ({ onOpenZone, onCreateZone, onBack }) => {
  const { t } = useI18n();
  const activeProjectId = useGisStore(s => s.activeProjectId);
  const activeProject = useGisStore(s => s.projects.find(p => String(p.id) === String(s.activeProjectId)));
  const removeZone = useGisStore(s => s.removeZone);
  const { call: callDeleteZone } = useApi<void>();

  const [summary, setSummary] = useState<GisZoneSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [reloadKey, setReloadKey] = useState(0);
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);

  useEffect(() => {
    if (!activeProjectId) return;
    const controller = new AbortController();
    setLoading(true);
    setError('');
    getProjectZonesSummary(String(activeProjectId), controller.signal)
      .then(setSummary)
      .catch(err => {
        if ((err as Error).name === 'AbortError') return;
        setError((err as Error).message || t('zones.summary.error'));
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [activeProjectId, reloadKey, t]);

  const totalStats = useMemo(() => summary.reduce((acc, s) => ({
    segments: acc.segments + s.osm.segment_count,
    named: acc.named + s.osm.distinct_name_count,
    selected: acc.selected + s.planning.target_overrides + s.study.materialized_targets,
    luminaires: acc.luminaires + s.luminaires,
    materialized: acc.materialized + s.study.materialized_targets,
  }), { segments: 0, named: 0, selected: 0, luminaires: 0, materialized: 0 }), [summary]);

  const handleDelete = async (id: string, name: string) => {
    if (!window.confirm(t('zone.deleteConfirm', { name }))) return;
    setPendingDelete(id);
    try {
      await callDeleteZone(signal => deleteZone(id, signal));
      removeZone(id);
      setReloadKey(v => v + 1);
    } catch (err) {
      console.error('No se pudo eliminar la zona', err);
      setError((err as Error).message || 'No se pudo eliminar la zona');
    } finally {
      setPendingDelete(null);
    }
  };

  return (
    <main className="flex-1 overflow-y-auto bg-salvi-cream">
      <div className="mx-auto max-w-7xl p-6">
        <nav className="flex items-center gap-2 text-sm text-salvi-muted">
          <button onClick={onBack} className="font-medium text-[#1E1E1E] hover:text-[#333333]">
            {t('projects.title')}
          </button>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="9 18 15 12 9 6" />
          </svg>
          <span className="truncate font-semibold text-[#6A6A6A]">{activeProject?.name || '—'}</span>
        </nav>

        <div className="mb-6 mt-4 flex flex-col gap-4 rounded-xl border border-salvi-line bg-white p-5 shadow-sm sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <h2 className="truncate text-xl font-semibold text-salvi-black" title={activeProject?.name}>
              {activeProject?.name || '—'}
            </h2>
            <p className="mt-0.5 text-sm text-salvi-muted">
              {[activeProject?.client, activeProject?.location].filter(Boolean).join(' · ') || '—'}
            </p>
            {summary.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-2 text-xs">
                <span className="rounded-full bg-salvi-surface px-2.5 py-0.5 font-semibold text-salvi-grey">
                  {t('zones.summary.streets', { n: totalStats.named })}
                </span>
                <span className="rounded-full bg-salvi-surface px-2.5 py-0.5 font-semibold text-salvi-grey">
                  {t('zones.summary.segments', { n: totalStats.segments })}
                </span>
                <span className="rounded-full bg-[#1F7A4D]/10 px-2.5 py-0.5 font-semibold text-[#1F7A4D]">
                  {t('zones.summary.studied', { n: totalStats.materialized })}
                </span>
                <span className="rounded-full bg-salvi-surface px-2.5 py-0.5 font-semibold text-salvi-grey">
                  {t('zones.summary.luminaires', { n: totalStats.luminaires })}
                </span>
              </div>
            )}
          </div>
          <Button variant="primary" onClick={onCreateZone} className="shrink-0">
            + {t('zones.new')}
          </Button>
        </div>

        {error && (
          <div className="mb-6 rounded-lg border border-state-danger/25 bg-[#FDECEA] px-4 py-3 text-sm text-state-danger">
            {error}
          </div>
        )}

        {loading ? (
          <div className="rounded-xl bg-white p-12 text-center text-sm text-salvi-muted shadow-sm">
            {t('actions.loading')}
          </div>
        ) : summary.length === 0 ? (
          <div className="rounded-xl border border-salvi-line bg-white p-12 text-center shadow-sm">
            <div className="text-3xl">📍</div>
            <h3 className="mt-3 text-base font-semibold text-salvi-black">{t('zones.empty.title')}</h3>
            <p className="mt-1 text-sm text-salvi-muted">{t('zones.empty.subtitle')}</p>
            <Button variant="primary" className="mt-5" onClick={onCreateZone}>
              + {t('zones.new')}
            </Button>
          </div>
        ) : (
          <div className="space-y-3">
            {summary.map(s => {
              const jobState = s.study.job_state;
              const jobStyle = jobState ? (JOB_STYLE[jobState] || 'bg-salvi-surface text-salvi-grey') : 'bg-salvi-surface text-salvi-grey';
              const jobLabel = jobState ? (JOB_LABEL[jobState] || jobState) : t('zones.study.none');
              return (
                <article
                  key={s.zone.id}
                  className="rounded-xl border border-salvi-line bg-white p-4 shadow-sm transition-shadow hover:shadow-md"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex min-w-0 items-center gap-3">
                      <div className="h-10 w-10 shrink-0 rounded-full opacity-90" style={{ backgroundColor: s.zone.color }} />
                      <div className="min-w-0">
                        <h4 className="truncate text-sm font-semibold text-salvi-black" title={s.zone.name}>
                          {s.zone.name}
                        </h4>
                        <p className="text-xs text-salvi-muted">
                          {s.zone.type || '—'} · {t('zones.updated', { date: formatDate(s.planning.updated_at ?? s.osm.loaded_at ?? null) })}
                        </p>
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${jobStyle}`}>{jobLabel}</span>
                      <Button variant="primary" onClick={() => onOpenZone(s.zone.id)}>
                        {t('zones.openMap')}
                      </Button>
                      <button
                        type="button"
                        onClick={() => handleDelete(s.zone.id, s.zone.name)}
                        disabled={pendingDelete === s.zone.id}
                        className="rounded-lg border border-[#B42318]/25 px-2.5 py-2 text-sm font-semibold text-[#B42318] transition-colors hover:bg-[#FDECEA] disabled:opacity-50"
                        title={t('zone.delete')}
                      >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="3 6 5 6 21 6" />
                          <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                          <path d="M10 11v6M14 11v6" />
                          <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
                        </svg>
                      </button>
                    </div>
                  </div>

                  <dl className="mt-4 grid grid-cols-2 gap-2 md:grid-cols-5">
                    <div className="rounded-lg bg-salvi-surface/60 p-2.5">
                      <dt className="text-[10px] font-semibold uppercase tracking-wide text-salvi-muted">{t('zones.stat.streets')}</dt>
                      <dd className="mt-0.5 text-sm font-semibold text-salvi-black">
                        {s.osm.loaded ? s.osm.distinct_name_count : '—'}
                        <span className="text-xs font-normal text-salvi-muted"> / {s.osm.loaded ? s.osm.segment_count : '0'} {t('zones.stat.segments')}</span>
                      </dd>
                    </div>
                    <div className="rounded-lg bg-salvi-surface/60 p-2.5">
                      <dt className="text-[10px] font-semibold uppercase tracking-wide text-salvi-muted">{t('zones.stat.kilometers')}</dt>
                      <dd className="mt-0.5 text-sm font-semibold text-salvi-black">
                        {s.osm.loaded ? `${s.osm.length_km} km` : '—'}
                      </dd>
                    </div>
                    <div className="rounded-lg bg-salvi-surface/60 p-2.5">
                      <dt className="text-[10px] font-semibold uppercase tracking-wide text-salvi-muted">{t('zones.stat.selected')}</dt>
                      <dd className="mt-0.5 text-sm font-semibold text-salvi-black">
                        {s.selection.count}
                        <span className="text-xs font-normal text-salvi-muted"> / {s.osm.segment_count} {t('zones.stat.segments')}</span>
                      </dd>
                    </div>
                    <div className="rounded-lg bg-salvi-surface/60 p-2.5">
                      <dt className="text-[10px] font-semibold uppercase tracking-wide text-salvi-muted">{t('zones.stat.route')}</dt>
                      <dd className="mt-0.5 text-sm font-semibold text-salvi-black">
                        {s.scope.current && s.scope.length_m ? `${Math.round(s.scope.length_m)} m` : '—'}
                        <span className="text-xs font-normal text-salvi-muted"> / {s.scope.member_count}</span>
                      </dd>
                    </div>
                    <div className="rounded-lg bg-salvi-surface/60 p-2.5">
                      <dt className="text-[10px] font-semibold uppercase tracking-wide text-salvi-muted">{t('zones.stat.luminaires')}</dt>
                      <dd className="mt-0.5 text-sm font-semibold text-salvi-black">{s.luminaires}</dd>
                    </div>
                  </dl>
                </article>
              );
            })}
          </div>
        )}
      </div>
    </main>
  );
};

export default ProjectDetailPage;
