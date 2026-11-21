import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { Link, NavLink, Redirect, Router, useLocation, useNavigate } from './router';

function Where() {
  const { pathname, search } = useLocation();
  return <output data-testid="where">{pathname + search}</output>;
}

function GoButton({ to, replace }: { to: string; replace?: boolean }) {
  const navigate = useNavigate();
  return (
    <button type="button" onClick={() => navigate(to, { replace })}>
      go
    </button>
  );
}

const where = () => screen.getByTestId('where').textContent;

describe('router', () => {
  beforeEach(() => window.history.replaceState(null, '', '/app/overview'));
  afterEach(() => window.history.replaceState(null, '', '/'));

  it('navigates on a plain click and pushes a history entry', () => {
    render(
      <Router>
        <Link to="/app/products">Products</Link>
        <Where />
      </Router>,
    );
    const before = window.history.length;
    fireEvent.click(screen.getByRole('link', { name: 'Products' }));
    expect(where()).toBe('/app/products');
    expect(window.location.pathname).toBe('/app/products');
    expect(window.history.length).toBe(before + 1);
  });

  it('leaves modified and middle clicks to the browser (new tab / window)', () => {
    render(
      <Router>
        <Link to="/app/products">Products</Link>
        <Link to="/app/data" target="_blank">
          Data
        </Link>
        <Where />
      </Router>,
    );
    const link = screen.getByRole('link', { name: 'Products' });
    for (const init of [{ ctrlKey: true }, { metaKey: true }, { shiftKey: true }, { altKey: true }, { button: 1 }]) {
      expect(fireEvent.click(link, init)).toBe(true); // not prevented
    }
    expect(fireEvent.click(screen.getByRole('link', { name: 'Data' }))).toBe(true);
    expect(where()).toBe('/app/overview');
  });

  it('respects a consumer onClick that prevents default', () => {
    render(
      <Router>
        <Link to="/app/products" onClick={(event) => event.preventDefault()}>
          Products
        </Link>
        <Where />
      </Router>,
    );
    fireEvent.click(screen.getByRole('link', { name: 'Products' }));
    expect(where()).toBe('/app/overview');
  });

  it('marks the active NavLink with aria-current, ignoring a trailing slash', () => {
    window.history.replaceState(null, '', '/app/products/');
    render(
      <Router>
        <NavLink to="/app/products">Products</NavLink>
        <NavLink to="/app/data">Data</NavLink>
      </Router>,
    );
    expect(screen.getByRole('link', { name: 'Products' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: 'Data' })).not.toHaveAttribute('aria-current');
  });

  it('follows back/forward (popstate)', () => {
    render(
      <Router>
        <Where />
      </Router>,
    );
    act(() => {
      window.history.pushState(null, '', '/app/insights?x=1');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });
    expect(where()).toBe('/app/insights?x=1');
  });

  it('replaces the entry for replace navigations and Redirect', () => {
    render(
      <Router>
        <GoButton to="/app/data" replace />
        <Where />
      </Router>,
    );
    const before = window.history.length;
    fireEvent.click(screen.getByRole('button', { name: 'go' }));
    expect(where()).toBe('/app/data');
    expect(window.history.length).toBe(before);

    render(
      <Router>
        <Redirect to="/app/settings" />
      </Router>,
    );
    expect(window.location.pathname).toBe('/app/settings');
    expect(window.history.length).toBe(before);
  });
});
