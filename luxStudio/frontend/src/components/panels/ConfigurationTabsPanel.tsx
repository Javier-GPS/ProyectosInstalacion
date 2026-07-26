import React, { useState } from 'react';
import { LampCeiling, Map } from 'lucide-react';
import { useI18n } from '../../i18n';
import GeometryPanel from './GeometryPanel';
import LuminairePanel from './LuminairePanel';

type TabKey = 'road' | 'luminaire';

type ConfigTab = {
  key: TabKey;
  label: string;
  shortLabel: string;
  icon: React.ReactNode;
  content: React.ReactNode;
};

const ConfigurationTabsPanel: React.FC = () => {
  const { t } = useI18n();
  const [activeTab, setActiveTab] = useState<TabKey>('road');

  const tabs: ConfigTab[] = [
    {
      key: 'road',
      label: t('geometry.title'),
      shortLabel: 'Via',
      icon: <Map className="h-4 w-4" aria-hidden="true" />,
      content: <GeometryPanel embedded />,
    },
    {
      key: 'luminaire',
      label: t('luminaire.title'),
      shortLabel: 'Luz',
      icon: <LampCeiling className="h-4 w-4" aria-hidden="true" />,
      content: <LuminairePanel embedded />,
    },
  ];

  return (
    <section className="studio-panel overflow-hidden rounded-xl">
      <div role="tablist" aria-label={t('tramoEditor.configurationTabs')} className="grid grid-cols-2 gap-1 border-b border-[#E8E2D8] bg-[#FFFFFF] p-1.5">
        {tabs.map(tab => {
          const isActive = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              type="button"
              role="tab"
              aria-selected={isActive}
              onClick={() => setActiveTab(tab.key)}
              title={tab.label}
              className={`flex min-w-0 items-center justify-center gap-1.5 rounded-lg px-2 py-2 text-xs font-semibold transition-all ${
                isActive
                  ? 'bg-[#1E1E1E] text-white shadow-sm'
                  : 'text-[#A09A91] hover:bg-[#FFFFFF] hover:text-[#1E1E1E]'
              }`}
            >
              {tab.icon}
              <span className="hidden truncate min-[1500px]:inline">{tab.label}</span>
              <span className="truncate min-[1500px]:hidden">{tab.shortLabel}</span>
            </button>
          );
        })}
      </div>
      <div className="studio-scroll max-h-[calc(100vh-15.5rem)] overflow-y-auto p-3">
        {tabs.map(tab => (
          <div
            key={tab.key}
            role="tabpanel"
            hidden={activeTab !== tab.key}
          >
            {tab.content}
          </div>
        ))}
      </div>
    </section>
  );
};

export default ConfigurationTabsPanel;
