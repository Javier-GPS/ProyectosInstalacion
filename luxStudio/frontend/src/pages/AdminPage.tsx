import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import LuminaireTable from '../components/admin/LuminaireTable';
import LuminaireForm from '../components/admin/LuminaireForm';
import DimensionTable from '../components/admin/DimensionTable';
import CatalogTable from '../components/admin/CatalogTable';
import PcbTable from '../components/admin/PcbTable';
import LuminaireLedTable from '../components/admin/LuminaireLedTable';
import AdminUsersPage from './AdminUsersPage';
import { useI18n } from '../i18n';
import type { LDTInfo } from '../types';

type Section = 'users' | 'catalog';
type CatalogTab = 'luminaires' | 'gamas' | 'difusores' | 'lentes' | 'led-types' | 'leds' | 'pcbs' | 'drivers' | 'luminaire-leds';

const sections: { key: Section; labelKey: string }[] = [
  { key: 'users', labelKey: 'admin.section.users' },
  { key: 'catalog', labelKey: 'admin.section.catalog' },
];

const catalogTabs: { key: CatalogTab; labelKey: string }[] = [
  { key: 'luminaires', labelKey: 'admin.catalog.luminaires' },
  { key: 'gamas', labelKey: 'admin.catalog.gamas' },
  { key: 'difusores', labelKey: 'admin.catalog.difusores' },
  { key: 'lentes', labelKey: 'admin.catalog.lentes' },
  { key: 'led-types', labelKey: 'admin.catalog.ledTypes' },
  { key: 'leds', labelKey: 'admin.catalog.leds' },
  { key: 'pcbs', labelKey: 'admin.catalog.pcbs' },
  { key: 'drivers', labelKey: 'admin.catalog.drivers' },
  { key: 'luminaire-leds', labelKey: 'admin.catalog.luminaireLeds' },
];

const dimensionEndpoints: Record<string, { endpoint: string; labelKey: string }> = {
  gamas: { endpoint: 'gamas', labelKey: 'admin.catalog.gamas' },
  difusores: { endpoint: 'difusores', labelKey: 'admin.catalog.difusores' },
  lentes: { endpoint: 'lentes', labelKey: 'admin.catalog.lentes' },
  'led-types': { endpoint: 'led-types', labelKey: 'admin.catalog.ledTypes' },
};

const AdminPage: React.FC = () => {
  const { t } = useI18n();
  const [section, setSection] = useState<Section>('users');
  const [catalogTab, setCatalogTab] = useState<CatalogTab>('luminaires');
  const [editLum, setEditLum] = useState<LDTInfo | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  const handleEdit = (lum: LDTInfo) => {
    setEditLum(lum);
    setShowForm(true);
  };

  const handleNew = () => {
    setEditLum(null);
    setShowForm(true);
  };

  const handleSaved = () => {
    setShowForm(false);
    setEditLum(null);
    setRefreshKey(k => k + 1);
  };

  const handleCancel = () => {
    setShowForm(false);
    setEditLum(null);
  };

  const renderCatalogContent = () => {
    switch (catalogTab) {
      case 'luminaires':
        return showForm ? (
          <LuminaireForm editLum={editLum} onSaved={handleSaved} onCancel={handleCancel} />
        ) : (
          <div className="bg-[#FFFFFF] rounded-xl border border-[#E8E2D8] shadow-sm overflow-hidden">
            <LuminaireTable onEdit={handleEdit} refreshKey={refreshKey} />
          </div>
        );
      case 'leds':
        return (
          <CatalogTable
            endpoint="leds"
            label={t('admin.catalog.leds')}
            refreshKey={refreshKey}
            columns={[
              { key: 'id', label: 'ID' },
              { key: 'led_ref', label: 'Ref' },
              { key: 'led_desc_corta', label: 'Descripción' },
              { key: 'led_tipo', label: 'Tipo' },
              { key: 'pmax_lum', label: 'Pmax Lum' },
              { key: 'i_max_led', label: 'I Max' },
              {
                key: 'pmax_ajustada',
                label: 'Pmax Ajustada',
                render: (v: any) => v != null ? <strong className="text-[#333333]">{v}</strong> : '—',
              },
            ]}
          />
        );
      case 'pcbs':
        return <PcbTable refreshKey={refreshKey} />;
      case 'drivers':
        return (
          <CatalogTable
            endpoint="drivers"
            label={t('admin.catalog.drivers')}
            refreshKey={refreshKey}
            columns={[
              { key: 'id', label: 'ID' },
              { key: 'dr_ref', label: 'Ref' },
              { key: 'dr_pot_max_driver', label: 'Pot Max' },
            ]}
          />
        );
      case 'luminaire-leds':
        return <LuminaireLedTable refreshKey={refreshKey} />;
      default:
        return (
          <DimensionTable
            endpoint={dimensionEndpoints[catalogTab].endpoint}
            label={t(dimensionEndpoints[catalogTab].labelKey)}
            refreshKey={refreshKey}
            onRefresh={() => setRefreshKey(k => k + 1)}
          />
        );
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-semibold text-[#1E1E1E]">{t('admin.title')}</h2>
          <p className="text-[#A09A91] text-sm mt-1">{t('admin.subtitle')}</p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            to="/projects"
            className="px-3 py-1.5 text-xs rounded-md border border-[#E8E2D8] text-[#6A6A6A] hover:bg-[#F7F4EF]"
          >
            {t('actions.backToStudio')}
          </Link>
          {section === 'catalog' && catalogTab === 'luminaires' && !showForm && (
            <button
              onClick={handleNew}
              className="px-3 py-1.5 text-xs font-medium rounded-md bg-[#1E1E1E] text-white hover:bg-[#333333]"
            >
              {t('actions.newLuminaire')}
            </button>
          )}
        </div>
      </div>

      {/* Level 1: sections */}
      <div className="flex gap-1 mb-6 border-b border-[#E8E2D8]">
        {sections.map(sec => (
          <button
            key={sec.key}
            onClick={() => { setSection(sec.key); setShowForm(false); setEditLum(null); }}
            className={`px-5 py-2.5 text-sm font-semibold border-b-2 transition-colors ${
              section === sec.key
                ? 'border-[#1E1E1E] text-[#1E1E1E]'
                : 'border-transparent text-[#A09A91] hover:text-[#6A6A6A] hover:border-[#D4CEC6]'
            }`}
          >
            {t(sec.labelKey)}
          </button>
        ))}
      </div>

      {/* Level 2: catalog sub-tabs */}
      {section === 'catalog' && (
        <div className="flex gap-1 mb-6 border-b border-[#E8E2D8] ml-0">
          {catalogTabs.map(tb => (
            <button
              key={tb.key}
              onClick={() => { setCatalogTab(tb.key); setShowForm(false); setEditLum(null); }}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                catalogTab === tb.key
                  ? 'border-[#1E1E1E] text-[#1E1E1E]'
                  : 'border-transparent text-[#A09A91] hover:text-[#6A6A6A] hover:border-[#D4CEC6]'
              }`}
            >
              {t(tb.labelKey)}
            </button>
          ))}
        </div>
      )}

      {/* Content */}
      {section === 'users' ? (
        <div className="bg-[#FFFFFF] rounded-xl border border-[#E8E2D8] shadow-sm overflow-hidden">
          <AdminUsersPage />
        </div>
      ) : (
        renderCatalogContent()
      )}
    </div>
  );
};

export default AdminPage;
