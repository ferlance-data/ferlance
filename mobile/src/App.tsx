// Ferlance on the phone: sign in, then five tabs for the everyday jobs. Deeper work (invoices,
// stock, books, tax) stays on the website.

import { StatusBar } from 'expo-status-bar';
import { storage } from './storage';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import type { Business } from '../../frontend/src/lib/types';
import { ApiError, restore, setSignedOutHandler, signOut as endSession } from './api';
import Debts from './screens/Debts';
import Guides from './screens/Guides';
import Home from './screens/Home';
import Lance from './screens/Lance';
import Record from './screens/Record';
import SignIn from './screens/SignIn';
import { makeSession, SessionContext } from './session';
import { Body, Button, Loading, Notice, Screen, ThemeProvider, useTheme } from './ui';

type Tab = 'home' | 'debts' | 'record' | 'lance' | 'guides';
const TABS: [Tab, string][] = [
  ['home', 'Today'],
  ['debts', 'Debts'],
  ['record', 'Record'],
  ['lance', 'Lance'],
  ['guides', 'Guides'],
];
const SCREENS: Record<Tab, () => React.JSX.Element> = { home: Home, debts: Debts, record: Record, lance: Lance, guides: Guides };
/** Set once the guides have been offered on this phone (first sign-in opens them). */
const TOUR_KEY = 'ferlance.tour-seen';

type State =
  | { kind: 'loading' }
  | { kind: 'offline'; message: string }
  | { kind: 'signed-out'; message?: string }
  | { kind: 'no-business' }
  | { kind: 'in'; business: Business };

function TabBar({ tab, onChange }: { tab: Tab; onChange: (tab: Tab) => void }) {
  const c = useTheme();
  return (
    <View
      accessibilityRole="tablist"
      style={{ flexDirection: 'row', borderTopWidth: 1, borderColor: c.border, backgroundColor: c.surface }}
    >
      {TABS.map(([key, label]) => (
        <Pressable
          key={key}
          accessibilityRole="tab"
          accessibilityState={{ selected: key === tab }}
          onPress={() => onChange(key)}
          style={{ flex: 1, minHeight: 56, alignItems: 'center', justifyContent: 'center' }}
        >
          <View
            style={{ width: 24, height: 3, borderRadius: 2, marginBottom: 6, backgroundColor: key === tab ? c.accent : 'transparent' }}
          />
          <Text style={{ color: key === tab ? c.text : c.sub, fontWeight: key === tab ? '700' : '500', fontSize: 13 }}>{label}</Text>
        </Pressable>
      ))}
    </View>
  );
}

function Main() {
  const c = useTheme();
  const [state, setState] = useState<State>({ kind: 'loading' });
  const [tab, setTab] = useState<Tab>('home');

  const enter = useCallback(async (business: Business | null) => {
    if (!business) {
      setState({ kind: 'no-business' });
      return;
    }
    const seen = await storage.getItemAsync(TOUR_KEY).catch(() => '1');
    if (!seen) {
      setTab('guides');
      await storage.setItemAsync(TOUR_KEY, '1').catch(() => undefined);
    }
    setState({ kind: 'in', business });
  }, []);

  const start = useCallback(async () => {
    setState({ kind: 'loading' });
    try {
      const business = await restore();
      if (business === undefined) setState({ kind: 'signed-out' });
      else await enter(business);
    } catch (error) {
      setState({ kind: 'offline', message: error instanceof ApiError ? error.message : 'Could not reach Ferlance.' });
    }
  }, [enter]);

  useEffect(() => {
    setSignedOutHandler(() => setState({ kind: 'signed-out', message: 'Your session has ended. Sign in again.' }));
    void start();
  }, [start]);

  const signOut = useCallback(() => {
    void endSession();
    setTab('home');
    setState({ kind: 'signed-out' });
  }, []);

  const session = useMemo(() => (state.kind === 'in' ? makeSession(state.business, signOut) : null), [state, signOut]);

  let content: React.JSX.Element;
  if (state.kind === 'loading') content = <Loading />;
  else if (state.kind === 'offline')
    content = (
      <Screen>
        <Notice text={state.message} error />
        <Button label="Try again" onPress={() => void start()} />
      </Screen>
    );
  else if (state.kind === 'signed-out') content = <SignIn message={state.message} onSignedIn={(business) => void enter(business)} />;
  else if (state.kind === 'no-business')
    content = (
      <Screen>
        <Body>
          This account is not part of a business yet. Open the invite link you were sent, or create a workspace on the Ferlance website.
        </Body>
        <Button label="Sign out" kind="secondary" onPress={signOut} />
      </Screen>
    );
  else {
    const Current = SCREENS[tab];
    content = (
      <SessionContext.Provider value={session}>
        <View style={{ flex: 1 }}>
          <Current />
        </View>
        <TabBar tab={tab} onChange={setTab} />
      </SessionContext.Provider>
    );
  }

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: c.bg }} edges={['top', 'left', 'right', 'bottom']}>
      {content}
    </SafeAreaView>
  );
}

export default function App() {
  return (
    <SafeAreaProvider>
      <ThemeProvider>
        <StatusBar style="auto" />
        <Main />
      </ThemeProvider>
    </SafeAreaProvider>
  );
}
