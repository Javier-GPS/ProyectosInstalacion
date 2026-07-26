import React, { useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { useI18n } from '../i18n';
import { AuthShell } from './LoginPage';

const ChangePasswordPage: React.FC = () => {
  const { changePassword, logout, user } = useAuth();
  const { t } = useI18n();
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [repeatPassword, setRepeatPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (newPassword !== repeatPassword) {
      setError('auth.passwordMismatch');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await changePassword(currentPassword, newPassword);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell>
      <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
        {t('auth.changePasswordRequired', { name: user?.name ?? '' })}
      </div>
      <form onSubmit={submit} className="space-y-4">
        <label className="block text-sm font-semibold text-[#6A6A6A]">
          {t('auth.currentPassword')}
          <input type="password" value={currentPassword} onChange={event => setCurrentPassword(event.target.value)} className="mt-1 w-full rounded-lg border border-[#E8E2D8] px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100" required />
        </label>
        <label className="block text-sm font-semibold text-[#6A6A6A]">
          {t('auth.newPassword')}
          <input type="password" value={newPassword} onChange={event => setNewPassword(event.target.value)} className="mt-1 w-full rounded-lg border border-[#E8E2D8] px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100" required minLength={8} />
        </label>
        <label className="block text-sm font-semibold text-[#6A6A6A]">
          {t('auth.repeatNewPassword')}
          <input type="password" value={repeatPassword} onChange={event => setRepeatPassword(event.target.value)} className="mt-1 w-full rounded-lg border border-[#E8E2D8] px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100" required minLength={8} />
        </label>
        {error && <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
        <button type="submit" disabled={loading} className={`w-full rounded-lg px-4 py-2.5 text-sm font-semibold text-white ${loading ? 'bg-blue-400' : 'bg-[#1E1E1E] hover:bg-[#333333]'}`}>
          {loading ? t('actions.saving') : t('auth.savePassword')}
        </button>
        <button type="button" onClick={logout} className="w-full rounded-lg border border-[#E8E2D8] px-4 py-2 text-sm font-semibold text-[#6A6A6A] hover:bg-[#F7F4EF]">
          Cerrar sesion
        </button>
      </form>
    </AuthShell>
  );
};

export default ChangePasswordPage;
