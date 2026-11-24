// The signed-in business, shared by every screen.

import { createContext, useContext } from 'react';
import type { Business } from '../../frontend/src/lib/types';

export interface Session {
  business: Business;
  /** e.g. `/api/businesses/<id>/debts` */
  path: (suffix: string) => string;
  /** Owners and managers record sales and debts; accountants only read. */
  canWrite: boolean;
  signOut: () => void;
}

export const SessionContext = createContext<Session | null>(null);

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error('useSession must be used inside a signed-in screen');
  return session;
}

export function makeSession(business: Business, signOut: () => void): Session {
  return {
    business,
    path: (suffix) => `/api/businesses/${encodeURIComponent(business.id)}${suffix}`,
    canWrite: business.role !== 'accountant',
    signOut,
  };
}
