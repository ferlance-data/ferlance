// Workspace chrome: sidebar navigation, top bar (title, scope bar, page actions),
// and the routed page content.

import { Suspense, useCallback, useEffect, useState } from 'react';
import { signOut } from '../lib/api';
import { Link, NavLink, Redirect, useLocation, useNavigate } from '../lib/router';
import { Icon, IconSlot } from '../lib/icons';
import { toast } from '../lib/toast';
import { RANGE_OPTIONS, analysableDatasets, type RangePreset } from '../lib/scope';
import { WelcomeTour } from './components/Guides';
import { PageErrorBoundary } from './components/PageErrorBoundary';
import { SkeletonRows } from './components/ui';
import { ActionsSlotContext } from './page';
import { NAV_ORDER, PAGES, pagePath, resolvePageName, type PageDef } from './routes';
import { ROLE_LABEL, useScope, useWorkspace } from './workspace';

function BrandMark() {
  return (
    <svg className="brand-mark" viewBox="0 0 20 20" aria-hidden="true">
      <rect x="1" y="12" width="5" height="5" rx="1" />
      <rect x="7.5" y="7.5" width="5" height="5" rx="1" />
      <rect x="14" y="3" width="5" height="5" rx="1" />
    </svg>
  );
}

function NavItem({ page, pendingCount, onNavigate }: { page: PageDef; pendingCount?: number; onNavigate: () => void }) {
  return (
    // Close the phone drawer on click: navigation to a not-yet-loaded page commits only after its chunk arrives.
    <NavLink className="nav-item" to={pagePath(page.name)} data-page={page.name} onClick={onNavigate}>
      <IconSlot name={page.nav.icon} />
      {page.nav.label}
      {page.name === 'data' ? (
        <span className="nav-count" id="nav-data-count" hidden={!pendingCount}>
          {pendingCount || ''}
        </span>
      ) : null}
    </NavLink>
  );
}

function Sidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { user, business, businesses, datasets, role, switchBusiness } = useWorkspace();
  const name = business.name || 'Workspace';
  const pending = datasets.filter((item) => item.status === 'partial' || item.status === 'failed').length;
  const group = (key: PageDef['nav']['group']) => PAGES.filter((page) => page.nav.group === key).sort((a, b) => NAV_ORDER.indexOf(a.name) - NAV_ORDER.indexOf(b.name));
  return (
    <>
      <aside className="sidebar" id="sidebar" aria-label="Workspace navigation">
        <div className="sidebar-top">
          <Link className="brand" to={pagePath('overview')}>
            <BrandMark />
            Ferlance
          </Link>
          <button className="btn btn-ghost btn-icon sidebar-close" type="button" aria-label="Close navigation" data-icon="x" onClick={onClose}>
            <Icon name="x" />
          </button>
        </div>
        <div className="workspace-chip" id="workspace-chip">
          <span className="avatar" id="workspace-avatar">
            {name.slice(0, 1).toUpperCase()}
          </span>
          <span className="workspace-chip-text">
            <strong id="workspace-name">{name}</strong>
            <small id="workspace-email">{role === 'owner' ? user.email : `${ROLE_LABEL[role]} · ${user.email}`}</small>
          </span>
        </div>
        {businesses.length > 1 ? (
          <select
            className="select business-switch"
            id="business-switch"
            aria-label="Switch business"
            value={business.id}
            onChange={(event) => switchBusiness(event.target.value)}
          >
            {businesses.map((item) => (
              <option key={item.id} value={item.id}>
                {item.role && item.role !== 'owner' ? `${item.name} (${ROLE_LABEL[item.role]})` : item.name}
              </option>
            ))}
          </select>
        ) : null}
        <nav className="nav" id="nav">
          <p className="nav-label">Analyse</p>
          {group('analyse').map((page) => (
            <NavItem key={page.name} page={page} onNavigate={onClose} />
          ))}
          <p className="nav-label">Selling and stock</p>
          {group('sell').map((page) => (
            <NavItem key={page.name} page={page} pendingCount={pending} onNavigate={onClose} />
          ))}
          <p className="nav-label">Money and books</p>
          {group('money').map((page) => (
            <NavItem key={page.name} page={page} onNavigate={onClose} />
          ))}
        </nav>
        <div className="sidebar-bottom">
          {group('bottom').map((page) => (
            <NavItem key={page.name} page={page} onNavigate={onClose} />
          ))}
          <button className="nav-item" id="logout" type="button" onClick={() => void signOut()}>
            <IconSlot name="logout" />
            Sign out
          </button>
        </div>
      </aside>
      <div className="sidebar-backdrop" id="sidebar-backdrop" hidden={!open} onClick={onClose} />
    </>
  );
}

function ScopeBar({ hidden }: { hidden: boolean }) {
  const { datasets } = useWorkspace();
  const { scope, setScope, bounds } = useScope();
  const files = analysableDatasets(datasets);
  const [showCustom, setShowCustom] = useState(scope.range === 'custom');
  const [rangeChoice, setRangeChoice] = useState<RangePreset>(scope.range);
  const [from, setFrom] = useState(scope.from ?? '');
  const [to, setTo] = useState(scope.to ?? '');

  const onRange = (value: RangePreset) => {
    setRangeChoice(value);
    const custom = value === 'custom';
    setShowCustom(custom);
    if (custom) {
      setFrom((current) => current || bounds.from || '');
      setTo((current) => current || bounds.to || '');
      return;
    }
    setScope({ range: value });
  };

  const apply = () => {
    if (from && to && from > to) {
      toast('The start date must be on or before the end date.', { error: true });
      return;
    }
    setScope({ range: 'custom', from: from || null, to: to || null });
  };

  return (
    <div className="scope-bar" id="scope-bar" hidden={hidden}>
      <label className="scope-control">
        <span className="visually-hidden">Data scope</span>
        <IconSlot name="database" />
        <select id="scope-dataset" aria-label="Data scope" value={scope.datasetId} onChange={(event) => setScope({ datasetId: event.target.value })}>
          <option value="all">{files.length ? `All business data · ${files.filter((item) => item.included).length} files` : 'All business data'}</option>
          {files.length ? (
            <optgroup label="A single file">
              {files.map((item) => (
                <option key={item.id} value={item.id}>
                  {`${item.filename}${item.included ? '' : ' (excluded)'}`}
                </option>
              ))}
            </optgroup>
          ) : null}
        </select>
      </label>
      <label className="scope-control">
        <span className="visually-hidden">Date range</span>
        <IconSlot name="calendar" />
        <select id="scope-range" aria-label="Date range" value={rangeChoice} onChange={(event) => onRange(event.target.value as RangePreset)}>
          {RANGE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <div className="scope-custom" id="scope-custom" hidden={!showCustom}>
        <input className="input" id="scope-from" type="date" aria-label="From date" value={from} onChange={(event) => setFrom(event.target.value)} />
        <span className="muted">–</span>
        <input className="input" id="scope-to" type="date" aria-label="To date" value={to} onChange={(event) => setTo(event.target.value)} />
        <button className="btn btn-secondary btn-sm" id="scope-apply" type="button" onClick={apply}>
          Apply
        </button>
      </div>
    </div>
  );
}

function Page({ page, onNavigate }: { page: PageDef; onNavigate: () => void }) {
  useEffect(() => {
    document.title = `${page.title} · Ferlance`;
    onNavigate();
    window.scrollTo({ top: 0 });
  }, [page, onNavigate]);
  const { Component } = page;
  return (
    <section className={`view${page.sectionClass ? ` ${page.sectionClass}` : ''}`} data-view={page.name}>
      <PageErrorBoundary>
        <Suspense fallback={<SkeletonRows count={6} height={24} />}>
          <Component />
        </Suspense>
      </PageErrorBoundary>
    </section>
  );
}

/** Old-style `#page` anchors map onto the new paths. Initial /app#page URLs are rewritten in main.tsx. */
function useHashRedirect() {
  const navigate = useNavigate();
  const location = useLocation();
  useEffect(() => {
    const redirect = () => {
      if (window.location.hash.length > 1) navigate(pagePath(resolvePageName(window.location.hash)), { replace: true });
    };
    redirect();
    window.addEventListener('hashchange', redirect);
    return () => window.removeEventListener('hashchange', redirect);
  }, [navigate, location.key]);
}

/** `/app/<name>` (optionally with a trailing slash) renders that page; legacy names redirect, anything else goes to Overview. */
function PageRoute({ pathname, onNavigate }: { pathname: string; onNavigate: () => void }) {
  const match = /^\/app\/([^/]+)\/?$/.exec(pathname);
  if (!match) return <Redirect to={pagePath('overview')} />;
  let name: string;
  try {
    name = decodeURIComponent(match[1] ?? '');
  } catch {
    name = '';
  }
  const resolved = resolvePageName(name);
  if (name !== resolved) return <Redirect to={pagePath(resolved)} />;
  const page = PAGES.find((item) => item.name === resolved) as PageDef;
  return <Page key={page.name} page={page} onNavigate={onNavigate} />;
}

export function Shell() {
  const [navOpen, setNavOpen] = useState(false);
  const [actionsSlot, setActionsSlot] = useState<HTMLDivElement | null>(null);
  const location = useLocation();
  useHashRedirect();

  // Ignore a trailing slash: /app/products/ renders the same page as /app/products.
  const pathname = location.pathname.replace(/\/+$/, '');
  const current = PAGES.find((page) => pathname === pagePath(page.name));
  const closeNav = useCallback(() => setNavOpen(false), []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setNavOpen(false);
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);

  return (
    <div className={`shell${navOpen ? ' nav-open' : ''}`} id="shell">
      <Sidebar open={navOpen} onClose={closeNav} />
      <div className="main">
        <header className="topbar">
          <button
            className="btn btn-ghost btn-icon menu-btn"
            id="menu-btn"
            type="button"
            aria-label="Open navigation"
            aria-controls="sidebar"
            aria-expanded={navOpen}
            data-icon="menu"
            onClick={() => setNavOpen(true)}
          >
            <Icon name="menu" />
          </button>
          <div className="topbar-title">
            <h1 id="page-title">{current?.title ?? 'Overview'}</h1>
          </div>
          {/* Stays mounted (hidden) on unscoped pages: CSS right-aligns the actions via `.scope-bar[hidden] + .topbar-actions`. */}
          <ScopeBar hidden={!current?.scoped} />
          <div className="topbar-actions" id="topbar-actions" ref={setActionsSlot} />
        </header>
        <main className="content" id="content">
          <p className="page-description" id="page-description">
            {current?.description ?? ''}
          </p>
          <ActionsSlotContext.Provider value={actionsSlot}>
            <PageRoute pathname={location.pathname} onNavigate={closeNav} />
          </ActionsSlotContext.Provider>
        </main>
      </div>
      {pathname === pagePath('help') ? null : <WelcomeTour />}
    </div>
  );
}
