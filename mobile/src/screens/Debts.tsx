// The debt book on the phone: who owes you, a new credit sale, record a payment, send a reminder.

import { useCallback, useEffect, useState } from 'react';
import { Linking, Modal, Pressable, RefreshControl, ScrollView, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { formatDate, isoDate, money } from '../../../frontend/src/lib/format';
import {
  BUCKET_LABEL,
  reminderText,
  smsLink,
  whatsappLink,
  type Debt,
  type DebtBook,
  type Direction,
} from '../../../frontend/src/app/views/debts.logic';
import { request } from '../api';
import { useSession } from '../session';
import { Body, Button, Card, Field, Loading, Notice, Screen, Segmented, Title, useTheme } from '../ui';

const SIDES: [Direction, string][] = [
  ['owed_to_us', 'Owed to you'],
  ['we_owe', 'You owe'],
];

function NewDebt({ direction, onDone }: { direction: Direction; onDone: (saved: boolean) => void }) {
  const { path } = useSession();
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [what, setWhat] = useState('');
  const [amount, setAmount] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const save = async () => {
    const value = Number(amount.replace(/,/g, ''));
    if (!name.trim() || !(value > 0)) {
      setError('A name and an amount are enough.');
      return;
    }
    setBusy(true);
    try {
      await request(path('/debts'), {
        body: {
          direction,
          party_name: name.trim(),
          phone: phone.trim(),
          description: what.trim(),
          amount: value,
          issued_on: isoDate(new Date()),
          basis: direction === 'owed_to_us' ? 'new_sale' : 'expense',
        },
      });
      onDone(true);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Could not save.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen>
      <Title sub={direction === 'owed_to_us' ? 'A customer takes goods now and pays later.' : 'You bought on credit from a supplier.'}>
        {direction === 'owed_to_us' ? 'New credit sale' : 'New supplier credit'}
      </Title>
      <Field label={direction === 'owed_to_us' ? 'Customer name' : 'Supplier name'} value={name} onChangeText={setName} />
      <Field label="Amount (GH₵)" value={amount} onChangeText={setAmount} keyboardType="decimal-pad" />
      <Field label="What for (optional)" value={what} onChangeText={setWhat} />
      <Field label="Phone, for reminders (optional)" value={phone} onChangeText={setPhone} keyboardType="phone-pad" />
      {error ? <Notice text={error} error /> : null}
      <Button label="Save" onPress={() => void save()} busy={busy} />
      <Button label="Cancel" kind="ghost" onPress={() => onDone(false)} />
    </Screen>
  );
}

function DebtRow({ debt, book, onChanged }: { debt: Debt; book: DebtBook; onChanged: () => void }) {
  const { path, canWrite } = useSession();
  const c = useTheme();
  const [open, setOpen] = useState(false);
  const [amount, setAmount] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const owing = money(debt.balance, { code: debt.currency });
  const message = reminderText(debt, book, owing, 'en');

  const pay = async () => {
    const value = amount ? Number(amount.replace(/,/g, '')) : null;
    if (value !== null && !(value > 0)) {
      setError('Enter the amount paid, or leave it empty for the full balance.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      await request(path(`/debts/${encodeURIComponent(debt.id)}/payments`), {
        body: { amount: value, paid_on: isoDate(new Date()), method: 'cash' },
      });
      setAmount('');
      setOpen(false);
      onChanged();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Could not record the payment.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={{ borderTopWidth: 1, borderColor: c.border, paddingTop: 12, gap: 8 }}>
      {/* Only the summary line toggles: taps on the form below must not fold the row away. */}
      <Pressable
        onPress={() => setOpen(!open)}
        accessibilityRole="button"
        accessibilityState={{ expanded: open }}
        style={{ flexDirection: 'row', justifyContent: 'space-between', gap: 8 }}
      >
        <View style={{ flex: 1 }}>
          <Body style={{ fontWeight: '600' }}>{debt.party_name}</Body>
          <Body muted>
            {[debt.description, formatDate(debt.issued_on), debt.age ? BUCKET_LABEL[debt.age] : null].filter(Boolean).join(' · ')}
          </Body>
        </View>
        <Body style={{ fontWeight: '700', color: debt.age && debt.age !== 'not_due' ? c.danger : c.text }}>{owing}</Body>
      </Pressable>
      {open ? (
        <View style={{ gap: 10 }}>
          {canWrite ? (
            <>
              <Field label="Amount paid (empty = all of it)" value={amount} onChangeText={setAmount} keyboardType="decimal-pad" />
              {error ? <Notice text={error} error /> : null}
              <Button label="Record payment" onPress={() => void pay()} busy={busy} />
            </>
          ) : null}
          {debt.direction === 'owed_to_us' ? (
            <View style={{ flexDirection: 'row', gap: 10 }}>
              <View style={{ flex: 1 }}>
                <Button
                  label="Remind on WhatsApp"
                  kind="secondary"
                  onPress={() => void Linking.openURL(whatsappLink(debt.phone, message))}
                />
              </View>
              <View style={{ flex: 1 }}>
                <Button label="Remind by SMS" kind="secondary" onPress={() => void Linking.openURL(smsLink(debt.phone, message))} />
              </View>
            </View>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

export default function Debts() {
  const { path, canWrite } = useSession();
  const c = useTheme();
  const [side, setSide] = useState<Direction>('owed_to_us');
  const [book, setBook] = useState<DebtBook | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setBook(await request<DebtBook>(path('/debts')));
      setError('');
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Could not load the debt book.');
    } finally {
      setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    void load();
  }, [load]);

  const open = book ? book.debts.filter((debt) => debt.direction === side && debt.status === 'open') : [];
  const total = book?.totals[side];

  return (
    <>
      <ScrollView
        style={{ backgroundColor: c.bg }}
        contentContainerStyle={{ padding: 16, gap: 16, paddingBottom: 40 }}
        refreshControl={<RefreshControl refreshing={loading && !!book} onRefresh={() => void load()} />}
      >
        <Title sub="Who owes you and whom you owe. Tap a name to record a payment or send a reminder.">Debt book</Title>
        <Segmented value={side} options={SIDES} onChange={setSide} />
        {canWrite ? (
          <Button label={side === 'owed_to_us' ? 'New credit sale' : 'New supplier credit'} onPress={() => setAdding(true)} />
        ) : null}
        {loading && !book ? <Loading /> : null}
        {error ? <Notice text={error} error /> : null}
        {book && total ? (
          <Card title={`${money(total.total, { code: book.currency })} · ${total.open} open`}>
            {open.length ? (
              open.map((debt) => <DebtRow key={debt.id} debt={debt} book={book} onChanged={() => void load()} />)
            ) : (
              <Body muted>{side === 'owed_to_us' ? 'Nobody owes you right now.' : 'You owe nobody right now.'}</Body>
            )}
          </Card>
        ) : null}
      </ScrollView>
      <Modal visible={adding} animationType="slide" onRequestClose={() => setAdding(false)}>
        <SafeAreaView style={{ flex: 1, backgroundColor: c.bg }}>
          <NewDebt
            direction={side}
            onDone={(saved) => {
              setAdding(false);
              if (saved) void load();
            }}
          />
        </SafeAreaView>
      </Modal>
    </>
  );
}
