import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { useI18n } from '../i18n';
import {
  ProjectFormModal,
} from '../components/projects';
import {
  EmptyTramosState,
  TramosTable,
  ConfirmModal,
  ImportTramosExcelModal,
  BulkEditModal,
} from '../components/tramos';
import { getProject, updateProject, type ProjectRecord } from '../lib/projects';
import {
  listTramos,
  getTramo,
  createTramo,
  updateTramo,
  deleteTramo,
  duplicateTramo,
  bulkDeleteTramos,
  startBulkCalculate,
  pollBulkProgress,
  cancelBulkCalculate,
  downloadTramoDocument,
  downloadBatchPdf,
  downloadBatchExcel,
  type BulkCalculateFailure,
  type TramoSummary,
} from '../lib/tramos';
import { useConfigStore } from '../store/useConfigStore';
import { buildCalculationRequest, configHash, withHash } from '../lib/tramoRequest';
import { downloadTemplate } from '../lib/tramosExcelImport';
import { triggerDownload } from '../lib/download';
import type { TramoRecord } from '../types';

const ProjectTramosPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { authFetch } = useAuth();
  const { t } = useI18n();
  const dirty = useConfigStore(state => state.dirty);
  const lastEditedTramoId = useConfigStore(state => state.lastEditedTramoId);
  const setLastEditedTramo = useConfigStore(state => state.setLastEditedTramo);
  const lastOpenedTramoId = useConfigStore(state => state.lastOpenedTramoId);
  const lastOpenedTramoProjectId = useConfigStore(state => state.lastOpenedTramoProjectId);
  const setLastOpenedTramo = useConfigStore(state => state.setLastOpenedTramo);
  const markSaved = useConfigStore(state => state.markSaved);
  const reset = useConfigStore(state => state.reset);
  const configTAmbC = useConfigStore(state => state.t_amb_c);
  const setTAmbC = useConfigStore(state => state.setTAmbC);
  const configMargenLavg = useConfigStore(state => state.margen_lavg);
  const setMargenLavg = useConfigStore(state => state.setMargenLavg);
  const configIOpMa = useConfigStore(state => state.i_op_ma);
  const setIOpMa = useConfigStore(state => state.setIOpMa);
  const configLmWMin = useConfigStore(state => state.lm_w_min);
  const setLmWMin = useConfigStore(state => state.setLmWMin);
  const [tAmbCDraft, setTAmbCDraft] = useState<string | null>(null);
  const [margenLavgDraft, setMargenLavgDraft] = useState<string | null>(null);
  const [iOpMaDraft, setIOpMaDraft] = useState<string | null>(null);
  const [lmWMinDraft, setLmWMinDraft] = useState<string | null>(null);

  const projectId = id ? Number(id) : null;

  const [project, setProject] = useState<ProjectRecord | null>(null);
  const [tramos, setTramos] = useState<TramoSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingProject, setEditingProject] = useState<ProjectRecord | null>(null);
  const [projectConfigOpen, setProjectConfigOpen] = useState(false);

  const [busyTramoIds, setBusyTramoIds] = useState<Set<number>>(new Set());
  const [batchDownloading, setBatchDownloading] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<TramoSummary | null>(null);
  const [selectedTramoIds, setSelectedTramoIds] = useState<Set<number>>(new Set());
  const [confirmBulkDelete, setConfirmBulkDelete] = useState(false);
  const [bulkEditOpen, setBulkEditOpen] = useState(false);

  const [showNewTramoModal, setShowNewTramoModal] = useState(false);
  const [newTramoName, setNewTramoName] = useState('');
  const [creatingTramo, setCreatingTramo] = useState(false);
  const [createTramoError, setCreateTramoError] = useState<string | null>(null);
  const newTramoInputRef = React.useRef<HTMLInputElement>(null);

  const [showImportModal, setShowImportModal] = useState(false);
  const [flashTramoId, setFlashTramoId] = useState<number | null>(null);
  const [bulkCalculating, setBulkCalculating] = useState(false);
  const [bulkCalculateProgress, setBulkCalculateProgress] = useState<{
    batchId: string; total: number; completed: number; failed: number; compliant: number; nonCompliant: number; cancelled?: boolean;
  } | null>(null);
  const [bulkCalculateResult, setBulkCalculateResult] = useState<
    { successCount: number; failed: BulkCalculateFailure[]; cancelled?: boolean } | null
  >(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const pollingRef = React.useRef<number | null>(null);
  const bulkLocked = bulkCalculating && !bulkCalculateProgress?.cancelled;
  const timerRef = React.useRef<number | null>(null);

  useEffect(() => {
    if (!bulkLocked) {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      return;
    }
    timerRef.current = window.setInterval(() => {
      setElapsedSeconds(s => s + 1);
    }, 1000) as unknown as number;
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [bulkLocked]);

  const setBusy = (tramoId: number, busy: boolean) => {
    setBusyTramoIds(prev => {
      const next = new Set(prev);
      if (busy) next.add(tramoId);
      else next.delete(tramoId);
      return next;
    });
  };

  const loadAll = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const [proj, ts] = await Promise.all([
        getProject(authFetch, projectId),
        listTramos(authFetch, projectId),
      ]);
      setProject(proj);
      setTramos(ts);
    } catch (err: any) {
      setError(err.message || t('errors.unknown'));
    } finally {
      setLoading(false);
    }
  }, [projectId, authFetch, t]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  useEffect(() => {
    if (!project) return;
    setTAmbC(project.t_amb_c ?? 25);
    setMargenLavg(project.margen_lavg ?? 0);
    setIOpMa(project.i_op_ma ?? null);
    setLmWMin(project.lm_w_min ?? null);
  }, [project, setTAmbC, setMargenLavg, setIOpMa, setLmWMin]);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => { if (pollingRef.current) clearTimeout(pollingRef.current); };
  }, []);

  useEffect(() => {
    if (!bulkLocked) return;
    const block = (event: MouseEvent) => {
      const link = (event.target as HTMLElement | null)?.closest('a[href]');
      if (!link) return;
      event.preventDefault();
      event.stopPropagation();
    };
    const stay = () => window.history.pushState(null, '', window.location.href);
    window.history.pushState(null, '', window.location.href);
    document.addEventListener('click', block, true);
    window.addEventListener('popstate', stay);
    return () => {
      document.removeEventListener('click', block, true);
      window.removeEventListener('popstate', stay);
    };
  }, [bulkLocked]);

  // After a successful save in the editor, the dirty flag is cleared. We also
  // clear `lastEditedTramoId` so the list doesn't show a stale dirty badge.
  useEffect(() => {
    if (!dirty && lastEditedTramoId) {
      setLastEditedTramo(null);
    }
  }, [dirty, lastEditedTramoId, setLastEditedTramo]);

  const handleNew = () => {
    if (!projectId || bulkLocked) return;
    setNewTramoName('');
    setCreateTramoError(null);
    setShowNewTramoModal(true);
  };

  const closeNewTramoModal = () => {
    if (creatingTramo) return;
    setShowNewTramoModal(false);
    setNewTramoName('');
    setCreateTramoError(null);
  };

  const handleConfirmNewTramo = async () => {
    if (!projectId || creatingTramo) return;
    const name = newTramoName.trim();
    if (!name) {
      setCreateTramoError(' ');
      newTramoInputRef.current?.focus();
      return;
    }
    setCreatingTramo(true);
    setCreateTramoError(null);
    try {
      reset();
      const request = buildCalculationRequest();
      const hash = configHash(request);
      const saved = await createTramo(authFetch, projectId, {
        name,
        config_json: withHash(request, hash),
      });
      markSaved({
        configJson: saved.config_json ?? withHash(request, hash),
        resultJson: saved.result_json ?? null,
      });
      setLastEditedTramo(saved.id);
      setShowNewTramoModal(false);
      setNewTramoName('');
      navigate(`/projects/${projectId}/tramos/${saved.id}`);
    } catch (err: any) {
      setCreateTramoError(err.message || t('tramos.create.error'));
    } finally {
      setCreatingTramo(false);
    }
  };

  const handleOpen = (tramo: TramoSummary) => {
    if (bulkLocked) return;
    const targetProjectId = tramo.project_id || projectId;
    if (!targetProjectId || !tramo.id) return;
    setLastOpenedTramo(targetProjectId, tramo.id);
    navigate(`/projects/${targetProjectId}/tramos/${tramo.id}`);
  };

  const lastOpenedTramo = useMemo(
    () =>
      lastOpenedTramoProjectId === projectId && lastOpenedTramoId !== null
        ? tramos.find(t => t.id === lastOpenedTramoId) ?? null
        : null,
    [tramos, lastOpenedTramoId, lastOpenedTramoProjectId, projectId],
  );

  const handleJumpToLastTramo = useCallback(() => {
    if (!lastOpenedTramo || bulkLocked) return;
    setFlashTramoId(lastOpenedTramo.id);
    const el = document.getElementById(`tramo-row-${lastOpenedTramo.id}`);
    el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    window.setTimeout(() => setFlashTramoId(null), 1000);
  }, [lastOpenedTramo, bulkLocked]);

  const handleRename = async (tramo: TramoSummary, next: string) => {
    if (bulkLocked) return;
    setBusy(tramo.id, true);
    try {
      const updated = await updateTramo(authFetch, projectId!, tramo.id, { name: next });
      setTramos(prev => prev.map(t => (t.id === tramo.id ? { ...t, name: updated.name } : t)));
    } catch (err: any) {
      setError(err.message || t('errors.unknown'));
    } finally {
      setBusy(tramo.id, false);
    }
  };

  const handleDuplicate = async (tramo: TramoSummary) => {
    if (bulkLocked) return;
    setBusy(tramo.id, true);
    try {
      await duplicateTramo(authFetch, projectId!, tramo.id);
      await loadAll();
    } catch (err: any) {
      setError(err.message || t('errors.unknown'));
    } finally {
      setBusy(tramo.id, false);
    }
  };

  const handleDelete = async () => {
    if (!confirmDelete || bulkLocked) return;
    const target = confirmDelete;
    setBusy(target.id, true);
    try {
      await deleteTramo(authFetch, projectId!, target.id);
      setTramos(prev => prev.filter(t => t.id !== target.id));
      if (lastEditedTramoId === target.id) {
        setLastEditedTramo(null);
      }
      if (lastOpenedTramoId === target.id) {
        setLastOpenedTramo(null, null);
      }
      setConfirmDelete(null);
    } catch (err: any) {
      setError(err.message || t('errors.unknown'));
    } finally {
      setBusy(target.id, false);
    }
  };

  const handleBulkDelete = async () => {
    if (selectedTramoIds.size === 0 || bulkLocked) return;
    const ids = Array.from(selectedTramoIds);
    ids.forEach(id => setBusy(id, true));
    try {
      await bulkDeleteTramos(authFetch, projectId!, ids);
      setTramos(prev => prev.filter(t => !selectedTramoIds.has(t.id)));
      if (lastEditedTramoId && selectedTramoIds.has(lastEditedTramoId)) {
        setLastEditedTramo(null);
      }
      if (lastOpenedTramoId && selectedTramoIds.has(lastOpenedTramoId)) {
        setLastOpenedTramo(null, null);
      }
      setSelectedTramoIds(new Set());
      setConfirmBulkDelete(false);
    } catch (err: any) {
      setError(err.message || t('errors.unknown'));
      setConfirmBulkDelete(false);
    } finally {
      ids.forEach(id => setBusy(id, false));
    }
  };

  const handleBulkCalculate = async () => {
    if (selectedTramoIds.size === 0 || bulkCalculating) return;
    setElapsedSeconds(0);
    setBulkCalculating(true);
    setError(null);
    setBulkCalculateResult(null);
    const ids = Array.from(selectedTramoIds);
    try {
      const margenLavg = parseFloat(margenLavgDraft ?? String(configMargenLavg));
      const margenValue = Number.isFinite(margenLavg) ? margenLavg : 0;
      if (project && project.margen_lavg !== margenValue) {
        setMargenLavg(margenValue);
        await updateProject(authFetch, projectId!, { project_name: project.project_name, margen_lavg: margenValue });
        setProject(p => p ? { ...p, margen_lavg: margenValue } : null);
        setMargenLavgDraft(null);
      }
      const status = await startBulkCalculate(authFetch, projectId!, ids, margenValue);
      setBulkCalculateProgress({ batchId: status.batch_id, total: status.total, completed: 0, failed: 0, compliant: 0, nonCompliant: 0, cancelled: false });

      const poll = async () => {
        try {
          const prog = await pollBulkProgress(authFetch, projectId!, status.batch_id);
          setBulkCalculateProgress({
            batchId: status.batch_id,
            total: prog.total,
            completed: prog.completed,
            failed: prog.failed,
            compliant: prog.items.filter(i => i.status === 'done' && i.compliant === true).length,
            nonCompliant: prog.items.filter(i => i.status === 'done' && i.compliant === false).length,
            cancelled: prog.cancelled,
          });
          if (!prog.cancelled && prog.completed < prog.total) {
            pollingRef.current = window.setTimeout(poll, 1500);
          } else {
            try {
              const ts = await listTramos(authFetch, projectId!);
              setTramos(ts);
            } catch {
              // ponytail: status reload is best-effort; manual refresh still recovers.
            }
            setBulkCalculating(false);
            setBulkCalculateProgress(null);
            const failures = prog.items.filter(i => i.status === 'error').map(i => ({ id: i.id, name: i.name, error: i.error || '' }));
            setBulkCalculateResult({
              successCount: prog.items.filter(i => i.status === 'done').length,
              failed: failures,
              cancelled: prog.cancelled,
            });
          }
        } catch {
          pollingRef.current = window.setTimeout(poll, 3000);
        }
      };
      pollingRef.current = window.setTimeout(poll, 1000);
    } catch (err: any) {
      setError(err.message || t('errors.unknown'));
      setBulkCalculating(false);
    }
  };

  const handleSaveProjectConfig = async () => {
    if (!project || !projectId) return;
    const parseOptional = (raw: string | null, fallback: number | null) => {
      const value = (raw ?? (fallback == null ? '' : String(fallback))).trim();
      if (!value) return null;
      const parsed = parseFloat(value.replace(',', '.'));
      return Number.isFinite(parsed) ? parsed : fallback;
    };
    const tAmb = parseFloat((tAmbCDraft ?? String(configTAmbC)).replace(',', '.'));
    const margen = parseFloat((margenLavgDraft ?? String(configMargenLavg)).replace(',', '.'));
    const next = {
      t_amb_c: Number.isFinite(tAmb) ? tAmb : configTAmbC,
      margen_lavg: Number.isFinite(margen) ? margen : configMargenLavg,
      i_op_ma: parseOptional(iOpMaDraft, configIOpMa),
      lm_w_min: parseOptional(lmWMinDraft, configLmWMin),
    };
    setTAmbC(next.t_amb_c);
    setMargenLavg(next.margen_lavg);
    setIOpMa(next.i_op_ma);
    setLmWMin(next.lm_w_min);
    const saved = await updateProject(authFetch, projectId, { project_name: project.project_name, ...next });
    setProject(saved);
    setTAmbCDraft(null);
    setMargenLavgDraft(null);
    setIOpMaDraft(null);
    setLmWMinDraft(null);
    setProjectConfigOpen(false);
  };

  const handleCancelBulkCalculate = async () => {
    if (!projectId || !bulkCalculateProgress) return;
    try {
      await cancelBulkCalculate(authFetch, projectId, bulkCalculateProgress.batchId);
      setBulkCalculateProgress(prev => prev ? { ...prev, cancelled: true } : prev);
    } catch (err: any) {
      setError(err.message || t('errors.unknown'));
    }
  };

  const handleDownloadPdf = async (tramo: TramoSummary) => {
    if (!tramo.has_result || bulkLocked) return;
    setBusy(tramo.id, true);
    try {
      console.debug('[tramos] download pdf', { tramoId: tramo.id, documentId: tramo.document_ids.pdf });
      const blob = tramo.document_ids.pdf
        ? await downloadTramoDocument(authFetch, projectId!, tramo.id, tramo.document_ids.pdf)
        : await generateTramoReport(tramo, 'pdf');
      triggerDownload(blob, `${tramo.name}.pdf`);
    } catch (err: any) {
      setError(err.message || t('errors.unknown'));
    } finally {
      setBusy(tramo.id, false);
    }
  };

  const handleDownloadExcel = async (tramo: TramoSummary) => {
    if (!tramo.has_result || bulkLocked) return;
    setBusy(tramo.id, true);
    try {
      console.debug('[tramos] download excel', { tramoId: tramo.id, documentId: tramo.document_ids.excel });
      const blob = tramo.document_ids.excel
        ? await downloadTramoDocument(authFetch, projectId!, tramo.id, tramo.document_ids.excel)
        : await generateTramoReport(tramo, 'excel');
      triggerDownload(blob, `${tramo.name}.xlsx`);
    } catch (err: any) {
      setError(err.message || t('errors.unknown'));
    } finally {
      setBusy(tramo.id, false);
    }
  };

  const handleDownloadBatchPdf = async () => {
    if (selectedTramoIds.size === 0 || bulkLocked) return;
    if (selectedTramoIds.size > 2000) {
      setError(t('tramos.bulkDownload.tooMany'));
      return;
    }
    const ids = Array.from(selectedTramoIds);
    const selectedTramos = tramos.filter(tr => ids.includes(tr.id));
    const hasResults = selectedTramos.every(tr => tr.has_result);
    if (!hasResults) {
      setError(t('tramos.bulkDownload.noResults'));
      return;
    }
    setBatchDownloading(true);
    setBusyTramoIds(new Set(ids));
    try {
      const blob = await downloadBatchPdf(authFetch, ids);
      triggerDownload(blob, `${project?.project_name ?? 'LUX'}_Report.pdf`);
    } catch (err: any) {
      setError(err.message || t('errors.unknown'));
    } finally {
      setBusyTramoIds(new Set());
      setBatchDownloading(false);
    }
  };

  const handleDownloadBatchExcel = async () => {
    if (selectedTramoIds.size === 0 || bulkLocked) return;
    if (selectedTramoIds.size > 2000) {
      setError(t('tramos.bulkDownload.tooMany'));
      return;
    }
    const ids = Array.from(selectedTramoIds);
    const selectedTramos = tramos.filter(tr => ids.includes(tr.id));
    const hasResults = selectedTramos.every(tr => tr.has_result);
    if (!hasResults) {
      setError(t('tramos.bulkDownload.noResults'));
      return;
    }
    setBatchDownloading(true);
    setBusyTramoIds(new Set(ids));
    try {
      const blob = await downloadBatchExcel(authFetch, ids);
      triggerDownload(blob, `${project?.project_name ?? 'LUX'}_Results.xlsx`);
    } catch (err: any) {
      setError(err.message || t('errors.unknown'));
    } finally {
      setBusyTramoIds(new Set());
      setBatchDownloading(false);
    }
  };

  const generateTramoReport = async (tramo: TramoSummary, format: 'pdf' | 'excel') => {
    const config = await loadTramoReportConfig(tramo);
    const endpoint = format === 'pdf' ? '/api/report/generate' : '/api/report/excel';
    const response = await authFetch(`${endpoint}?tramo_id=${tramo.id}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => null);
      throw new Error(data?.detail || t('errors.unknown'));
    }
    await loadAll();
    return response.blob();
  };

  const loadTramoReportConfig = async (tramo: TramoSummary) => {
    const full = await getTramo(authFetch, projectId!, tramo.id);
    const configJson = full.config_json;
    if (!configJson) throw new Error(t('errors.unknown'));
    const config = JSON.parse(configJson);
    delete config.__configHash;
    return config;
  };

  const handleProjectSaved = (saved: ProjectRecord) => {
    setProject(saved);
  };

  if (loading && !project) {
    return (
      <main className="p-6">
        <div className="mx-auto max-w-7xl">
          <div className="rounded-xl border border-[#E8E2D8] bg-[#FFFFFF] p-12 text-center text-[#6a6a6a]">
            {t('actions.loading')}
          </div>
        </div>
      </main>
    );
  }

  if (error && !project) {
    return (
      <main className="p-6">
        <div className="mx-auto max-w-3xl text-center">
          <div className="rounded-xl border border-[#B42318]/25 bg-[#FDECEA] p-8">
            <p className="text-[#B42318]">{error}</p>
            <button
              type="button"
              onClick={() => navigate('/projects')}
              className="mt-4 rounded-lg bg-[#1E1E1E] px-4 py-2 text-sm font-semibold text-white hover:bg-[#333333]"
            >
              {t('projects.editor.backToList')}
            </button>
          </div>
        </div>
      </main>
    );
  }

  if (!project) return null;

  const dirtyTramoIds = new Set<number>();
  if (dirty && lastEditedTramoId) {
    dirtyTramoIds.add(lastEditedTramoId);
  }

  return (
    <main className="p-6">
      <div className="mx-auto max-w-7xl">
        <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <nav className="flex items-center gap-2 text-sm text-[#A09A91]">
            {bulkLocked ? (
              <span className="font-medium text-[#6a6a6a]">{t('projects.title')}</span>
            ) : (
              <Link to="/projects" className="font-medium text-[#1E1E1E] hover:text-[#333333]">
                {t('projects.title')}
              </Link>
            )}
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="9 18 15 12 9 6" />
            </svg>
            <span className="truncate font-semibold text-[#6A6A6A]" title={project.project_name}>
              {project.project_name}
            </span>
          </nav>
        </div>

        <div className="mb-6 flex flex-col gap-4 rounded-xl border border-[#E8E2D8] bg-[#FFFFFF] p-5 shadow-sm sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <h2 className="truncate text-xl font-semibold text-[#1E1E1E]" title={project.project_name}>
              {project.project_name}
            </h2>
            <p className="mt-0.5 text-sm text-[#A09A91]">
              {[project.client, project.location].filter(Boolean).join(' · ') || '—'}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-3">
            <button
              type="button"
              onClick={() => setProjectConfigOpen(true)}
              disabled={bulkLocked}
              className="rounded-lg border border-[#E8E2D8] px-3 py-2 text-sm font-semibold text-[#6A6A6A] hover:bg-[#F7F4EF] disabled:opacity-50"
              >
                Configuración de proyecto
            </button>
            {lastOpenedTramo && (
              <button
                type="button"
                onClick={handleJumpToLastTramo}
                disabled={bulkLocked}
                title={t('tramos.lastOpened.jump')}
                className="inline-flex max-w-[180px] items-center gap-1.5 rounded-lg border border-[#1E1E1E]/15 bg-[#1E1E1E]/6 px-3 py-2 text-sm font-semibold text-[#333333] hover:bg-blue-100 disabled:opacity-50"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <polyline points="9 14 4 9 9 4" />
                  <path d="M20 20v-7a4 4 0 0 0-4-4H4" />
                </svg>
                <span className="truncate">{t('tramos.lastOpened.label')}: {lastOpenedTramo.name}</span>
              </button>
            )}
            <button
              type="button"
              onClick={() => setShowImportModal(true)}
              disabled={bulkLocked}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[#1F7A4D]/25 bg-[#1F7A4D]/10 px-3 py-2 text-sm font-semibold text-[#1F7A4D] hover:bg-[#1F7A4D]/20 disabled:opacity-50"
              title={t('tramos.import.buttonHint')}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="17 8 12 3 7 8" />
                <line x1="12" y1="3" x2="12" y2="15" />
              </svg>
              {t('tramos.import.button')}
            </button>
            <button
              type="button"
              onClick={downloadTemplate}
              className="inline-flex items-center gap-1.5 rounded-lg border border-[#E8E2D8] px-3 py-2 text-sm font-semibold text-[#6A6A6A] hover:bg-[#F7F4EF]"
              title={t('tramos.import.downloadTemplate')}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
              {t('tramos.import.downloadTemplate')}
            </button>
            <button
              type="button"
              onClick={() => setEditingProject(project)}
              disabled={bulkLocked}
              className="rounded-lg border border-[#E8E2D8] px-3 py-2 text-sm font-semibold text-[#6A6A6A] hover:bg-[#F7F4EF] disabled:opacity-50"
              >
                {t('tramos.editProject')}
            </button>
            <button
              type="button"
              onClick={handleNew}
              disabled={bulkLocked}
              className="inline-flex items-center gap-1.5 rounded-lg bg-[#1E1E1E] px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-[#333333] disabled:opacity-50"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="5" x2="12" y2="19" />
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
              {t('tramos.new')}
            </button>
          </div>
        </div>

        {error && (
          <div className="mb-6 rounded-lg border border-[#B42318]/25 bg-[#FDECEA] px-4 py-3 text-sm text-[#B42318]">
            {error}
          </div>
        )}

        {bulkCalculateResult && (bulkCalculateResult.successCount > 0 || bulkCalculateResult.failed.length > 0) && (
          <div className="mb-4 rounded-lg border border-[#E8E2D8] bg-[#FFFFFF] px-4 py-3 text-sm text-[#6A6A6A] shadow-sm">
            <div className="flex items-center justify-between gap-3">
              <span>
                <strong className="text-[#1F7A4D]">{bulkCalculateResult.successCount}</strong> OK
                {bulkCalculateResult.cancelled && (
                  <>
                    {' · '}
                    <strong className="text-[#6A6A6A]">{t('tramos.bulkCalculate.cancelled')}</strong>
                  </>
                )}
                {bulkCalculateResult.failed.length > 0 && (
                  <>
                    {' · '}
                    <strong className="text-amber-700">{bulkCalculateResult.failed.length}</strong> {t('tramos.bulkCalculate.failed', { count: bulkCalculateResult.failed.length })}
                  </>
                )}
              </span>
              <button
                type="button"
                onClick={() => setBulkCalculateResult(null)}
                className="text-[#6a6a6a] hover:text-[#6A6A6A]"
              >
                ×
              </button>
            </div>
            {bulkCalculateResult.failed.length > 0 && (
              <details className="mt-2 text-xs text-[#6A6A6A]">
                <summary className="cursor-pointer">{t('tramos.bulkCalculate.showErrors')}</summary>
                <ul className="mt-2 list-disc space-y-1 pl-5">
                  {bulkCalculateResult.failed.map(f => (
                    <li key={f.id}>
                      <span className="font-semibold">{f.name}</span>: {f.error}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        )}

        {bulkCalculateProgress && (
          <div className="mb-3 rounded-lg border border-[#1E1E1E]/15 bg-[#1E1E1E]/6 px-4 py-3 text-sm text-[#1E1E1E] shadow-sm">
            <div className="flex items-center justify-between gap-3">
              <span className="font-medium">
                {bulkCalculateProgress.cancelled ? t('tramos.bulkCalculate.stopping') : t('tramos.bulkCalculate.calculating')} {bulkCalculateProgress.completed}/{bulkCalculateProgress.total} tramos
                {bulkCalculateProgress.failed > 0 && (
                  <span className="ml-2 text-amber-700">({bulkCalculateProgress.failed} errores)</span>
                )}
              </span>
              <div className="flex shrink-0 items-center gap-2">
                <button
                  type="button"
                  onClick={handleCancelBulkCalculate}
                  disabled={bulkCalculateProgress.cancelled}
                  className="rounded-md border border-[#1E1E1E]/20 bg-[#FFFFFF] px-2.5 py-1 text-xs font-semibold text-[#1E1E1E] hover:bg-blue-100 disabled:opacity-50"
                >
                  {t('tramos.bulkCalculate.stop')}
                </button>
                <svg className="h-5 w-5 animate-spin text-[#1E1E1E]" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              </div>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1 rounded-full bg-[#1E1E1E]/6 px-2.5 py-0.5 text-xs font-semibold text-[#333333]">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" /></svg>
                {`${Math.floor(elapsedSeconds / 60).toString().padStart(2, '0')}:${(elapsedSeconds % 60).toString().padStart(2, '0')}`}
              </span>
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-semibold text-[#1F7A4D]">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
                {t('tramos.bulkCalculate.compliantCount', { count: bulkCalculateProgress.compliant })}
              </span>
              <span className="inline-flex items-center gap-1 rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-semibold text-[#B42318]">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
                {t('tramos.bulkCalculate.nonCompliantCount', { count: bulkCalculateProgress.nonCompliant })}
              </span>
            </div>
            <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-[#1E1E1E]/30">
              <div className="h-full rounded-full bg-[#1E1E1E] transition-all duration-500" style={{ width: `${(bulkCalculateProgress.completed / Math.max(bulkCalculateProgress.total, 1)) * 100}%` }} />
            </div>
          </div>
        )}

        {tramos.length === 0 ? (
          <EmptyTramosState onCreate={handleNew} />
        ) : (
          <>
            {selectedTramoIds.size > 0 && (
              <div className="mb-3 flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setBulkEditOpen(true)}
                  disabled={bulkLocked}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-[#1E1E1E] px-3 py-2 text-sm font-semibold text-white hover:bg-[#333333] disabled:opacity-50"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                  </svg>
                  {t('tramos.bulkEdit.button', { count: selectedTramoIds.size })}
                </button>
                <button
                  type="button"
                  onClick={handleBulkCalculate}
                  disabled={bulkCalculating}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-[#1F7A4D] px-3 py-2 text-sm font-semibold text-white hover:bg-[#16633E] disabled:opacity-50"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
                  </svg>
                  {bulkCalculating ? t('tramos.bulkCalculate.calculating') : t('tramos.bulkCalculate.button', { count: selectedTramoIds.size })}
                </button>
                <button
                  type="button"
                  onClick={handleDownloadBatchPdf}
                  disabled={batchDownloading || bulkLocked}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-[#B42318] px-3 py-2 text-sm font-semibold text-white hover:bg-[#8A2A1E] disabled:opacity-50"
                >
                  {batchDownloading ? (
                    <svg className="animate-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10" strokeDasharray="32" strokeDashoffset="32" strokeLinecap="round" /></svg>
                  ) : (
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                      <polyline points="14 2 14 8 20 8" />
                      <line x1="12" y1="18" x2="12" y2="9" />
                      <polyline points="9 12 12 9 15 12" />
                    </svg>
                  )}
                  {batchDownloading ? t('tramos.bulkDownload.downloading') : t('tramos.bulkDownload.pdf', { count: selectedTramoIds.size })}
                </button>
                <button
                  type="button"
                  onClick={handleDownloadBatchExcel}
                  disabled={batchDownloading || bulkLocked}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-amber-600 px-3 py-2 text-sm font-semibold text-white hover:bg-amber-700 disabled:opacity-50"
                >
                  {batchDownloading ? (
                    <svg className="animate-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10" strokeDasharray="32" strokeDashoffset="32" strokeLinecap="round" /></svg>
                  ) : (
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                      <polyline points="7 10 12 15 17 10" />
                      <line x1="12" y1="15" x2="12" y2="3" />
                    </svg>
                  )}
                  {batchDownloading ? t('tramos.bulkDownload.downloading') : t('tramos.bulkDownload.excel', { count: selectedTramoIds.size })}
                </button>
                <button
                  type="button"
                  onClick={() => setConfirmBulkDelete(true)}
                  disabled={bulkLocked}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-[#B42318] px-3 py-2 text-sm font-semibold text-white hover:bg-[#8A2A1E] disabled:opacity-50"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="3 6 5 6 21 6" />
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                  </svg>
                  {t('tramos.bulkDelete.button', { count: selectedTramoIds.size })}
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedTramoIds(new Set())}
                  disabled={bulkLocked}
                  className="rounded-lg border border-[#E8E2D8] px-3 py-2 text-sm font-semibold text-[#6A6A6A] hover:bg-[#F7F4EF] disabled:opacity-50"
                >
                  {t('tramos.bulkDelete.clear')}
                </button>
              </div>
            )}
            <TramosTable
              tramos={tramos}
              dirtyTramoIds={dirtyTramoIds}
              busyTramoIds={busyTramoIds}
              flashTramoId={flashTramoId}
              selectedIds={selectedTramoIds}
              onSelectionChange={setSelectedTramoIds}
              onOpen={handleOpen}
              onRename={handleRename}
              onDuplicate={handleDuplicate}
              onDelete={tramo => setConfirmDelete(tramo)}
              onDownloadPdf={handleDownloadPdf}
              onDownloadExcel={handleDownloadExcel}
              onLoadMeasurementsConfig={loadTramoReportConfig}
              locked={bulkLocked}
            />
          </>
        )}
      </div>

      <ProjectFormModal
        open={editingProject !== null}
        onClose={() => setEditingProject(null)}
        onSaved={handleProjectSaved}
        initialProject={editingProject}
      />

      <ConfirmModal
        open={confirmDelete !== null}
        title={t('actions.delete')}
        message={confirmDelete ? t('tramos.confirmDelete', { name: confirmDelete.name }) : ''}
        confirmLabel={t('actions.delete')}
        cancelLabel={t('unsavedChanges.cancel')}
        destructive
        busy={confirmDelete ? busyTramoIds.has(confirmDelete.id) : false}
        onConfirm={handleDelete}
        onCancel={() => setConfirmDelete(null)}
      />

      <ConfirmModal
        open={confirmBulkDelete}
        title={t('tramos.bulkDelete.title')}
        message={t('tramos.bulkDelete.message', { count: selectedTramoIds.size })}
        confirmLabel={t('actions.delete')}
        cancelLabel={t('unsavedChanges.cancel')}
        destructive
        busy={false}
        onConfirm={handleBulkDelete}
        onCancel={() => setConfirmBulkDelete(false)}
      />

      <BulkEditModal
        open={bulkEditOpen}
        selectedIds={selectedTramoIds}
        projectId={projectId!}
        authFetch={authFetch}
        onClose={() => setBulkEditOpen(false)}
        onUpdated={loadAll}
      />

      {showNewTramoModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/20 px-4">
          <div className="w-full max-w-md rounded-xl bg-[#FFFFFF] shadow-2xl">
            <div className="border-b border-[#E8E2D8] px-6 py-4">
              <h2 className="text-base font-semibold text-[#1E1E1E]">{t('tramos.create.title')}</h2>
            </div>
            <div className="px-6 py-4">
              <label className="block text-sm font-medium text-[#6A6A6A]">
                {t('tramos.create.nameLabel')}
                <input
                  ref={newTramoInputRef}
                  autoFocus
                  value={newTramoName}
                  onChange={event => {
                    setNewTramoName(event.target.value);
                    if (createTramoError) setCreateTramoError(null);
                  }}
                  onKeyDown={event => {
                    if (event.key === 'Enter') {
                      event.preventDefault();
                      handleConfirmNewTramo();
                    } else if (event.key === 'Escape') {
                      event.preventDefault();
                      closeNewTramoModal();
                    }
                  }}
                  maxLength={255}
                  placeholder={t('tramos.create.namePlaceholder')}
                  disabled={creatingTramo}
                  className={`mt-1 w-full rounded-md border bg-[#FFFFFF] px-3 py-2 text-sm text-[#1E1E1E] outline-none focus:ring-2 ${
                    createTramoError
                      ? 'border-red-300 focus:border-red-400 focus:ring-red-100'
                      : 'border-[#1E1E1E]/20 focus:border-blue-500 focus:ring-blue-100'
                  }`}
                />
              </label>
              {createTramoError && createTramoError.trim() !== '' && (
                <p className="mt-2 text-xs text-red-600">{createTramoError}</p>
              )}
              <p className="mt-3 text-xs text-[#A09A91]">
                {t('tramos.create.hint')}
              </p>
            </div>
            <div className="flex items-center justify-end gap-2 border-t border-[#E8E2D8] px-6 py-3">
              <button
                type="button"
                onClick={closeNewTramoModal}
                disabled={creatingTramo}
                className="rounded-lg border border-[#E8E2D8] px-3 py-2 text-sm font-semibold text-[#6A6A6A] hover:bg-[#F7F4EF] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {t('tramos.create.cancel')}
              </button>
              <button
                type="button"
                onClick={handleConfirmNewTramo}
                disabled={creatingTramo}
                className="rounded-lg bg-[#1E1E1E] px-3 py-2 text-sm font-semibold text-white hover:bg-[#333333] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {creatingTramo ? t('form.saving') : t('tramos.create.confirm')}
              </button>
            </div>
          </div>
        </div>
      )}

      {projectConfigOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/20 px-4">
          <div className="w-full max-w-md rounded-xl bg-[#FFFFFF] shadow-2xl">
            <div className="border-b border-[#E8E2D8] px-6 py-4">
              <h2 className="text-base font-semibold text-[#1E1E1E]">{t('project.config.title')}</h2>
            </div>
            <div className="grid grid-cols-2 gap-4 px-6 py-4">
              <label className="text-sm font-medium text-[#6A6A6A]">
                {t('project.config.tAmb')}
                <input type="number" step="1" min={-40} max={80} value={tAmbCDraft ?? configTAmbC}
                  onChange={e => setTAmbCDraft(e.target.value)}
                   className="mt-1 w-full rounded-md border border-[#E8E2D8] px-3 py-2 text-sm" />
              </label>
              <label className="text-sm font-medium text-[#6A6A6A]">
                {t('project.config.margenLavg')}
                <input type="number" step="0.1" min={0} max={100} value={margenLavgDraft ?? configMargenLavg}
                  onChange={e => setMargenLavgDraft(e.target.value)}
                  className="mt-1 w-full rounded-md border border-[#E8E2D8] px-3 py-2 text-sm" />
              </label>
              <label className="text-sm font-medium text-[#6A6A6A]">
                {t('project.config.iOp')}
                <input type="number" placeholder="auto" value={iOpMaDraft ?? configIOpMa ?? ''}
                  onChange={e => setIOpMaDraft(e.target.value)}
                  className="mt-1 w-full rounded-md border border-[#E8E2D8] px-3 py-2 text-sm" />
              </label>
              <label className="text-sm font-medium text-[#6A6A6A]">
                {t('project.config.lmWMin')}
                <input type="number" placeholder="sin mínimo" value={lmWMinDraft ?? configLmWMin ?? ''}
                  onChange={e => setLmWMinDraft(e.target.value)}
                  className="mt-1 w-full rounded-md border border-[#E8E2D8] px-3 py-2 text-sm" />
              </label>
            </div>
            <div className="flex items-center justify-end gap-2 border-t border-[#E8E2D8] px-6 py-3">
              <button type="button" onClick={() => setProjectConfigOpen(false)}
                className="rounded-lg border border-[#E8E2D8] px-3 py-2 text-sm font-semibold text-[#6A6A6A] hover:bg-[#F7F4EF]">
                {t('actions.cancel')}
              </button>
              <button type="button" onClick={handleSaveProjectConfig}
                className="rounded-lg bg-[#1E1E1E] px-3 py-2 text-sm font-semibold text-white hover:bg-[#333333]">
                {t('actions.save')}
              </button>
            </div>
          </div>
        </div>
      )}

      <ImportTramosExcelModal
        open={showImportModal}
        onClose={() => setShowImportModal(false)}
        onImported={loadAll}
        projectId={projectId ?? 0}
        authFetch={authFetch}
      />
    </main>
  );
};

export default ProjectTramosPage;
