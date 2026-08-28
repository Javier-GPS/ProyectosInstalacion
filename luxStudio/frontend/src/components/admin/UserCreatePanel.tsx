import React, { FormEvent, useState } from 'react';
import { useAuth } from '../../auth/AuthContext';
import { useI18n } from '../../i18n';

const UserCreatePanel: React.FC = () => {
  const { authFetch } = useAuth();
  const { t } = useI18n();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setNotice(null);
    setLoading(true);
    try {
      const response = await authFetch('/api/admin/users', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email, password }),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(data?.detail || t('admin.users.createFailed'));
      }
      setNotice(t('admin.users.created', { email: data?.email || email, password }));
      setName('');
      setEmail('');
      setPassword('');
    } catch (err) {
      setError(err instanceof Error ? err.message : t('admin.users.createFailed'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="rounded-xl border border-[#E8E2D8] bg-[#FFFFFF] p-4 shadow-sm">
      <div className="mb-4">
        <h3 className="font-semibold text-[#1E1E1E]">{t('admin.users.title')}</h3>
        <p className="mt-1 text-sm text-[#A09A91]">{t('admin.users.subtitle')}</p>
      </div>
      <form onSubmit={submit} className="grid gap-3 md:grid-cols-[1fr_1fr_1fr_auto] md:items-end">
        <label className="text-xs font-semibold text-[#6A6A6A]">
          {t('admin.users.namePlaceholder')}
          <input
            value={name}
            onChange={event => setName(event.target.value)}
            required
            maxLength={255}
            autoComplete="name"
            className="mt-1 w-full rounded-md border border-[#D4CEC6] px-3 py-2 text-sm font-normal focus:outline-none focus:ring-2 focus:ring-[#1E1E1E]/15"
          />
        </label>
        <label className="text-xs font-semibold text-[#6A6A6A]">
          {t('admin.users.emailPlaceholder')}
          <input
            type="email"
            value={email}
            onChange={event => setEmail(event.target.value)}
            required
            maxLength={255}
            autoComplete="email"
            className="mt-1 w-full rounded-md border border-[#D4CEC6] px-3 py-2 text-sm font-normal focus:outline-none focus:ring-2 focus:ring-[#1E1E1E]/15"
          />
        </label>
        <label className="text-xs font-semibold text-[#6A6A6A]">
          {t('admin.users.passwordPlaceholder')}
          <input
            type="password"
            value={password}
            onChange={event => setPassword(event.target.value)}
            required
            minLength={8}
            maxLength={128}
            autoComplete="new-password"
            className="mt-1 w-full rounded-md border border-[#D4CEC6] px-3 py-2 text-sm font-normal focus:outline-none focus:ring-2 focus:ring-[#1E1E1E]/15"
          />
        </label>
        <button
          type="submit"
          disabled={loading}
          className="rounded-md bg-[#1E1E1E] px-4 py-2 text-sm font-medium text-white hover:bg-[#333333] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? t('actions.loading') : t('admin.users.create')}
        </button>
      </form>
      {notice && <p role="status" className="mt-3 rounded-md bg-[#EAF6EF] px-3 py-2 text-sm text-[#1F7A4D]">{notice}</p>}
      {error && <p role="alert" className="mt-3 rounded-md bg-[#FDECEA] px-3 py-2 text-sm text-[#B42318]">{error}</p>}
    </section>
  );
};

export default UserCreatePanel;
