// Workspace pages: one entry per view. Paths live under /app/<name>.

import { lazy, type ComponentType, type LazyExoticComponent } from 'react';
import type { IconName } from '../lib/icons';

export type PageName = 'overview' | 'products' | 'insights' | 'lance' | 'inventory' | 'invoices' | 'debts' | 'books' | 'position' | 'data' | 'settings';

export interface PageDef {
  name: PageName;
  title: string;
  description: string;
  /** Scoped pages show the scope bar and read the current dataset/date scope. */
  scoped: boolean;
  /** Extra class on the page's <section class="view"> wrapper. */
  sectionClass?: string;
  nav: { label: string; icon: IconName; group: 'analyse' | 'operate' | 'bottom' };
  Component: LazyExoticComponent<ComponentType>;
}

export const PAGES: PageDef[] = [
  {
    name: 'overview',
    title: 'Overview',
    description: 'How the business is doing for the data and dates you choose, compared with the period before.',
    scoped: true,
    nav: { label: 'Overview', icon: 'overview', group: 'analyse' },
    Component: lazy(() => import('./views/Overview')),
  },
  {
    name: 'products',
    title: 'Products',
    description: 'Every product or service in your records, ranked by what it earns and what it costs.',
    scoped: true,
    nav: { label: 'Products', icon: 'products', group: 'analyse' },
    Component: lazy(() => import('./views/Products')),
  },
  {
    name: 'insights',
    title: 'Insights',
    description: 'Findings calculated from your records — every number below can be traced back to an imported row.',
    scoped: true,
    nav: { label: 'Insights', icon: 'insights', group: 'analyse' },
    Component: lazy(() => import('./views/Insights')),
  },
  {
    name: 'lance',
    title: 'Ask Lance',
    description: 'Ask about your business in plain language. Lance answers from your own records and says when data is missing.',
    scoped: true,
    sectionClass: 'view-lance',
    nav: { label: 'Ask Lance', icon: 'sparkles', group: 'analyse' },
    Component: lazy(() => import('./views/Lance')),
  },
  {
    name: 'inventory',
    title: 'Inventory',
    description: 'Track stock with an auditable ledger. Sales imports never change stock — only the movements you record here do.',
    scoped: false,
    nav: { label: 'Inventory', icon: 'inventory', group: 'operate' },
    Component: lazy(() => import('./views/Inventory')),
  },
  {
    name: 'invoices',
    title: 'Invoices',
    description: 'Invoices, quotes and receipts in cedis, shared on WhatsApp as a PDF. Payments are tracked in the debt book.',
    scoped: false,
    nav: { label: 'Invoices', icon: 'receipt', group: 'operate' },
    Component: lazy(() => import('./views/Invoices')),
  },
  {
    name: 'debts',
    title: 'Debt book',
    description: 'Who owes you and whom you owe: credit sales, supplier credit, part-payments and friendly reminders.',
    scoped: false,
    nav: { label: 'Debt book', icon: 'users', group: 'operate' },
    Component: lazy(() => import('./views/Debts')),
  },
  {
    name: 'books',
    title: 'Books',
    description: 'Profit and loss, what you own and owe, and money in and out, kept automatically from your imports, MoMo and stock.',
    scoped: false,
    nav: { label: 'Books', icon: 'receipt', group: 'operate' },
    Component: lazy(() => import('./views/Books')),
  },
  {
    name: 'position',
    title: 'Financial position',
    description: 'What the business owns and owes on any date, built from the balances you record.',
    scoped: false,
    nav: { label: 'Financial position', icon: 'scale', group: 'operate' },
    Component: lazy(() => import('./views/Position')),
  },
  {
    name: 'data',
    title: 'Data imports',
    description: 'Bring in sales, cost and Mobile Money records. Every file is checked row by row, and nothing is dropped without a reason.',
    scoped: false,
    nav: { label: 'Data imports', icon: 'database', group: 'operate' },
    Component: lazy(() => import('./views/Data')),
  },
  {
    name: 'settings',
    title: 'Settings',
    description: 'Your profile, how the workspace looks, and who on your team can see it.',
    scoped: false,
    nav: { label: 'Settings', icon: 'settings', group: 'bottom' },
    Component: lazy(() => import('./views/Settings')),
  },
];

/** Old page names (and old hash links) that still resolve. */
export const LEGACY_ROUTES: Record<string, PageName> = {
  dashboard: 'overview',
  catalogue: 'products',
  'ask-lance': 'lance',
  'financial-position': 'position',
  profile: 'settings',
};

/** Map any page name, legacy name, or hash fragment to a known page. */
export function resolvePageName(raw: string | undefined | null): PageName {
  const name = (raw ?? '').replace(/^#/, '');
  const mapped = LEGACY_ROUTES[name] ?? name;
  return (PAGES.some((page) => page.name === mapped) ? mapped : 'overview') as PageName;
}

export const pagePath = (name: PageName): string => `/app/${name}`;
