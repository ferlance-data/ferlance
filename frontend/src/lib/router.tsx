// Minimal client-side router for the workspace. It replaces react-router, which was
// about 12% of the first-load JavaScript, for the handful of features the app uses:
// history navigation, links, active nav links and a redirect.
//
// Navigations run inside startTransition. A page whose lazy chunk is still loading
// keeps the current page on screen instead of flashing the Suspense fallback.

import {
  createContext,
  startTransition,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type AnchorHTMLAttributes,
  type MouseEvent,
  type ReactNode,
} from 'react';

export interface Location {
  pathname: string;
  search: string;
  hash: string;
  /** Changes on every navigation, including to the same URL. */
  key: number;
}

export type Navigate = (to: string, options?: { replace?: boolean }) => void;

interface RouterValue {
  location: Location;
  navigate: Navigate;
}

const RouterContext = createContext<RouterValue | null>(null);

let nextKey = 0;
const readLocation = (): Location => ({
  pathname: window.location.pathname,
  search: window.location.search,
  hash: window.location.hash,
  key: nextKey++,
});

export function Router({ children }: { children: ReactNode }) {
  const [location, setLocation] = useState(readLocation);

  useEffect(() => {
    const onPop = () => startTransition(() => setLocation(readLocation()));
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  const navigate = useCallback<Navigate>((to, { replace = false } = {}) => {
    const url = new URL(to, window.location.href);
    if (url.origin !== window.location.origin) {
      window.location.assign(url.href);
      return;
    }
    const target = url.pathname + url.search + url.hash;
    window.history[replace ? 'replaceState' : 'pushState'](null, '', target);
    startTransition(() => setLocation(readLocation()));
  }, []);

  const value = useMemo(() => ({ location, navigate }), [location, navigate]);
  return <RouterContext.Provider value={value}>{children}</RouterContext.Provider>;
}

function useRouter(): RouterValue {
  const value = useContext(RouterContext);
  if (!value) throw new Error('Router hooks must be used inside <Router>');
  return value;
}

export const useLocation = (): Location => useRouter().location;
export const useNavigate = (): Navigate => useRouter().navigate;

/** Plain left clicks are handled in-app; modified, middle-button and new-target clicks keep browser behaviour. */
function isAppClick(event: MouseEvent<HTMLAnchorElement>): boolean {
  const target = event.currentTarget.getAttribute('target');
  return (
    !event.defaultPrevented &&
    event.button === 0 &&
    !event.metaKey &&
    !event.ctrlKey &&
    !event.shiftKey &&
    !event.altKey &&
    (!target || target === '_self') &&
    !event.currentTarget.hasAttribute('download')
  );
}

export interface LinkProps extends Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href'> {
  to: string;
  replace?: boolean;
}

export function Link({ to, replace, onClick, ...rest }: LinkProps) {
  const navigate = useNavigate();
  return (
    <a
      {...rest}
      href={to}
      onClick={(event) => {
        onClick?.(event);
        if (!isAppClick(event)) return;
        event.preventDefault();
        navigate(to, { replace });
      }}
    />
  );
}

const trimSlash = (path: string) => path.replace(/\/+$/, '') || '/';

/** A link that marks itself `aria-current="page"` when its path is the current one. */
export function NavLink(props: LinkProps) {
  const { pathname } = useLocation();
  const active = trimSlash(pathname) === trimSlash(new URL(props.to, window.location.href).pathname);
  return <Link aria-current={active ? 'page' : undefined} {...props} />;
}

/** Redirect on render, like react-router's <Navigate>. */
export function Redirect({ to, replace = true }: { to: string; replace?: boolean }) {
  const navigate = useNavigate();
  useEffect(() => navigate(to, { replace }), [navigate, to, replace]);
  return null;
}
