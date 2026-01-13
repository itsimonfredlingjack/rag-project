import type { Source } from '../../stores/useAppStore';

export const CITATION_RE = /\[(?:Källa\s+)?(\d+)\]/g;

export function extractCitedSourceIds(answer: string, sources: Source[]): Set<string> {
    const cited = new Set<string>();
    if (!answer) return cited;

    for (const match of answer.matchAll(CITATION_RE)) {
        const n = Number(match[1]);
        if (!Number.isFinite(n) || n < 1) continue;
        const src = sources[n - 1];
        if (src?.id) cited.add(src.id);
    }

    return cited;
}
