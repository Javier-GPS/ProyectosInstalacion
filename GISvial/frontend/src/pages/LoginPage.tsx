import React, { useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { useI18n } from '../i18n';

const LoginPage: React.FC = () => {
  const { login } = useAuth();
  const { t } = useI18n();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(email, password);
    } catch (err: any) {
      setError(err.message || t('login.error'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-salvi-cream to-salvi-surface">
      <div className="w-full max-w-sm">
        <div className="bg-white/90 backdrop-blur-sm rounded-xl shadow-panel border border-salvi-line p-8">
          <div className="text-center mb-8">
            <div className="font-brand font-light text-3xl text-salvi-black tracking-[6px] mb-1">SALVI</div>
            <div className="text-xs text-salvi-muted tracking-widest uppercase">GIS</div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-salvi-grey mb-1">{t('login.email')}</label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                className="w-full border border-salvi-line rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-salvi-black/10"
                required
                autoFocus
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-salvi-grey mb-1">{t('login.password')}</label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                className="w-full border border-salvi-line rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-salvi-black/10"
                required
              />
            </div>

            {error && (
              <div className="bg-red-50 border border-red-200 text-state-danger text-xs rounded-lg px-3 py-2">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-salvi-black text-white rounded-lg py-2.5 text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-opacity"
            >
              {loading ? t('actions.loading') : t('login.submit')}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
};

export default LoginPage;
