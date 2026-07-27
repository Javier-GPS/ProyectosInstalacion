import { useCallback, useEffect, useState } from 'react';

export interface HashParams {
  projectId?: string;
  zoneId?: string;
  step?: string;
  lumId?: string;
}

const parseHash = (): HashParams => {
  const hash = window.location.hash.replace(/^#\/?/, '');
  if (!hash) return {};
  const parts = hash.split('/');
  const params: HashParams = {};
  for (let i = 0; i < parts.length; i += 2) {
    const key = parts[i];
    const val = parts[i + 1];
    if (key && val) {
      if (key === 'proyecto') params.projectId = val;
      else if (key === 'zona') params.zoneId = val;
      else if (key === 'step') params.step = val;
      else if (key === 'lum') params.lumId = val;
    }
  }
  return params;
};

const buildHash = (params: HashParams): string => {
  const parts: string[] = [];
  if (params.projectId) parts.push('proyecto', params.projectId);
  if (params.zoneId) parts.push('zona', params.zoneId);
  if (params.step) parts.push('step', params.step);
  if (params.lumId) parts.push('lum', params.lumId);
  return '#/' + parts.join('/');
};

export const useHashRouter = () => {
  const [params, setParams] = useState<HashParams>(parseHash);

  useEffect(() => {
    const onHashChange = () => setParams(parseHash());
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  const setHashParams = useCallback((next: HashParams) => {
    const hash = buildHash(next);
    if (window.location.hash !== hash) {
      window.history.pushState(null, '', hash);
      setParams(next);
    }
  }, []);

  return { params, setHashParams };
};
