import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { I18nProvider } from '../src/i18n';
import ConfigurationTabsPanel from '../src/components/panels/ConfigurationTabsPanel';
import { useConfigStore } from '../src/store/useConfigStore';

// Mock global fetch to prevent LuminairePanel from throwing on mount
vi.stubGlobal('fetch', vi.fn(() =>
  Promise.resolve(new Response(JSON.stringify({}), { status: 200 }))
));

const renderWithProviders = (ui: React.ReactNode) => {
  useConfigStore.setState(useConfigStore.getInitialState());
  return render(<I18nProvider>{ui}</I18nProvider>);
};

describe('ConfigurationTabsPanel', () => {
  it('renders tabs and shows road tab as active by default', () => {
    renderWithProviders(<ConfigurationTabsPanel />);
    const tabs = screen.getAllByRole('tab');
    expect(tabs).toHaveLength(2);
    expect(tabs[0].getAttribute('aria-selected')).toBe('true');
    expect(tabs[1].getAttribute('aria-selected')).toBe('false');
  });

  it('switches to luminaire tab on click', () => {
    renderWithProviders(<ConfigurationTabsPanel />);
    const tabs = screen.getAllByRole('tab');
    fireEvent.click(tabs[1]);
    expect(tabs[1].getAttribute('aria-selected')).toBe('true');
    expect(tabs[0].getAttribute('aria-selected')).toBe('false');
  });
});
