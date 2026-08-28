import { describe, it, expect, beforeEach, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { I18nProvider } from '../src/i18n';
import UserCreatePanel from '../src/components/admin/UserCreatePanel';

const { authFetch } = vi.hoisted(() => ({ authFetch: vi.fn() }));

vi.mock('../src/auth/AuthContext', () => ({
  useAuth: () => ({ authFetch }),
}));

describe('UserCreatePanel', () => {
  beforeEach(() => {
    authFetch.mockReset();
    authFetch.mockResolvedValue(new Response(JSON.stringify({ email: 'ana@example.com' }), { status: 201 }));
  });

  it('creates a user through the authenticated admin endpoint', async () => {
    render(<I18nProvider><UserCreatePanel /></I18nProvider>);

    fireEvent.change(screen.getByLabelText('Nombre'), { target: { value: 'Ana' } });
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'ana@example.com' } });
    fireEvent.change(screen.getByLabelText('Contraseña inicial'), { target: { value: 'TestPass123!' } });
    fireEvent.click(screen.getByRole('button', { name: 'Crear usuario' }));

    await waitFor(() => expect(authFetch).toHaveBeenCalledWith('/api/admin/users', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ name: 'Ana', email: 'ana@example.com', password: 'TestPass123!' }),
    })));
    expect(await screen.findByRole('status')).toHaveTextContent('Usuario creado');
  });
});
