// The guides: one per everyday situation, with when to use it, why, how, and a short video.
// Shared by the landing page ("How it works") and the app (Help & guides, the first-visit tour).
// Videos are recorded from the real app by tools/demo/record.mjs; tools/demo/voice.py adds the
// spoken narration (narration.json) in each language.

import narration from './narration.json';

export interface Guide {
  slug: string;
  title: string;
  /** The situation, in the owner's words. */
  when: string;
  why: string;
  steps: string[];
  /** Workspace page to open, e.g. 'debts'. */
  page: string;
  poster: string;
}

const media = (slug: string) => ({ poster: `/assets/demo/${slug}.jpg` });

export const GUIDES: Guide[] = [
  {
    slug: 'start',
    title: 'Your first minute',
    when: 'Every morning, before you open the shop.',
    why: 'See how the business is really doing (sales, profit, what changed) in one place, and what to do about it.',
    steps: [
      'Bring your records in: Data imports → Import data (a spreadsheet, or paste MoMo messages).',
      'Open Overview to see sales, profit and the change since the last period.',
      'Open Insights and tap a suggestion to see the reasons and the next step.',
    ],
    page: 'overview',
    ...media('start'),
  },
  {
    slug: 'credit',
    title: 'Selling on credit',
    when: 'A customer takes goods now and pays later, or you buy from a supplier on credit.',
    why: 'No more lost notebook debts: Ferlance remembers who owes what, how late it is, and helps you collect.',
    steps: [
      'Debt book → New credit sale. A name and an amount are enough.',
      'Tap Remind to send a WhatsApp or SMS reminder from your own phone, with where to pay by MoMo.',
      'When they pay, tap Record payment, or confirm the MoMo message Ferlance matches to the debt.',
    ],
    page: 'debts',
    ...media('credit'),
  },
  {
    slug: 'invoices',
    title: 'Invoices and receipts',
    when: 'A customer or company asks for an invoice, a quote or a receipt.',
    why: 'A proper PDF in cedis with your details, numbered without gaps, ready to send on WhatsApp.',
    steps: [
      'Invoices → New invoice (or switch to Quotes or Receipts).',
      'Pick items from your stock or type them, with quantity and price.',
      'Tap Share PDF to send it. An unpaid invoice waits in the debt book until it is paid.',
    ],
    page: 'invoices',
    ...media('invoices'),
  },
  {
    slug: 'notebook',
    title: 'From your exercise book',
    when: 'You keep sales, debtors or spending in an exercise book.',
    why: 'Your paper records become real numbers without retyping everything, and you check every line first.',
    steps: [
      'Notebook pages → Add a page.',
      'Take a photo of the page (read by AI), or type the lines (free).',
      'Check each line, untick anything that should not be added, then press Add.',
    ],
    page: 'notebook',
    ...media('notebook'),
  },
  {
    slug: 'stock',
    title: 'Keeping stock right',
    when: 'Goods arrive, goods go out, or you count the shelves.',
    why: 'Know what to restock before you run out, what your stock is worth, and where goods go missing.',
    steps: [
      'Inventory → Add product for each item you sell.',
      'Stock in / out when goods arrive or leave; Scan invoice reads a delivery note photo.',
      'Stocktake compares your count with the records and shows the differences.',
    ],
    page: 'inventory',
    ...media('stock'),
  },
  {
    slug: 'books',
    title: 'Your books and MoMo statements',
    when: 'At month end, or when an accountant or a lender asks for your accounts.',
    why: 'Real profit and loss and a balance sheet, kept for you from what you already record. No bookkeeping.',
    steps: [
      'Books shows profit and loss, what you own and owe, and money in and out.',
      'Reconcile → Import a statement from MTN, Telecel, AT or your bank to check the books against it.',
      'Planning → Downloads gives your accountant the year-end pack.',
    ],
    page: 'books',
    ...media('books'),
  },
  {
    slug: 'loan',
    title: 'Getting ready for a loan',
    when: 'You want a loan from a bank, a rural bank or a microfinance company.',
    why: 'Show your track record with proof (sales backed by MoMo and bank statements) in one link you control.',
    steps: [
      'Credit report shows your readiness score and how to raise it.',
      'Import your MoMo and bank statements so more of your sales are proven.',
      'Tick the box and Create link; send it to the lender. Withdraw it any time.',
    ],
    page: 'credit',
    ...media('loan'),
  },
];

export const TOUR_KEY = 'ferlance-tour-seen';

/** Narration languages, in menu order. Drafts still need a native speaker's check. */
export type GuideLang = 'en' | 'tw' | 'ga' | 'ee' | 'fat';
export const GUIDE_LANGS: { code: GuideLang; label: string; draft: boolean }[] = Object.entries(narration.languages).map(
  ([code, info]) => ({
    code: code as GuideLang,
    label: info.label,
    draft: info.draft,
  }),
);
/** Remembers the viewer's narration language (per browser). */
export const LANG_KEY = 'ferlance-guide-lang';

export const isGuideLang = (value: unknown): value is GuideLang => GUIDE_LANGS.some((lang) => lang.code === value);

/** The guide video with its narration in `lang`. */
export const guideVideo = (slug: string, lang: GuideLang): string => `/assets/demo/${slug}.${lang}.mp4`;

/** What the narrator says, for reading along (and for anyone who can't play sound). */
export function guideScript(slug: string, lang: GuideLang): string {
  const scripts = (narration.guides as Record<string, Partial<Record<GuideLang, string>>>)[slug];
  return scripts?.[lang] ?? scripts?.en ?? '';
}

/** Credit the voice models require (Africa TTS is CC BY-NC 4.0: attribution, non-commercial). */
export const VOICE_CREDIT =
  'Voices: English by Kokoro (Apache 2.0); Twi, Ga, Ewe and Fante by Africa TTS from AfriSpeech (CC BY-NC 4.0). Translations are drafts being checked by native speakers.';
