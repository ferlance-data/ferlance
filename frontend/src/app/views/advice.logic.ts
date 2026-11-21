// Pure helpers for the advice cards and detail sheet.

import { money, number, plainPercent } from '../../lib/format';
import type { Advice, AdviceEvidence, AdviceItem, AdviceSeverity } from '../../lib/types';
import type { Tone } from '../components/ui';
import type { IconName } from '../../lib/icons';

export const SEVERITY: Record<AdviceSeverity, { label: string; tone: Tone; icon: IconName }> = {
  risk: { label: 'Act now', tone: 'error', icon: 'alert' },
  attention: { label: 'Watch', tone: 'warning', icon: 'trending-down' },
  opportunity: { label: 'Opportunity', tone: 'success', icon: 'trending-up' },
  info: { label: 'Good to know', tone: 'info', icon: 'info' },
};

export function evidenceText(entry: AdviceEvidence): string {
  if (typeof entry.value !== 'number') return String(entry.value);
  if (entry.format === 'money') return money(entry.value);
  if (entry.format === 'percent') return plainPercent(entry.value, 1);
  return number(entry.value, Number.isInteger(entry.value) ? 0 : 1);
}

/** The items to show: the server's top list first, then (when expanded) everything else in rank order. */
export function visibleAdvice(advice: Advice | undefined, expanded: boolean): AdviceItem[] {
  if (!advice) return [];
  if (expanded) return advice.items;
  const byId = new Map(advice.items.map((item) => [item.id, item]));
  return advice.top.map((id) => byId.get(id)).filter((item): item is AdviceItem => Boolean(item));
}
