import { afterEach, describe, expect, it } from 'vitest';
import { chooseBusiness, rememberBusiness, ROLE_PERMISSIONS } from './workspace';

const a = { id: 'a', name: 'Own shop', currency: 'GHS', role: 'owner' as const };
const b = { id: 'b', name: 'Client', currency: 'GHS', role: 'accountant' as const };

describe('chooseBusiness', () => {
  afterEach(() => localStorage.clear());
  it('opens the remembered business while the user still belongs to it', () => {
    rememberBusiness('b');
    expect(chooseBusiness({ business: a, businesses: [a, b] })).toBe(b);
  });
  it('falls back to the first business when the remembered one is gone', () => {
    rememberBusiness('gone');
    expect(chooseBusiness({ business: a, businesses: [a, b] })).toBe(a);
    expect(chooseBusiness({ business: a })).toBe(a);
    expect(chooseBusiness({ business: null, businesses: [] })).toBeNull();
  });
});

describe('ROLE_PERMISSIONS', () => {
  it('keeps accountants away from data writes and team management', () => {
    expect(ROLE_PERMISSIONS.accountant).not.toContain('write_data');
    expect(ROLE_PERMISSIONS.accountant).toContain('write_balances');
    expect(ROLE_PERMISSIONS.manager).not.toContain('manage_team');
  });
});
