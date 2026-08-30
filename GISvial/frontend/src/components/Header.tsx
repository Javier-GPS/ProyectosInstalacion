import React from 'react';
import { useAuth } from '../auth/AuthContext';
import { useI18n } from '../i18n';
import { useGisStore } from '../store/useGisStore';
import type { GisLanguage } from '../i18n/types';

const LANGUAGES: { code: GisLanguage; label: string }[] = [
  { code: 'es', label: 'ES' },
  { code: 'en', label: 'EN' },
  { code: 'pt', label: 'PT' },
  { code: 'fr', label: 'FR' },
  { code: 'ca', label: 'CA' },
];

interface HeaderProps {
  children?: React.ReactNode;
}

const Header: React.FC<HeaderProps> = ({ children }) => {
  const { user, logout } = useAuth();
  const { language, setLanguage, t } = useI18n();
  // Dentro del portal la sesión la gestiona la cabecera del portal: sin usuario ni logout propios.
  const embedded = window.self !== window.top;
  const view = useGisStore(s => s.view);
  const activeProject = useGisStore(s => s.projects.find(p => String(p.id) === String(s.activeProjectId)));
  const sidebarOpen = useGisStore(s => s.sidebarOpen);
  const setSidebarOpen = useGisStore(s => s.setSidebarOpen);
  const confirmPlanningLeave = useGisStore(s => s.confirmPlanningLeave);

  const toggleSidebar = () => {
    if (sidebarOpen && !confirmPlanningLeave()) return;
    setSidebarOpen(!sidebarOpen);
  };
  const handleLogout = () => {
    if (confirmPlanningLeave()) logout();
  };

  return (
    <header className="h-14 bg-white/90 backdrop-blur-sm border-b border-salvi-line flex items-center justify-between px-4 shrink-0 z-10 shadow-sm">
      {/* Left — brand + project name + wizard nav (editor only) */}
      <div className="flex items-center gap-4 min-w-0">
        <span className="flex items-center gap-2 shrink-0">
          <span className="font-brand font-light text-xl text-salvi-black tracking-[4px]">SALVI</span>
          <span className="bg-green-100 text-state-success text-xs font-bold px-2 py-0.5 rounded">GIS</span>
        </span>

        {view === 'editor' && (
          <>
            <div className="h-5 w-px bg-salvi-line shrink-0" />
            <span className="text-sm font-medium text-salvi-grey truncate max-w-[180px]" title={activeProject?.name || ''}>
              {activeProject?.name || ''}
            </span>

            <div className="h-5 w-px bg-salvi-line shrink-0" />
            {children}
          </>
        )}
      </div>

      {/* Right — sidebar toggle (editor only) + language + user */}
      <div className="flex items-center gap-3 shrink-0">
        {view === 'editor' && (
          <>
            <button
              onClick={toggleSidebar}
              className="text-xs border border-salvi-line rounded-md px-2 py-1 text-salvi-grey hover:bg-salvi-surface transition-colors"
              title={sidebarOpen ? 'Cerrar panel' : 'Abrir panel'}
              aria-label={sidebarOpen ? 'Cerrar panel' : 'Abrir panel'}
            >
              {sidebarOpen ? '◀' : '▶'}
            </button>

            <div className="h-5 w-px bg-salvi-line" />
          </>
        )}

        <select
          value={language}
          onChange={e => setLanguage(e.target.value as GisLanguage)}
          className="text-xs border border-salvi-line rounded px-2 py-1 bg-white text-salvi-grey font-medium"
        >
          {LANGUAGES.map(l => (
            <option key={l.code} value={l.code}>{l.label}</option>
          ))}
        </select>

        {!embedded && (
          <>
            <div className="h-5 w-px bg-salvi-line" />

            <span className="text-xs text-salvi-grey font-medium truncate max-w-[120px]">{user?.name || ''}</span>
            <button
              onClick={handleLogout}
              className="text-xs font-medium text-salvi-grey hover:text-state-danger transition-colors"
            >
              {t('nav.logout')}
            </button>
          </>
        )}
      </div>
    </header>
  );
};

export default Header;
