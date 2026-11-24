// Getting records in from the phone: paste MoMo messages, or photograph / type a notebook page,
// check every line, then add it.

import * as ImagePicker from 'expo-image-picker';
import { useState } from 'react';
import { Switch, View } from 'react-native';
import { isoDate, money } from '../../../frontend/src/lib/format';
import { request } from '../api';
import { useSession } from '../session';
import { Body, Button, Card, Field, Notice, Screen, Segmented, Title, useTheme } from '../ui';

type Mode = 'momo' | 'page';
type PageType = 'sales' | 'debts' | 'expenses';

interface PageLine {
  include: boolean;
  date: string | null;
  description: string;
  customer: string | null;
  quantity: number | null;
  amount: number | null;
  confidence: number;
  notes: string[];
}

interface Draft {
  id: string;
  type: PageType;
  date: string | null;
  source: 'vision' | 'text';
  lines: PageLine[];
}

const TYPES: [PageType, string][] = [
  ['sales', 'Sales'],
  ['debts', 'Debtors'],
  ['expenses', 'Spending'],
];

function MoMo() {
  const { path } = useSession();
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);

  const send = async () => {
    if (!text.trim()) return;
    setBusy(true);
    setResult(null);
    try {
      const done = await request<{ transactions_count: number; total_amount: number }>(path('/sources/momo'), { body: { sms_text: text } });
      setResult({
        ok: true,
        text: `Added ${done.transactions_count} Mobile Money transaction${done.transactions_count === 1 ? '' : 's'} (${money(done.total_amount)}).`,
      });
      setText('');
    } catch (failure) {
      setResult({ ok: false, text: failure instanceof Error ? failure.message : 'Could not read those messages.' });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="Paste MoMo messages">
      <Body muted>
        Copy one or more MTN, Telecel or AT Money messages from your SMS app and paste them here. Each is checked; duplicates are flagged.
      </Body>
      <Field label="Messages" value={text} onChangeText={setText} multiline placeholder="Payment received for GHS 50.00 from …" />
      {result ? <Notice text={result.text} error={!result.ok} /> : null}
      <Button label="Add messages" onPress={() => void send()} busy={busy} disabled={!text.trim()} />
    </Card>
  );
}

function Review({ draft, onDone }: { draft: Draft; onDone: (message: string) => void }) {
  const { path } = useSession();
  const c = useTheme();
  // Like the website: every line with an amount starts ticked.
  const [lines, setLines] = useState(() => draft.lines.map((line) => ({ ...line, include: line.amount !== null })));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const kept = lines.filter((line) => line.include);
  const total = kept.reduce((sum, line) => sum + (line.amount ?? 0), 0);

  const confirm = async () => {
    setBusy(true);
    setError('');
    try {
      await request(path(`/pages/${encodeURIComponent(draft.id)}/confirm`), {
        body: {
          page_type: draft.type,
          page_date: draft.date ?? isoDate(new Date()),
          lines: lines.map(({ include, date, description, customer, quantity, amount }) => ({
            include,
            date,
            description,
            customer,
            quantity,
            amount,
          })),
        },
      });
      onDone(`Added ${kept.length} line${kept.length === 1 ? '' : 's'} (${money(total)}).`);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Could not add the page.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="Check each line">
      <Body muted>Untick anything that should not be added. Lines marked ⚠ were hard to read.</Body>
      {lines.map((line, index) => (
        <View
          key={index}
          style={{ flexDirection: 'row', alignItems: 'center', gap: 10, borderTopWidth: 1, borderColor: c.border, paddingTop: 10 }}
        >
          <Switch
            accessibilityLabel={`Include ${line.description || 'line'}`}
            value={line.include}
            onValueChange={(include) => setLines(lines.map((other, at) => (at === index ? { ...other, include } : other)))}
          />
          <View style={{ flex: 1 }}>
            <Body>
              {line.confidence < 0.7 ? '⚠ ' : ''}
              {[line.customer, line.description].filter(Boolean).join(' — ') || 'No description'}
            </Body>
            {line.quantity ? <Body muted>Qty {line.quantity}</Body> : null}
          </View>
          <Body style={{ fontWeight: '600' }}>{line.amount === null ? '—' : money(line.amount)}</Body>
        </View>
      ))}
      <Body style={{ fontWeight: '600' }}>Total to add: {money(total)}</Body>
      {error ? <Notice text={error} error /> : null}
      <Button
        label={`Add ${kept.length} line${kept.length === 1 ? '' : 's'}`}
        onPress={() => void confirm()}
        busy={busy}
        disabled={!kept.length}
      />
      <Button label="Start again" kind="ghost" onPress={() => onDone('')} />
    </Card>
  );
}

function Notebook() {
  const { path } = useSession();
  const [type, setType] = useState<PageType>('sales');
  const [text, setText] = useState('');
  const [busy, setBusy] = useState<'photo' | 'text' | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const fail = (failure: unknown, fallback: string) =>
    setMessage({ ok: false, text: failure instanceof Error ? failure.message : fallback });

  const photo = async (camera: boolean) => {
    setMessage(null);
    const permission = camera ? await ImagePicker.requestCameraPermissionsAsync() : await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      setMessage({
        ok: false,
        text: camera
          ? 'Ferlance needs the camera to photograph a page. You can allow it in your phone settings, or type the page instead.'
          : 'Allow access to photos to pick a page.',
      });
      return;
    }
    const options: ImagePicker.ImagePickerOptions = { mediaTypes: ['images'], quality: 0.7 };
    const picked = camera ? await ImagePicker.launchCameraAsync(options) : await ImagePicker.launchImageLibraryAsync(options);
    const asset = picked.canceled ? null : picked.assets[0];
    if (!asset) return;
    setBusy('photo');
    try {
      const form = new FormData();
      // React Native's FormData takes a { uri, name, type } file description.
      form.append('file', { uri: asset.uri, name: asset.fileName ?? 'page.jpg', type: asset.mimeType ?? 'image/jpeg' } as unknown as Blob);
      setDraft(await request<Draft>(path('/pages'), { body: form }));
    } catch (failure) {
      fail(failure, 'Could not read the photo.');
    } finally {
      setBusy(null);
    }
  };

  const typed = async () => {
    if (!text.trim()) return;
    setMessage(null);
    setBusy('text');
    try {
      setDraft(await request<Draft>(path('/pages/text'), { body: { text, page_type: type } }));
    } catch (failure) {
      fail(failure, 'Could not read the page.');
    } finally {
      setBusy(null);
    }
  };

  if (draft) {
    return (
      <Review
        draft={draft}
        onDone={(done) => {
          setDraft(null);
          if (done) {
            setText('');
            setMessage({ ok: true, text: done });
          }
        }}
      />
    );
  }

  return (
    <Card title="Add a notebook page">
      <Body muted>
        Photograph a page of your exercise book (read by AI, counts towards today's AI limit) or type the lines for free. You check every
        line before it is added.
      </Body>
      <Segmented value={type} options={TYPES} onChange={setType} />
      <Button label="Take a photo" onPress={() => void photo(true)} busy={busy === 'photo'} disabled={busy !== null} />
      <Button label="Pick a photo" kind="secondary" onPress={() => void photo(false)} disabled={busy !== null} />
      <Field
        label="Or type the lines, one per line"
        value={text}
        onChangeText={setText}
        multiline
        placeholder={type === 'debts' ? 'Akosua - 2 bags rice - 190' : type === 'expenses' ? 'Shop rent 500' : 'Rice 5kg 2 190'}
      />
      <Button
        label="Read typed lines"
        kind="secondary"
        onPress={() => void typed()}
        busy={busy === 'text'}
        disabled={!text.trim() || busy !== null}
      />
      {message ? <Notice text={message.text} error={!message.ok} /> : null}
    </Card>
  );
}

export default function Record() {
  const { canWrite } = useSession();
  const [mode, setMode] = useState<Mode>('momo');
  return (
    <Screen>
      <Title sub="Bring today's records in. Nothing is added until you confirm it.">Record</Title>
      {canWrite ? (
        <>
          <Segmented
            value={mode}
            options={[
              ['momo', 'MoMo messages'],
              ['page', 'Notebook page'],
            ]}
            onChange={setMode}
          />
          {mode === 'momo' ? <MoMo /> : <Notebook />}
        </>
      ) : (
        <Notice text="Your role can read the books but not add records. Ask the owner if you need to." />
      )}
    </Screen>
  );
}
