// The debt book: the notebook by the till, made quick. Who owes the business, whom it owes,
// part-payments, ageing, reminders sent from the owner's own WhatsApp or SMS, and MoMo matches.

import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { request } from '../../lib/api';
import { formatDate, isoDate, money } from '../../lib/format';
import { toast } from '../../lib/toast';
import { EmptyState, Kpi, Pill, ReadOnlyNotice, Segmented, SkeletonRows, StatusText } from '../components/ui';
import { PageActions } from '../page';
import { keys, useWorkspace } from '../workspace';
import {
  BUCKET_LABEL,
  METHOD_LABEL,
  overdue,
  reminderText,
  smsLink,
  whatsappLink,
  type Debt,
  type DebtBook,
  type Direction,
  type Language,
  type MomoMatch,
} from './debts.logic';

const SIDE: Record<Direction, { title: string; who: string; empty: string }> = {
  owed_to_us: { title: 'Customers owe you', who: 'Customer', empty: 'Nobody owes you right now.' },
  we_owe: { title: 'You owe', who: 'Supplier', empty: 'You owe nobody right now.' },
};
const BASIS: Record<Direction, { value: string; label: string }[]> = {
  owed_to_us: [
    { value: 'new_sale', label: 'A sale on credit (not in my imports)' },
    { value: 'recorded_sale', label: 'A sale already in my imports' },
  ],
  we_owe: [
    { value: 'recorded_purchase', label: 'Stock already in my stock records' },
    { value: 'expense', label: 'Something else (rent, transport…)' },
  ],
};
const BUCKET_TONE = { not_due: '', '1_30': 'warning', '31_60': 'warning', '61_90': 'error', over_90: 'error' } as const;

function AddDebt({ side, book, onDone }: { side: Direction; book: DebtBook; onDone: () => Promise<void> }) {
  const { businessPath } = useWorkspace();
  const today = isoDate(new Date());
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [amount, setAmount] = useState('');
  const [basis, setBasis] = useState(BASIS[side][0]!.value);
  const [description, setDescription] = useState('');
  const [issued, setIssued] = useState(today);
  const [due, setDue] = useState('');
  const [status, setStatus] = useState<{ message: string; error: boolean } | null>(null);
  const [saving, setSaving] = useState(false);
  const kind = side === 'owed_to_us' ? 'customer' : 'supplier';
  const known = book.parties.filter((party) => party.kind === kind);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    try {
      await request(businessPath('/debts'), {
        method: 'POST',
        json: {
          direction: side,
          party_name: name,
          phone,
          amount: Number(amount),
          basis,
          description,
          issued_on: issued,
          due_on: due || null,
        },
      });
      toast(`Recorded ${money(Number(amount), { code: book.currency })} for ${name}.`);
      setName('');
      setPhone('');
      setAmount('');
      setDescription('');
      setDue('');
      setStatus(null);
      await onDone();
    } catch (error) {
      setStatus({ message: (error as Error).message, error: true });
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className="card" id="debt-add" onSubmit={(event) => void submit(event)}>
      <div className="card-header">
        <div>
          <h2 className="card-title">{side === 'owed_to_us' ? 'Someone took goods on credit' : 'You took goods on credit'}</h2>
          <p className="card-subtitle">Name and amount are enough. It goes into your books too.</p>
        </div>
      </div>
      <div className="card-body form-grid">
        <label className="field">
          {SIDE[side].who}
          <input
            className="input"
            required
            maxLength={120}
            list={`debt-parties-${side}`}
            value={name}
            onChange={(event) => {
              setName(event.target.value);
              const match = known.find((party) => party.name.toLowerCase() === event.target.value.trim().toLowerCase());
              if (match?.phone) setPhone(match.phone);
            }}
          />
          <datalist id={`debt-parties-${side}`}>
            {known.map((party) => (
              <option key={party.id} value={party.name} />
            ))}
          </datalist>
        </label>
        <label className="field">
          Amount
          <input className="input" required inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} />
        </label>
        <label className="field">
          Phone (for reminders)
          <input
            className="input"
            type="tel"
            inputMode="tel"
            maxLength={30}
            value={phone}
            onChange={(event) => setPhone(event.target.value)}
          />
        </label>
        <label className="field">
          What for
          <select className="select" value={basis} onChange={(event) => setBasis(event.target.value)}>
            {BASIS[side].map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          Note (optional)
          <input
            className="input"
            maxLength={300}
            placeholder="e.g. 2 bags rice"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </label>
        <label className="field">
          Date
          <input className="input" type="date" required max={today} value={issued} onChange={(event) => setIssued(event.target.value)} />
        </label>
        <label className="field">
          Pay by (optional)
          <input className="input" type="date" min={issued} value={due} onChange={(event) => setDue(event.target.value)} />
        </label>
        <div className="button-row">
          <button className="btn btn-primary" type="submit" disabled={saving}>
            Record debt
          </button>
          <StatusText message={status?.message} error={status?.error} />
        </div>
      </div>
    </form>
  );
}

function DebtCard({ debt, book, editable, onDone }: { debt: Debt; book: DebtBook; editable: boolean; onDone: () => Promise<void> }) {
  const { businessPath } = useWorkspace();
  const [mode, setMode] = useState<'none' | 'pay' | 'remind'>('none');
  const [amount, setAmount] = useState(String(debt.balance));
  const [method, setMethod] = useState('cash');
  const [paidOn, setPaidOn] = useState(isoDate(new Date()));
  const [withhold, setWithhold] = useState('');
  const [language, setLanguage] = useState<Language>('en');
  const [status, setStatus] = useState<{ message: string; error: boolean } | null>(null);
  const balance = money(debt.balance, { code: debt.currency });
  const text = reminderText(debt, book, balance, language);

  async function pay(event: FormEvent) {
    event.preventDefault();
    try {
      await request(businessPath(`/debts/${debt.id}/payments`), {
        method: 'POST',
        json: { amount: Number(amount), method, paid_on: paidOn, withhold: withhold || null },
      });
      toast(debt.direction === 'we_owe' ? `Payment to ${debt.party_name} recorded.` : `Payment from ${debt.party_name} recorded.`);
      setMode('none');
      await onDone();
    } catch (error) {
      setStatus({ message: (error as Error).message, error: true });
    }
  }

  async function voidDebt() {
    if (!window.confirm(`Void this debt for ${debt.party_name}? Its payments are voided too. It stays in the history, marked void.`))
      return;
    try {
      await request(businessPath(`/debts/${debt.id}/void`), { method: 'POST' });
      await onDone();
    } catch (error) {
      toast((error as Error).message, { error: true });
    }
  }

  return (
    <li className="debt-card">
      <div className="debt-head">
        <div className="file-cell">
          <strong>{debt.party_name}</strong>
          <small>{`${debt.description ? `${debt.description} · ` : ''}since ${formatDate(debt.issued_on)}${debt.due_on ? ` · pay by ${formatDate(debt.due_on)}` : ''}`}</small>
        </div>
        <div className="debt-amount">
          <span className="num">{balance}</span>
          {debt.status === 'open' && debt.age ? (
            <Pill tone={BUCKET_TONE[debt.age]}>{BUCKET_LABEL[debt.age]}</Pill>
          ) : (
            <Pill tone={debt.status === 'settled' ? 'success' : ''}>{debt.status === 'settled' ? 'Paid' : 'Void'}</Pill>
          )}
        </div>
      </div>
      {debt.paid ? (
        <small className="muted">{`${money(debt.paid, { code: debt.currency })} paid of ${money(debt.amount, { code: debt.currency })}`}</small>
      ) : null}
      {debt.status === 'open' ? (
        <div className="button-row">
          {editable ? (
            <button
              className="btn btn-secondary btn-sm"
              type="button"
              aria-expanded={mode === 'pay'}
              onClick={() => {
                setAmount(String(debt.balance));
                setStatus(null);
                setMode(mode === 'pay' ? 'none' : 'pay');
              }}
            >
              Record payment
            </button>
          ) : null}
          {debt.direction === 'owed_to_us' ? (
            <button
              className="btn btn-ghost btn-sm"
              type="button"
              aria-expanded={mode === 'remind'}
              onClick={() => setMode(mode === 'remind' ? 'none' : 'remind')}
            >
              Remind
            </button>
          ) : null}
          {editable ? (
            <button className="btn btn-ghost btn-sm" type="button" onClick={() => void voidDebt()}>
              Void
            </button>
          ) : null}
        </div>
      ) : null}
      {mode === 'pay' ? (
        <form className="form-grid debt-pay" onSubmit={(event) => void pay(event)}>
          <label className="field">
            Amount
            <input className="input" required inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} />
          </label>
          <label className="field">
            Paid by
            <select className="select" value={method} onChange={(event) => setMethod(event.target.value)}>
              {['cash', 'momo_mtn', 'momo_telecel', 'momo_at', 'bank'].map((key) => (
                <option key={key} value={key}>
                  {METHOD_LABEL[key]}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            Date
            <input
              className="input"
              type="date"
              required
              min={debt.issued_on}
              value={paidOn}
              onChange={(event) => setPaidOn(event.target.value)}
            />
          </label>
          {debt.direction === 'we_owe' ? (
            <label className="field">
              Withholding tax
              <select className="select" value={withhold} onChange={(event) => setWithhold(event.target.value)}>
                <option value="">None</option>
                <option value="goods">Goods (3%)</option>
                <option value="works">Works (5%)</option>
                <option value="services">Services (7.5%)</option>
                <option value="non_resident">Non-resident supplier (20%)</option>
              </select>
              <span className="field-hint">Kept back for GRA; the supplier gets the rest. Rates need your accountant's check (Tax &amp; payroll).</span>
            </label>
          ) : null}
          <div className="button-row">
            <button className="btn btn-primary btn-sm" type="submit">
              Save payment
            </button>
            <StatusText message={status?.message} error={status?.error} />
          </div>
        </form>
      ) : null}
      {mode === 'remind' ? (
        <div className="debt-remind">
          <Segmented
            label="Reminder language"
            value={language}
            onChange={setLanguage}
            options={[
              { value: 'en', label: 'English' },
              { value: 'tw', label: 'Twi' },
            ]}
          />
          <p className="body-sm debt-message">{text}</p>
          <div className="button-row">
            <a className="btn btn-primary btn-sm" href={whatsappLink(debt.phone, text)} target="_blank" rel="noopener noreferrer">
              Send on WhatsApp
            </a>
            <a className="btn btn-secondary btn-sm" href={smsLink(debt.phone, text)}>
              Send by SMS
            </a>
          </div>
          {!debt.phone ? <p className="footnote">No phone number saved for this customer, so you will pick the contact yourself.</p> : null}
          {language === 'tw' ? <p className="footnote">Twi wording is a first draft. You can change it before sending.</p> : null}
        </div>
      ) : null}
      {debt.payments.length ? (
        <ul className="debt-payments">
          {debt.payments.map((payment) => (
            <li key={payment.id} className={payment.voided || payment.on_hold ? 'muted' : ''}>
              {`${formatDate(payment.paid_on)} · ${money(payment.amount, { code: debt.currency })} · ${METHOD_LABEL[payment.method] ?? payment.method}${payment.voided ? ' · void' : payment.on_hold ? ' · on hold: its MoMo import is left out' : ''}`}
            </li>
          ))}
        </ul>
      ) : null}
    </li>
  );
}

export default function Debts() {
  const { business, businessPath, can } = useWorkspace();
  const queryClient = useQueryClient();
  const editable = can('write_data');
  const [side, setSide] = useState<Direction>('owed_to_us');
  const [showClosed, setShowClosed] = useState(false);
  const [payTo, setPayTo] = useState<string | null>(null);
  const bookQuery = useQuery({
    queryKey: keys.business(business.id, 'debts'),
    queryFn: ({ signal }) => request<DebtBook>(businessPath('/debts'), { signal }),
  });
  const matches = useQuery({
    queryKey: keys.business(business.id, 'debts-matches'),
    queryFn: ({ signal }) => request<MomoMatch[]>(businessPath('/debts/suggestions'), { signal }),
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: keys.business(business.id) });
  const book = bookQuery.data;
  if (!book) return <SkeletonRows count={6} />;
  const code = book.currency;
  const listed = book.debts.filter((debt) => debt.direction === side && (showClosed || debt.status === 'open'));
  const totals = book.totals[side];

  async function confirmMatch(match: MomoMatch) {
    try {
      await request(businessPath(`/debts/${match.debt_id}/payments`), { method: 'POST', json: { momo_ref: match.momo_ref } });
      toast(`${match.party_name}'s MoMo payment recorded.`);
      await refresh();
    } catch (error) {
      toast((error as Error).message, { error: true });
    }
  }

  async function savePayTo(event: FormEvent) {
    event.preventDefault();
    try {
      await request(businessPath('/debts/settings'), { method: 'PUT', json: { pay_to: payTo ?? '' } });
      toast('Saved. Reminders will show where to pay.');
      setPayTo(null);
      await refresh();
    } catch (error) {
      toast((error as Error).message, { error: true });
    }
  }

  return (
    <>
      <PageActions>
        <Segmented
          id="debt-side"
          label="Debt book side"
          mode="tabs"
          value={side}
          onChange={setSide}
          options={[
            { value: 'owed_to_us', label: 'Owed to you' },
            { value: 'we_owe', label: 'You owe' },
          ]}
        />
      </PageActions>

      <div className="kpi-grid" id="debt-kpis">
        <Kpi
          label="Customers owe you"
          icon="users"
          value={money(book.totals.owed_to_us.total, { code })}
          foot={`${book.totals.owed_to_us.open} open`}
        />
        <Kpi label="Late" icon="alert" value={money(overdue(book.totals.owed_to_us.buckets), { code })} foot="Past the pay-by date" />
        <Kpi
          label="You owe suppliers"
          icon="receipt"
          value={money(book.totals.we_owe.total, { code })}
          foot={`${book.totals.we_owe.open} open`}
        />
      </div>

      {matches.data?.length && editable ? (
        <div className="card" id="debt-matches">
          <div className="card-header">
            <div>
              <h2 className="card-title">MoMo payments that may settle debts</h2>
              <p className="card-subtitle">From your MoMo messages. Check each one before you confirm.</p>
            </div>
          </div>
          <div className="card-body">
            <ul className="pending-invites">
              {matches.data.map((match) => (
                <li key={`${match.momo_ref}:${match.debt_id}`}>
                  <span>{`${match.from} sent ${money(match.amount, { code })} on ${formatDate(match.date)}: ${match.party_name} owes ${money(match.balance, { code })} (${match.reason})`}</span>
                  <button className="btn btn-secondary btn-sm" type="button" onClick={() => void confirmMatch(match)}>
                    It's a payment
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </div>
      ) : null}

      {editable ? (
        <AddDebt key={side} side={side} book={book} onDone={refresh} />
      ) : (
        <ReadOnlyNotice role={business.role ?? 'accountant'} what="the debt book" />
      )}

      <div className="card" id="debt-list">
        <div className="card-header">
          <div>
            <h2 className="card-title">{SIDE[side].title}</h2>
            <p className="card-subtitle">
              {(Object.keys(BUCKET_LABEL) as (keyof typeof BUCKET_LABEL)[])
                .filter((key) => totals.buckets[key])
                .map((key) => `${BUCKET_LABEL[key]}: ${money(totals.buckets[key], { code })}`)
                .join(' · ') || 'Nothing open'}
            </p>
          </div>
          <label className="field field-inline">
            <input type="checkbox" checked={showClosed} onChange={(event) => setShowClosed(event.target.checked)} />
            Show paid and void
          </label>
        </div>
        {listed.length ? (
          <ul className="debt-list">
            {listed.map((debt) => (
              <DebtCard key={debt.id} debt={debt} book={book} editable={editable} onDone={refresh} />
            ))}
          </ul>
        ) : (
          <EmptyState title={SIDE[side].empty} />
        )}
      </div>

      {editable ? (
        <form className="card" id="debt-payto" onSubmit={(event) => void savePayTo(event)}>
          <div className="card-header">
            <div>
              <h2 className="card-title">Where customers pay you</h2>
              <p className="card-subtitle">Shown in reminders, e.g. "MTN MoMo 024 000 0000 (Ama Provisions)"</p>
            </div>
          </div>
          <div className="card-body form-grid">
            <label className="field">
              MoMo number and name
              <input className="input" maxLength={160} value={payTo ?? book.pay_to} onChange={(event) => setPayTo(event.target.value)} />
            </label>
            <div className="button-row">
              <button className="btn btn-secondary" type="submit" disabled={payTo === null}>
                Save
              </button>
            </div>
          </div>
        </form>
      ) : null}
    </>
  );
}
