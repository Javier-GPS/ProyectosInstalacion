import { buildCanonicalConfigRequest } from './configRequest';

export const buildReportRequestBody = (config: any, configOverride?: any) =>
  buildCanonicalConfigRequest(config, configOverride);
