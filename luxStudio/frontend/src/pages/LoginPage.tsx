import React, { useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { useI18n } from '../i18n';

export const AuthShell: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <main className="min-h-screen bg-[#FCF9F5] flex items-center justify-center px-4 py-10">
    <section className="w-full max-w-md rounded-2xl border border-[#E8E2D8] bg-[#F7F4EF] p-8 shadow-xl shadow-black/30">
      <div className="mb-7 text-center">
        <div className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-[#1E1E1E]">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="5"/>
            <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>
          </svg>
        </div>
        <h1 className="text-2xl font-bold text-[#1E1E1E] font-brand">LUX Studio</h1>
        <p className="mt-1 text-sm font-semibold text-[#A09A91]">SALVI LIGHTING · Road Lighting Design</p>
      </div>
      {children}
    </section>
  </main>
);

const LoginPage: React.FC = () => {
  const { login } = useAuth();
  const { t } = useI18n();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await login(email, password);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell>
      <form onSubmit={submit} className="space-y-4">
        <label className="block text-sm font-semibold text-[#6A6A6A]">
          {t('auth.email')}
          <input
            type="email"
            value={email}
            onChange={event => setEmail(event.target.value)}
            className="mt-1 w-full rounded-lg border border-[#E8E2D8] bg-[#FFFFFF] px-3 py-2 text-sm outline-none focus:border-[#1E1E1E] focus:ring-2 focus:ring-[#1E1E1E]/10 text-[#1E1E1E]"
            required
          />
        </label>
        <label className="block text-sm font-semibold text-[#6A6A6A]">
          {t('auth.password')}
          <input
            type="password"
            value={password}
            onChange={event => setPassword(event.target.value)}
            className="mt-1 w-full rounded-lg border border-[#E8E2D8] bg-[#FFFFFF] px-3 py-2 text-sm outline-none focus:border-[#1E1E1E] focus:ring-2 focus:ring-[#1E1E1E]/10 text-[#1E1E1E]"
            required
          />
        </label>
        {error && <div className="rounded-lg border border-[#B42318]/25 bg-[#FDECEA] px-3 py-2 text-sm text-[#B42318]">{t(error)}</div>}
        <button
          type="submit"
          disabled={loading}
          className={`w-full rounded-lg px-4 py-2.5 text-sm font-semibold text-white ${loading ? 'bg-[#1E1E1E]/60' : 'bg-[#1E1E1E] hover:bg-[#333333]'}`}
        >
          {loading ? t('auth.loggingIn') : t('auth.login')}
        </button>
      </form>
    </AuthShell>
  );
};

export default LoginPage;
