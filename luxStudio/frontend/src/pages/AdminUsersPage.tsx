import React, { useEffect, useState, useMemo } from 'react';
import { useAuth } from '../auth/AuthContext';
import { useColumnFilters, type ColumnFilterDef } from '../hooks/useColumnFilters';
import { useI18n } from '../i18n';

interface AdminUserRecord {
  id: number;
  company_name: string;
  email: string;
  name: string;
  role: 'ADMIN' | 'USER';
  is_active: boolean;
  must_reset_password: boolean;
}

const AdminUsersPage: React.FC = () => {
  const { t } = useI18n();
  const { authFetch, user } = useAuth();
  const [users, setUsers] = useState<AdminUserRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [form, setForm] = useState({
    name: '',
    email: '',
    role: 'USER',
    password: '',
    is_active: true,
    must_reset_password: true,
  });
  const [editingUserId, setEditingUserId] = useState<number | null>(null);
  const [resetPassword, setResetPassword] = useState<Record<number, string>>({});

  const loadUsers = () => {
    setLoading(true);
    authFetch('/api/admin/users')
      .then(res => res.json())
      .then(setUsers)
      .catch(error => setMessage(error.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (user?.role === 'ADMIN') loadUsers();
  }, [user?.role]);

  const filterDefs: ColumnFilterDef<AdminUserRecord>[] = useMemo(() => [
    { key: 'id', getValue: u => String(u.id) },
    { key: 'name', getValue: u => u.name },
    { key: 'email', getValue: u => u.email },
    { key: 'role', getValue: u => u.role },
    { key: 'is_active', getValue: u => u.is_active ? t('yes') : t('no') },
    { key: 'must_reset_password', getValue: u => u.must_reset_password ? t('yes') : t('no') },
  ], []);

  const { filters, setFilter, filteredData: filteredUsers } = useColumnFilters(users, filterDefs);

  const createUser = async (event: React.FormEvent) => {
    event.preventDefault();
    setMessage(null);
    if (editingUserId) {
      const response = await authFetch(`/api/admin/users/${editingUserId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: form.name,
          email: form.email,
          role: form.role,
          is_active: form.is_active,
          must_reset_password: form.must_reset_password,
        }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => null);
        setMessage(data?.detail || t('admin.users.updateFailed'));
        return;
      }
      setMessage(t('admin.users.updated'));
      setEditingUserId(null);
      setForm({ name: '', email: '', role: 'USER', password: '', is_active: true, must_reset_password: true });
      loadUsers();
      return;
    }
    const response = await authFetch('/api/admin/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => null);
      setMessage(data?.detail || t('admin.users.createFailed'));
      return;
    }
    setMessage(t('admin.users.created', { email: form.email, password: form.password }));
    setForm({ name: '', email: '', role: 'USER', password: '', is_active: true, must_reset_password: true });
    loadUsers();
  };

  const startEditUser = (item: AdminUserRecord) => {
    setEditingUserId(item.id);
    setMessage(null);
    setForm({
      name: item.name,
      email: item.email,
      role: item.role,
      password: '',
      is_active: item.is_active,
      must_reset_password: item.must_reset_password,
    });
  };

  const cancelEditUser = () => {
    setEditingUserId(null);
    setForm({ name: '', email: '', role: 'USER', password: '', is_active: true, must_reset_password: true });
  };

  const patchUser = async (id: number, body: Partial<AdminUserRecord>) => {
    await authFetch(`/api/admin/users/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    loadUsers();
  };

  const resetUserPassword = async (id: number) => {
    const password = resetPassword[id];
    if (!password) return;
    await authFetch(`/api/admin/users/${id}/reset-password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password, must_reset_password: true }),
    });
    setMessage(t('admin.users.passwordResetMsg', { password }));
    setResetPassword(current => ({ ...current, [id]: '' }));
    loadUsers();
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      <div>
        <h2 className="text-2xl font-semibold text-[#1E1E1E]">{t('admin.users.title')}</h2>
        <p className="text-[#A09A91] text-sm mt-1">{t('admin.users.subtitle')}</p>
      </div>

      <form onSubmit={createUser} className="bg-[#FFFFFF] rounded-xl border border-[#E8E2D8] shadow-sm p-4 grid grid-cols-1 md:grid-cols-6 gap-3">
        <input className="rounded-md border border-[#E8E2D8] px-3 py-2 text-sm" placeholder={t('admin.users.namePlaceholder')} value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} required />
        <input className="rounded-md border border-[#E8E2D8] px-3 py-2 text-sm" placeholder={t('admin.users.emailPlaceholder')} type="email" value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} required />
        <select className="rounded-md border border-[#E8E2D8] px-3 py-2 text-sm" value={form.role} onChange={e => setForm({ ...form, role: e.target.value })}>
          <option value="USER">USER</option>
          <option value="ADMIN">ADMIN</option>
        </select>
        <input className="rounded-md border border-[#E8E2D8] px-3 py-2 text-sm" placeholder={t('admin.users.passwordPlaceholder')} type="text" value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} required={!editingUserId} minLength={8} disabled={Boolean(editingUserId)} />
        <label className="flex items-center gap-2 text-sm text-[#6A6A6A]">
          <input type="checkbox" checked={form.must_reset_password} onChange={e => setForm({ ...form, must_reset_password: e.target.checked })} />
          {t('admin.users.resetAtLogin')}
        </label>
        <div className="flex gap-2">
          <button className="rounded-md bg-[#1E1E1E] px-4 py-2 text-sm font-semibold text-white hover:bg-[#333333]">
            {editingUserId ? t('admin.users.save') : t('admin.users.create')}
          </button>
          {editingUserId && (
            <button type="button" onClick={cancelEditUser} className="rounded-md border border-[#E8E2D8] px-4 py-2 text-sm font-semibold text-[#6A6A6A] hover:bg-[#F7F4EF]">
              {t('admin.users.cancel')}
            </button>
          )}
        </div>
      </form>

      {message && <div className="rounded-lg border border-blue-200 bg-[#1E1E1E]/6 px-3 py-2 text-sm text-blue-800">{message}</div>}

      <div className="bg-[#FFFFFF] rounded-xl border border-[#E8E2D8] shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#E8E2D8] text-left text-[#A09A91] text-xs uppercase tracking-wider">
                <th className="px-3 py-2">ID</th>
                <th className="px-3 py-2">{t('admin.users.namePlaceholder')}</th>
                <th className="px-3 py-2">{t('admin.users.emailPlaceholder')}</th>
                <th className="px-3 py-2">{t('admin.users.role')}</th>
                <th className="px-3 py-2">{t('admin.users.active')}</th>
                <th className="px-3 py-2">{t('admin.users.resetPassword')}</th>
                <th className="px-3 py-2">{t('admin.users.passwordPlaceholder')}</th>
                <th className="px-3 py-2 text-right">{t('admin.actions')}</th>
              </tr>
              <tr className="border-b border-[#E8E2D8]">
                <th className="px-1 py-1"><input value={filters.id || ''} onChange={e => setFilter('id', e.target.value)} placeholder="ID" className="w-full px-1.5 py-1 text-[11px] border border-[#E8E2D8] rounded bg-[#FFFFFF] focus:outline-none focus:border-blue-400" /></th>
                <th className="px-1 py-1"><input value={filters.name || ''} onChange={e => setFilter('name', e.target.value)} placeholder={t('admin.users.namePlaceholder')} className="w-full px-1.5 py-1 text-[11px] border border-[#E8E2D8] rounded bg-[#FFFFFF] focus:outline-none focus:border-blue-400" /></th>
                <th className="px-1 py-1"><input value={filters.email || ''} onChange={e => setFilter('email', e.target.value)} placeholder={t('admin.users.emailPlaceholder')} className="w-full px-1.5 py-1 text-[11px] border border-[#E8E2D8] rounded bg-[#FFFFFF] focus:outline-none focus:border-blue-400" /></th>
                <th className="px-1 py-1"><input value={filters.role || ''} onChange={e => setFilter('role', e.target.value)} placeholder={t('admin.users.role')} className="w-full px-1.5 py-1 text-[11px] border border-[#E8E2D8] rounded bg-[#FFFFFF] focus:outline-none focus:border-blue-400" /></th>
                <th className="px-1 py-1"><input value={filters.is_active || ''} onChange={e => setFilter('is_active', e.target.value)} placeholder={t('admin.users.active')} className="w-full px-1.5 py-1 text-[11px] border border-[#E8E2D8] rounded bg-[#FFFFFF] focus:outline-none focus:border-blue-400" /></th>
                <th className="px-1 py-1"><input value={filters.must_reset_password || ''} onChange={e => setFilter('must_reset_password', e.target.value)} placeholder={t('admin.users.resetPassword')} className="w-full px-1.5 py-1 text-[11px] border border-[#E8E2D8] rounded bg-[#FFFFFF] focus:outline-none focus:border-blue-400" /></th>
                <th className="px-1 py-1" />
                <th className="px-1 py-1" />
              </tr>
            </thead>
            <tbody>
              {filteredUsers.map(item => (
                <tr key={item.id} className="border-b border-[#E8E2D8] hover:bg-[#F7F4EF]">
                  <td className="px-3 py-2 text-[#6a6a6a]">{item.id}</td>
                  <td className="px-3 py-2 font-medium">{item.name}</td>
                  <td className="px-3 py-2">{item.email}</td>
                  <td className="px-3 py-2">
                    <select value={item.role} onChange={e => patchUser(item.id, { role: e.target.value as 'ADMIN' | 'USER' })} className="rounded border border-[#E8E2D8] px-2 py-1 text-xs">
                      <option value="USER">USER</option>
                      <option value="ADMIN">ADMIN</option>
                    </select>
                  </td>
                  <td className="px-3 py-2">{item.is_active ? t('yes') : t('no')}</td>
                  <td className="px-3 py-2">{item.must_reset_password ? t('yes') : t('no')}</td>
                  <td className="px-3 py-2">
                    <input className="w-36 rounded border border-[#E8E2D8] px-2 py-1 text-xs" value={resetPassword[item.id] || ''} onChange={e => setResetPassword({ ...resetPassword, [item.id]: e.target.value })} placeholder={t('admin.users.newPasswordPlaceholder')} />
                  </td>
                  <td className="px-3 py-2 text-right space-x-1">
                    <button onClick={() => startEditUser(item)} className="px-2 py-1 text-xs rounded border border-[#E8E2D8] text-[#6A6A6A] hover:bg-slate-100">{t('admin.users.edit')}</button>
                    <button onClick={() => resetUserPassword(item.id)} className="px-2 py-1 text-xs rounded border border-[#E8E2D8] text-[#6A6A6A] hover:bg-slate-100">{t('admin.users.resetPassword')}</button>
                    <button onClick={() => patchUser(item.id, { is_active: !item.is_active })} className={`px-2 py-1 text-xs rounded border ${item.is_active ? 'border-red-200 text-red-600 hover:bg-red-50' : 'border-emerald-200 text-emerald-600 hover:bg-emerald-50'}`}>
                      {item.is_active ? t('admin.users.deactivate') : t('admin.users.activate')}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {loading && <div className="p-8 text-center text-[#6a6a6a]">{t('admin.users.loading')}</div>}
        </div>
      </div>
    </div>
  );
};

export default AdminUsersPage;
