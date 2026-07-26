import React, { useState, useCallback } from 'react';
import { useGisStore } from '../../store/useGisStore';
import { useI18n } from '../../i18n';
import { createZone, deleteZone, nominatimSearch } from '../../lib/api';
import { nominatimReverse } from '../../lib/api';
import type { GisZone } from '../../types';

const ZoneList: React.FC = () => {
  const { t } = useI18n();
  const zones = useGisStore(s => s.zones);
  const selectedZoneId = useGisStore(s => s.selectedZoneId);
  const activeProjectId = useGisStore(s => s.activeProjectId);
  const setSelectedZone = useGisStore(s => s.setSelectedZone);
  const addZone = useGisStore(s => s.addZone);
  const removeZone = useGisStore(s => s.removeZone);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState('');
  const [searchQ, setSearchQ] = useState('');
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [searching, setSearching] = useState(false);

  const handleCreate = useCallback(async () => {
    if (!newName.trim() || !activeProjectId) return;
    try {
      const zone = await createZone({ name: newName.trim(), project_id: activeProjectId });
      addZone(zone);
      setNewName('');
      setCreating(false);
      setSelectedZone(zone.id);
    } catch (err) { console.error(err); }
  }, [newName, activeProjectId]);

  const handleDelete = useCallback(async (id: string, name: string) => {
    if (!confirm(t('zone.deleteConfirm', { name }))) return;
    try {
      await deleteZone(id);
      removeZone(id);
      if (selectedZoneId === id) setSelectedZone(null);
    } catch (err) { console.error(err); }
  }, [selectedZoneId]);

  const handleSearch = useCallback(async () => {
    if (!searchQ.trim()) return;
    setSearching(true);
    try {
      const results = await nominatimSearch(searchQ, 'city');
      setSearchResults(results || []);
    } catch (err) { console.error(err); }
    finally { setSearching(false); }
  }, [searchQ]);

  return (
    <div className="gis-panel rounded-xl overflow-hidden flex flex-col max-h-full">
      <div className="p-3 border-b border-salvi-line flex items-center justify-between">
        <span className="text-sm font-semibold text-salvi-black">{t('nav.projects')}</span>
        <button
          onClick={() => setCreating(!creating)}
          className="text-xs bg-salvi-black text-white rounded-md px-2.5 py-1 hover:opacity-90 transition-opacity"
        >
          + {t('zone.create')}
        </button>
      </div>

      {/* Create zone */}
      {creating && (
        <div className="p-3 border-b border-salvi-line space-y-2 bg-salvi-surface">
          <input
            value={newName}
            onChange={e => setNewName(e.target.value)}
            placeholder={t('zone.name')}
            className="w-full border border-salvi-line rounded-md px-2.5 py-1.5 text-sm"
            autoFocus
          />
          <div className="flex gap-1">
            <input
              value={searchQ}
              onChange={e => setSearchQ(e.target.value)}
              placeholder={t('zone.search')}
              className="flex-1 border border-salvi-line rounded-md px-2.5 py-1.5 text-sm"
              onKeyDown={e => e.key === 'Enter' && handleSearch()}
            />
            <button onClick={handleSearch} disabled={searching} className="text-xs bg-salvi-grey text-white rounded-md px-2 py-1">
              🔍
            </button>
          </div>
          {searching && <div className="text-xs text-salvi-muted">{t('actions.loading')}</div>}
          {searchResults.length > 0 && (
            <div className="max-h-32 overflow-y-auto space-y-1">
              {searchResults.map((r, i) => (
                <button
                  key={i}
                  className="w-full text-left text-xs p-1.5 rounded hover:bg-salvi-line/50"
                  onClick={() => {
                    const coords = r.lat && r.lon ? { lat: parseFloat(r.lat), lon: parseFloat(r.lon) } : null;
                    setNewName(r.display_name?.split(',')[0] || r.display_name || newName);
                    setSearchResults([]);
                  }}
                >
                  {r.display_name}
                </button>
              ))}
            </div>
          )}
          <div className="flex gap-2 pt-1">
            <button onClick={handleCreate} className="flex-1 text-xs bg-salvi-black text-white rounded-md py-1.5">{t('actions.save')}</button>
            <button onClick={() => { setCreating(false); setSearchResults([]); }} className="text-xs text-salvi-grey py-1.5">{t('actions.cancel')}</button>
          </div>
        </div>
      )}

      {/* Zone list */}
      <div className="overflow-y-auto flex-1 gis-scroll">
        {zones.length === 0 && (
          <div className="p-6 text-center text-sm text-salvi-muted">
            {t('actions.loading')}
          </div>
        )}
        {zones.map(zone => (
          <div
            key={zone.id}
            onClick={() => setSelectedZone(zone.id)}
            className={`flex items-center gap-2 px-3 py-2.5 cursor-pointer border-b border-salvi-line/50 transition-colors ${
              selectedZoneId === zone.id ? 'bg-salvi-black/5' : 'hover:bg-salvi-surface'
            }`}
          >
            <div className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: zone.color }} />
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium text-salvi-black truncate">{zone.name}</div>
              <div className="text-xs text-salvi-muted">{zone.type || '—'}</div>
            </div>
            <button
              onClick={e => { e.stopPropagation(); handleDelete(zone.id, zone.name); }}
              className="text-salvi-muted hover:text-state-danger text-xs p-1"
              title={t('zone.delete')}
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </div>
  );
};

export default ZoneList;
