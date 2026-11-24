// Small building blocks shared by every screen, in the Ferlance colours (light and dark).

import { createContext, useContext, type ReactNode } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  useColorScheme,
  type TextInputProps,
} from 'react-native';

const LIGHT = {
  bg: '#f6f7f7',
  surface: '#ffffff',
  muted: '#eef1f0',
  text: '#0f1c1b',
  sub: '#5b6766',
  border: '#dde3e2',
  accent: '#1f8a66',
  accentText: '#ffffff',
  danger: '#b42318',
  good: '#1f8a66',
};
const DARK: typeof LIGHT = {
  bg: '#0f0f11',
  surface: '#1a1a1d',
  muted: '#242428',
  text: '#f1f1f3',
  sub: '#a3a3ab',
  border: '#2e2e33',
  accent: '#7af0c2',
  accentText: '#0a1514',
  danger: '#ff8a80',
  good: '#7af0c2',
};
export type Palette = typeof LIGHT;

const ThemeContext = createContext<Palette>(LIGHT);
export function ThemeProvider({ children }: { children: ReactNode }) {
  const scheme = useColorScheme();
  return <ThemeContext.Provider value={scheme === 'dark' ? DARK : LIGHT}>{children}</ThemeContext.Provider>;
}
export const useTheme = (): Palette => useContext(ThemeContext);

export function Screen({ children, scroll = true }: { children: ReactNode; scroll?: boolean }) {
  const c = useTheme();
  if (!scroll) return <View style={[styles.screen, { backgroundColor: c.bg }]}>{children}</View>;
  return (
    <ScrollView style={{ backgroundColor: c.bg }} contentContainerStyle={styles.screen} keyboardShouldPersistTaps="handled">
      {children}
    </ScrollView>
  );
}

export function Title({ children, sub }: { children: ReactNode; sub?: ReactNode }) {
  const c = useTheme();
  return (
    <View style={{ gap: 4 }}>
      <Text accessibilityRole="header" style={[styles.title, { color: c.text }]}>
        {children}
      </Text>
      {sub ? <Text style={{ color: c.sub, fontSize: 15, lineHeight: 21 }}>{sub}</Text> : null}
    </View>
  );
}

export function Body({ children, muted = false, style }: { children: ReactNode; muted?: boolean; style?: object }) {
  const c = useTheme();
  return <Text style={[{ color: muted ? c.sub : c.text, fontSize: 15, lineHeight: 22 }, style]}>{children}</Text>;
}

export function Card({ children, title }: { children: ReactNode; title?: string }) {
  const c = useTheme();
  return (
    <View style={[styles.card, { backgroundColor: c.surface, borderColor: c.border }]}>
      {title ? <Text style={{ color: c.text, fontWeight: '600', fontSize: 16 }}>{title}</Text> : null}
      {children}
    </View>
  );
}

export function Button({
  label,
  onPress,
  kind = 'primary',
  busy = false,
  disabled = false,
}: {
  label: string;
  onPress: () => void;
  kind?: 'primary' | 'secondary' | 'ghost';
  busy?: boolean;
  disabled?: boolean;
}) {
  const c = useTheme();
  const primary = kind === 'primary';
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: disabled || busy, busy }}
      disabled={disabled || busy}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        {
          backgroundColor: primary ? c.accent : kind === 'secondary' ? c.muted : 'transparent',
          opacity: disabled ? 0.5 : pressed ? 0.8 : 1,
        },
      ]}
    >
      {busy ? (
        <ActivityIndicator color={primary ? c.accentText : c.text} />
      ) : (
        <Text style={{ color: primary ? c.accentText : c.text, fontWeight: '600', fontSize: 15 }}>{label}</Text>
      )}
    </Pressable>
  );
}

export function Field({ label, ...props }: TextInputProps & { label: string }) {
  const c = useTheme();
  return (
    <View style={{ gap: 6 }}>
      <Text style={{ color: c.sub, fontSize: 14 }}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        placeholderTextColor={c.sub}
        {...props}
        style={[
          styles.input,
          { color: c.text, backgroundColor: c.surface, borderColor: c.border },
          props.multiline ? { minHeight: 120, textAlignVertical: 'top' } : null,
        ]}
      />
    </View>
  );
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: [T, string][];
  onChange: (value: T) => void;
}) {
  const c = useTheme();
  return (
    <View style={[styles.segmented, { backgroundColor: c.muted }]} accessibilityRole="tablist">
      {options.map(([key, label]) => (
        <Pressable
          key={key}
          accessibilityRole="tab"
          accessibilityState={{ selected: key === value }}
          onPress={() => onChange(key)}
          style={[styles.segment, key === value ? { backgroundColor: c.surface } : null]}
        >
          <Text style={{ color: key === value ? c.text : c.sub, fontWeight: key === value ? '600' : '400' }}>{label}</Text>
        </Pressable>
      ))}
    </View>
  );
}

export function Kpi({ label, value, note }: { label: string; value: string; note?: string }) {
  const c = useTheme();
  return (
    <View style={[styles.kpi, { backgroundColor: c.surface, borderColor: c.border }]}>
      <Text style={{ color: c.sub, fontSize: 13 }}>{label}</Text>
      <Text style={{ color: c.text, fontSize: 20, fontWeight: '700' }} numberOfLines={1} adjustsFontSizeToFit>
        {value}
      </Text>
      {note ? <Text style={{ color: c.sub, fontSize: 12 }}>{note}</Text> : null}
    </View>
  );
}

export function Notice({ text, error = false }: { text: string; error?: boolean }) {
  const c = useTheme();
  return (
    <Text accessibilityLiveRegion="polite" style={{ color: error ? c.danger : c.sub, fontSize: 14, lineHeight: 20 }}>
      {text}
    </Text>
  );
}

export function Loading() {
  const c = useTheme();
  return <ActivityIndicator style={{ marginTop: 32 }} color={c.accent} />;
}

const styles = StyleSheet.create({
  screen: { padding: 16, gap: 16, paddingBottom: 40, flexGrow: 1 },
  title: { fontSize: 24, fontWeight: '700' },
  card: { borderWidth: 1, borderRadius: 14, padding: 16, gap: 12 },
  button: { minHeight: 48, borderRadius: 12, paddingHorizontal: 18, alignItems: 'center', justifyContent: 'center' },
  input: { borderWidth: 1, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 12, fontSize: 16 },
  segmented: { flexDirection: 'row', borderRadius: 12, padding: 4, gap: 4 },
  segment: { flex: 1, minHeight: 40, borderRadius: 9, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 6 },
  kpi: { flexBasis: '47%', flexGrow: 1, borderWidth: 1, borderRadius: 14, padding: 14, gap: 4 },
});
