// Per-page chrome: views render their top-bar buttons through <PageActions>,
// which portals them into the top bar's actions slot.

import { createContext, useContext, type ReactNode } from 'react';
import { createPortal } from 'react-dom';

export const ActionsSlotContext = createContext<HTMLElement | null>(null);

export function PageActions({ children }: { children: ReactNode }) {
  const slot = useContext(ActionsSlotContext);
  return slot ? createPortal(children, slot) : null;
}
