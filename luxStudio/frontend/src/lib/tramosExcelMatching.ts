/**
 * Fuzzy string matching for Excel column → system parameter auto-mapping.
 *
 * Combines several signals and assigns scores in [0, 1]. The greedy
 * matcher then picks non-conflicting pairs above a threshold so each
 * column and each parameter is only used once.
 *
 * Signals:
 *  1. Normalized alias exact match  (very strong)
 *  2. Dice / Jaccard on token sets   (handles word reordering)
 *  3. Best token-level Levenshtein  (handles typos and singulars)
 *  4. Substring containment         (handles prefixes and units)
 */

const DIACRITICS_REGEX = /\p{Diacritic}/gu;
const PUNCTUATION_REGEX = /[^\p{L}\p{N}]+/gu;
const CAMEL_CASE_REGEX = /([\p{Ll}\p{N}])([\p{Lu}])/gu;

export const normalize = (input: string): string => {
  if (!input) return '';
  return input
    .normalize('NFD')
    .replace(DIACRITICS_REGEX, '')
    .toLowerCase()
    .replace(PUNCTUATION_REGEX, ' ')
    .replace(/\s+/g, ' ')
    .trim();
};

export const tokenize = (input: string): string[] => {
  const normalized = normalize(input);
  if (!normalized) return [];
  return normalized
    .split(' ')
    .flatMap(part => part.split(CAMEL_CASE_REGEX).filter(Boolean))
    .map(t => t.trim())
    .filter(t => t.length > 0);
};

export const tokenizeWithSeparators = (input: string): string[] => {
  const normalized = normalize(input).replace(/([a-z])([0-9])/g, '$1 $2').replace(/([0-9])([a-z])/g, '$1 $2');
  if (!normalized) return [];
  return normalized
    .split(/\s+/)
    .flatMap(part => part.split(CAMEL_CASE_REGEX).filter(Boolean))
    .filter(t => t.length > 0);
};

export const levenshtein = (a: string, b: string): number => {
  if (a === b) return 0;
  if (!a.length) return b.length;
  if (!b.length) return a.length;

  let previous = new Array(b.length + 1);
  let current = new Array(b.length + 1);
  for (let j = 0; j <= b.length; j++) previous[j] = j;

  for (let i = 1; i <= a.length; i++) {
    current[0] = i;
    for (let j = 1; j <= b.length; j++) {
      const cost = a.charCodeAt(i - 1) === b.charCodeAt(j - 1) ? 0 : 1;
      current[j] = Math.min(
        current[j - 1] + 1,
        previous[j] + 1,
        previous[j - 1] + cost,
      );
    }
    [previous, current] = [current, previous];
  }
  return previous[b.length];
};

export const levenshteinSimilarity = (a: string, b: string): number => {
  if (!a && !b) return 1;
  if (!a || !b) return 0;
  const distance = levenshtein(a, b);
  const maxLen = Math.max(a.length, b.length);
  return maxLen === 0 ? 1 : 1 - distance / maxLen;
};

export const jaccard = (a: string[], b: string[]): number => {
  if (!a.length && !b.length) return 1;
  if (!a.length || !b.length) return 0;
  const setA = new Set(a);
  const setB = new Set(b);
  let intersection = 0;
  for (const item of setA) {
    if (setB.has(item)) intersection++;
  }
  const union = setA.size + setB.size - intersection;
  return union === 0 ? 0 : intersection / union;
};

export const dice = (a: string[], b: string[]): number => {
  if (!a.length && !b.length) return 1;
  if (!a.length || !b.length) return 0;
  const setA = new Set(a);
  const setB = new Set(b);
  let intersection = 0;
  for (const item of setA) {
    if (setB.has(item)) intersection++;
  }
  const total = setA.size + setB.size;
  return total === 0 ? 0 : (2 * intersection) / total;
};

export const bestPairwiseTokenSimilarity = (a: string[], b: string[]): number => {
  if (!a.length || !b.length) return 0;
  let best = 0;
  for (const ta of a) {
    for (const tb of b) {
      const s = levenshteinSimilarity(ta, tb);
      if (s > best) best = s;
    }
  }
  return best;
};

export const containsSubstring = (a: string, b: string): boolean => {
  if (!a || !b) return false;
  const aN = normalize(a);
  const bN = normalize(b);
  if (aN.length < 3 || bN.length < 3) return false;
  return aN.includes(bN) || bN.includes(aN);
};

export interface MatchScore {
  dice: number;
  jaccard: number;
  tokenSimilarity: number;
  aliasExact: number;
  aliasFuzzy: number;
  substring: number;
  combined: number;
}

export const bestBigramMatch = (headerTokens: string[], aliasTokensList: string[][]): number => {
  if (headerTokens.length < 2) return 0;
  const bigrams: string[] = [];
  for (let i = 0; i < headerTokens.length - 1; i++) {
    bigrams.push(`${headerTokens[i]} ${headerTokens[i + 1]}`);
  }
  let best = 0;
  for (const aliasTokens of aliasTokensList) {
    if (aliasTokens.length < 2) continue;
    for (let i = 0; i < aliasTokens.length - 1; i++) {
      const aliasBigram = `${aliasTokens[i]} ${aliasTokens[i + 1]}`;
      for (const bg of bigrams) {
        if (bg === aliasBigram) return 1;
        const s = levenshteinSimilarity(bg, aliasBigram);
        if (s > best) best = s;
      }
    }
  }
  return best;
};

export const scoreCandidate = (
  header: string,
  headerTokens: string[],
  aliasTokensList: string[][],
  aliasesNormalized: string[],
  paramTokens: string[],
  paramNormalized: string,
): MatchScore => {
  const headerNorm = normalize(header);
  const aliasExact = aliasesNormalized.includes(headerNorm) ? 1 : 0;
  const aliasFuzzy = Math.max(
    0,
    ...aliasTokensList.map(tokens => bestPairwiseTokenSimilarity(headerTokens, tokens)),
    ...aliasesNormalized.map(alias => levenshteinSimilarity(headerNorm, alias)),
  );

  const diceVal = dice(headerTokens, paramTokens);
  const jaccardVal = jaccard(headerTokens, paramTokens);
  const tokenSim = bestPairwiseTokenSimilarity(headerTokens, paramTokens);
  const substring = containsSubstring(header, paramNormalized) ? 1 : 0;
  const tokenMatch = headerTokens.some(ht => paramTokens.includes(ht)) ? 1 : 0;
  const bigram = bestBigramMatch(headerTokens, aliasTokensList);
  const tokenCoverage = headerTokens.length === 0
    ? 0
    : headerTokens.filter(ht => paramTokens.includes(ht)).length / headerTokens.length;

  let combined: number;
  if (aliasExact === 1) {
    combined = 1;
  } else {
    const strong = Math.max(tokenSim, aliasFuzzy, substring, tokenMatch, bigram);
    const weak = 0.5 * diceVal + 0.3 * jaccardVal + 0.2 * tokenMatch;
    combined = 0.65 * strong + 0.35 * weak;
    if (substring === 1) combined = Math.max(combined, 0.85);
    if (bigram === 1) combined = Math.max(combined, 0.92);
    if (bigram >= 0.85) combined = Math.max(combined, 0.78);
    if (tokenMatch === 1 && tokenCoverage < 0.5) {
      combined *= 0.85;
    }
  }
  return { dice: diceVal, jaccard: jaccardVal, tokenSimilarity: tokenSim, aliasExact, aliasFuzzy, substring, combined };
};
