import React from 'react';
import { useAuth } from '../auth/AuthContext';
import { useI18n } from '../i18n';
import { useGisStore, type AppMode } from '../store/useGisStore';
import type { GisLanguage } from '../i18n/types';

const LANGUAGES: { code: GisLanguage; label: string }[] = [
  { code: 'es', label: 'ES' },
  { code: 'en', label: 'EN' },
  { code: 'pt', label: 'PT' },
  { code: 'fr', label: 'FR' },
  { code: 'ca', label: 'CA' },
];

const Header: React.FC = () => {
  const { user, logout } = useAuth();
  const { language, setLanguage, t } = useI18n();
  const appMode = useGisStore(s => s.appMode);
  const setAppMode = useGisStore(s => s.setAppMode);
  const activeProjectId = useGisStore(s => s.activeProjectId);
  const projects = useGisStore(s => s.projects);
  const setActiveProject = useGisStore(s => s.setActiveProject);
  const detailZoneId = useGisStore(s => s.detailZoneId);
  const setDetailZone = useGisStore(s => s.setDetailZone);

  return (
    <header className="h-14 bg-white/90 backdrop-blur-sm border-b border-salvi-line flex items-center justify-between px-4 shrink-0 z-10 shadow-sm">
      {/* Left — brand + project selector */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <span className="font-brand font-light text-xl text-salvi-black tracking-[4px]">SALVI</span>
          <span className="bg-green-100 text-state-success text-xs font-bold px-2 py-0.5 rounded">GIS</span>
        </div>

        <div className="h-5 w-px bg-salvi-line" />

        <select
          value={activeProjectId || ''}
          onChange={e => setActiveProject(e.target.value || null)}
          className="text-sm border border-salvi-line rounded-md px-2 py-1 bg-white text-salvi-black"
        >
          <option value="">— {t('nav.projects')} —</option>
          {projects.map(p => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>

        <div className="h-5 w-px bg-salvi-line" />

        {/* Mode switch */}
        <div className="flex rounded-md border border-salvi-line overflow-hidden text-sm">
          <button
            onClick={() => setAppMode('planning')}
            className={`px-3 py-1.5 font-medium transition-colors ${appMode === 'planning' ? 'bg-salvi-black text-white' : 'bg-white text-salvi-grey hover:bg-salvi-surface'}`}
          >
            {t('nav.planning')}
          </button>
          <button
            onClick={() => { setAppMode('detail'); if (!detailZoneId && activeProjectId) setDetailZone(activeProjectId); }}
            className={`px-3 py-1.5 font-medium transition-colors ${appMode === 'detail' ? 'bg-salvi-black text-white' : 'bg-white text-salvi-grey hover:bg-salvi-surface'}`}
          >
            {t('nav.detail')}
          </button>
        </div>
      </div>

      {/* Right — language + user */}
      <div className="flex items-center gap-3">
        <select
          value={language}
          onChange={e => setLanguage(e.target.value as GisLanguage)}
          className="text-xs border border-salvi-line rounded px-2 py-1 bg-white text-salvi-grey font-medium"
        >
          {LANGUAGES.map(l => (
            <option key={l.code} value={l.code}>{l.label}</option>
          ))}
        </select>

        <div className="h-5 w-px bg-salvi-line" />

        <span className="text-xs text-salvi-grey font-medium">{user?.name || ''}</span>
        <button
          onClick={logout}
          className="text-xs font-medium text-salvi-grey hover:text-state-danger transition-colors"
        >
          {t('nav.logout')}
        </button>
      </div>
    </header>
  );
};

export default Header;
