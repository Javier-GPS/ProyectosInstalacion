import React from 'react';
import { Link, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { useI18n, type Language } from '../i18n';

const MainLayout: React.FC = () => {
  const location = useLocation();
  const isAdmin = location.pathname === '/admin';
  const { language, setLanguage, t } = useI18n();
  const { user, logout } = useAuth();

  return (
    <div className="min-h-screen flex flex-col bg-[#FCF9F5]">
      <header className="border-b border-[#E8E2D8] bg-[#F7F4EF]/90 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 bg-[#FFFFFF] rounded-lg flex items-center justify-center">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                  <circle cx="12" cy="12" r="10" fill="#1E1E1E"/>
                  <circle cx="12" cy="12" r="6" fill="#F7F4EF"/>
                </svg>
              </div>
              <div>
                <h1 className="text-xl font-bold text-[#1E1E1E]">LUX Studio</h1>
                <p className="text-xs text-[#A09A91] -mt-0.5">{t('app.subtitle')}</p>
              </div>
            </div>
            <nav className="flex items-center gap-4">
              <span className="hidden md:inline text-xs font-semibold text-[#1E1E1E]">SALVI LIGHTING</span>
              <div className="hidden md:block h-6 w-px bg-[#E8E2D8]"/>
              {user?.role === 'ADMIN' && isAdmin && (
                <Link to="/projects" className="text-sm text-[#1E1E1E] hover:text-[#333333] font-medium">
                  {t('nav.studio')}
                </Link>
              )}
              {user?.role === 'ADMIN' && !isAdmin && (
                <Link to="/admin" className="text-sm text-[#A09A91] hover:text-[#1E1E1E]">
                  {t('nav.admin')}
                </Link>
              )}
              <div className="h-6 w-px bg-[#E8E2D8]"/>
              <span className="text-sm text-[#A09A91]">CIE 140 / EN 13201</span>
              <div className="h-6 w-px bg-[#E8E2D8]"/>
              <label className="sr-only" htmlFor="language-select">{t('language.label')}</label>
              <select
                id="language-select"
                value={language}
                onChange={event => setLanguage(event.target.value as Language)}
                className="rounded-md border border-[#E8E2D8] bg-[#FFFFFF] px-2 py-1 text-xs font-medium text-[#6A6A6A]"
              >
                <option value="es">{t('language.es')}</option>
                <option value="en">{t('language.en')}</option>
                <option value="fr">{t('language.fr')}</option>
                <option value="pt">{t('language.pt')}</option>
                <option value="de">{t('language.de')}</option>
                <option value="it">{t('language.it')}</option>
              </select>
              <div className="h-6 w-px bg-[#E8E2D8]"/>
              <span className="hidden lg:inline text-xs text-[#6A6A6A]">
                {user?.name}{user?.role === 'ADMIN' ? ' · ADMIN' : ''}
              </span>
              <button
                type="button"
                onClick={logout}
                className="text-xs font-medium text-[#A09A91] hover:text-[#B42318]"
              >
                {t('actions.logout')}
              </button>
              <div className="h-6 w-px bg-[#E8E2D8]"/>
              <span className="text-xs text-[#6a6a6a]">v0.1.0</span>
            </nav>
          </div>
        </div>
      </header>
      <main className="flex-1">
        <Outlet />
      </main>
    </div>
  );
};

export default MainLayout;
