import React, { useEffect, useRef, useState } from 'react';
import { useI18n } from '../../i18n';
import type { TramoSummary } from '../../lib/tramos';

interface TramoRowMenuProps {
  tramo: Pick<TramoSummary, 'id' | 'name'>;
  busy?: boolean;
  onRename: (next: string) => void;
  onDuplicate: () => void;
  onDelete: () => void;
  onOpen: () => void;
}

const TramoRowMenu: React.FC<TramoRowMenuProps> = ({
  tramo,
  busy,
  onRename,
  onDuplicate,
  onDelete,
  onOpen,
}) => {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [draft, setDraft] = useState(tramo.name);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [open]);

  useEffect(() => {
    if (renaming) setDraft(tramo.name);
  }, [renaming, tramo.name]);

  const submitRename = () => {
    const next = draft.trim();
    if (next && next !== tramo.name) onRename(next);
    setRenaming(false);
    setOpen(false);
  };

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={event => {
          event.stopPropagation();
          setOpen(value => !value);
        }}
        disabled={busy}
        className="rounded-md p-1.5 text-[#6a6a6a] transition-colors hover:bg-[#FFFFFF] hover:text-[#6A6A6A] disabled:opacity-50"
        aria-label="Acciones"
        title="Acciones"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="5" r="1.2" fill="currentColor" />
          <circle cx="12" cy="12" r="1.2" fill="currentColor" />
          <circle cx="12" cy="19" r="1.2" fill="currentColor" />
        </svg>
      </button>
      {open && (
        <div className="absolute right-0 z-50 mt-1 w-44 overflow-hidden rounded-lg border border-[#E8E2D8] bg-[#FFFFFF] py-1 shadow-lg">
          {!renaming && (
            <>
              <button
                type="button"
                onClick={() => { setOpen(false); onOpen(); }}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-[#6A6A6A] hover:bg-[#F7F4EF]"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M3 21h18" />
                  <path d="M5 21V8l7-5 7 5v13" />
                  <path d="M9 21v-6h6v6" />
                </svg>
                {t('tramos.menu.open')}
              </button>
              <button
                type="button"
                onClick={() => setRenaming(true)}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-[#6A6A6A] hover:bg-[#F7F4EF]"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                </svg>
                {t('tramos.menu.rename')}
              </button>
              <button
                type="button"
                onClick={() => { setOpen(false); onDuplicate(); }}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-[#6A6A6A] hover:bg-[#F7F4EF]"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                </svg>
                {t('tramos.menu.duplicate')}
              </button>
              <div className="my-1 border-t border-[#E8E2D8]" />
              <button
                type="button"
                onClick={() => { setOpen(false); onDelete(); }}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-[#B42318] hover:bg-[#B42318]/15"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="3 6 5 6 21 6" />
                  <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
                  <path d="M10 11v6M14 11v6" />
                  <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
                </svg>
                {t('tramos.menu.delete')}
              </button>
            </>
          )}
          {renaming && (
            <div className="px-3 py-2" onClick={event => event.stopPropagation()}>
              <input
                autoFocus
                value={draft}
                onChange={event => setDraft(event.target.value)}
                onKeyDown={event => {
                  if (event.key === 'Enter') submitRename();
                  else if (event.key === 'Escape') { setRenaming(false); setOpen(false); }
                }}
                maxLength={120}
                className="w-full rounded-md border border-[#E8E2D8] px-2 py-1 text-sm outline-none focus:border-[#1E1E1E] focus:ring-2 focus:ring-[#1E1E1E]/10"
              />
              <div className="mt-2 flex items-center justify-end gap-1">
                <button
                  type="button"
                  onClick={() => { setRenaming(false); setOpen(false); }}
                  className="rounded-md px-2 py-1 text-xs text-[#A09A91] hover:bg-[#FFFFFF]"
                >
                  {t('unsavedChanges.cancel')}
                </button>
                <button
                  type="button"
                  onClick={submitRename}
                  className="rounded-md bg-[#1E1E1E] px-2 py-1 text-xs font-semibold text-white hover:bg-[#333333]"
                >
                  OK
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default TramoRowMenu;
