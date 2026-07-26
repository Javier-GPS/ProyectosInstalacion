import React, { useEffect, useRef, useState } from 'react';

interface TramoNameInputProps {
  value: string;
  onSave: (next: string) => Promise<void> | void;
  onCancel?: () => void;
  maxLength?: number;
  label?: string;
  placeholder?: string;
  disabled?: boolean;
  compact?: boolean;
}

const TramoNameInput: React.FC<TramoNameInputProps> = ({
  value,
  onSave,
  onCancel,
  maxLength = 120,
  label,
  placeholder,
  disabled,
  compact = false,
}) => {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!editing) setDraft(value);
  }, [value, editing]);

  useEffect(() => {
    if (editing) {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [editing]);

  const commit = async () => {
    const next = draft.trim();
    if (!next) {
      setError(' ');
      inputRef.current?.focus();
      return;
    }
    if (next === value) {
      setEditing(false);
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSave(next);
      setEditing(false);
    } catch (err: any) {
      setError(err.message || 'Error');
    } finally {
      setSaving(false);
    }
  };

  const cancel = () => {
    setDraft(value);
    setError(null);
    setEditing(false);
    onCancel?.();
  };

  if (disabled) {
    return (
      <div>
        {label && <div className={`${compact ? 'text-[10px] text-indigo-700' : 'text-xs text-[#6a6a6a]'} font-semibold uppercase tracking-wide`}>{label}</div>}
        <div className={`mt-1 truncate font-semibold ${compact ? 'text-sm text-indigo-950' : 'text-lg text-[#1E1E1E]'}`}>{value}</div>
      </div>
    );
  }

  if (!editing) {
    return (
      <div className="group flex items-center gap-2">
        <div className="min-w-0">
          {label && <div className={`${compact ? 'text-[10px] text-indigo-700' : 'text-xs text-[#6a6a6a]'} font-semibold uppercase tracking-wide`}>{label}</div>}
          <div className={`truncate font-semibold ${compact ? 'text-xs text-indigo-950' : 'mt-0.5 text-lg text-[#1E1E1E]'}`} title={value}>
            {value}
          </div>
        </div>
        <button
          type="button"
          onClick={() => setEditing(true)}
          className={`${compact ? 'bg-white/70 p-1 text-indigo-500 hover:bg-white hover:text-indigo-700' : 'p-1.5 text-[#6a6a6a] hover:bg-[#FFFFFF] hover:text-[#6A6A6A]'} rounded-md transition-colors`}
          title="Renombrar"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
          </svg>
        </button>
      </div>
    );
  }

  return (
    <div>
      {label && <div className={`${compact ? 'text-[10px] text-indigo-700' : 'text-xs text-[#6a6a6a]'} font-semibold uppercase tracking-wide`}>{label}</div>}
      <div className="mt-0.5 flex items-center gap-2">
        <input
          ref={inputRef}
          type="text"
          value={draft}
          onChange={event => setDraft(event.target.value)}
          onKeyDown={event => {
            if (event.key === 'Enter') {
              event.preventDefault();
              commit();
            } else if (event.key === 'Escape') {
              event.preventDefault();
              cancel();
            }
          }}
          onBlur={() => {
            if (!saving) commit();
          }}
          maxLength={maxLength}
          placeholder={placeholder}
          className={`${compact ? 'w-48 text-xs' : 'w-72 text-lg'} rounded-md border bg-[#FFFFFF] px-2.5 py-1 font-semibold text-[#1E1E1E] outline-none transition-colors focus:ring-2 ${
            error ? 'border-red-300 focus:border-red-400 focus:ring-red-100' : 'border-[#1E1E1E]/20 focus:border-[#1E1E1E] focus:ring-[#1E1E1E]/10'
          }`}
        />
        {saving && <span className="text-xs text-[#6a6a6a]">Guardando…</span>}
      </div>
      {error && error.trim() !== '' && (
        <div className="mt-1 text-xs text-red-600">{error}</div>
      )}
    </div>
  );
};

export default TramoNameInput;
