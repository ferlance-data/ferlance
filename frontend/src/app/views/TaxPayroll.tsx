// Tax & payroll: the GRA and SSNIT rules Ferlance uses (each to be checked by your accountant),
// what is owed for a period, and a small monthly payroll with payslips.

import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { request } from '../../lib/api';
import { formatDate, isoDate, money, safeHref } from '../../lib/format';
import { Icon } from '../../lib/icons';
import { toast } from '../../lib/toast';
import { DataTable, EmptyState, Notice, Pill, ReadOnlyNotice, Segmented, SkeletonRows, StatusText } from '../components/ui';
import { PageActions } from '../page';
import { keys, useWorkspace } from '../workspace';
import { METHOD_LABEL } from './debts.logic';
import { RULE_KEY_LABEL, type Employee, type PayrollRun, type RunDetail, type TaxRule, type TaxSummary } from './taxpayroll.logic';

function Rules({ editable }: { editable: boolean }) {
  const { business, businessPath } = useWorkspace();
  const queryClient = useQueryClient();
  const rules = useQuery({ queryKey: keys.business(business.id, 'tax-rules'), queryFn: ({ signal }) => request<TaxRule[]>(businessPath('/tax/rules'), { signal }) });
  async function toggle(rule: TaxRule) {
    try {
      await request(businessPath(`/tax/rules/${rule.id}/check`), { method: 'PUT', json: { checked: !rule.checked } });
      await queryClient.invalidateQueries({ queryKey: keys.business(business.id) });
    } catch (error) {
      toast((error as Error).message, { error: true });
    }
  }
  if (!rules.data) return <SkeletonRows count={4} />;
  const open = rules.data.filter((rule) => !rule.checked).length;
  return (
    <div className="card" id="tax-rules">
      <div className="card-header">
        <div>
          <h2 className="card-title">The rates Ferlance uses</h2>
          <p className="card-subtitle">Taken from GRA and SSNIT pages in November 2026. Each one dates when it applies and where it came from.</p>
        </div>
        {open ? <Pill tone="warning" icon="alert">{`${open} need your accountant's check`}</Pill> : <Pill tone="success" icon="check">All checked</Pill>}
      </div>
      <ul className="debt-list">
        {rules.data.map((rule) => (
          <li className="debt-card" key={rule.id}>
            <div className="debt-head">
              <div className="file-cell">
                <strong>{rule.label}</strong>
                <small>{`${RULE_KEY_LABEL[rule.key] ?? rule.key} · from ${formatDate(rule.from)}${rule.to ? ` to ${formatDate(rule.to)}` : ''}`}</small>
              </div>
              {rule.checked ? <Pill tone="success">{`Checked by ${rule.checked.checked_by ?? 'someone'}`}</Pill> : <Pill tone="warning">Needs accountant check</Pill>}
            </div>
            <small className="muted">{rule.notes}</small>
            <div className="button-row">
              {rule.sources.map((source) => (
                <a key={source.url} className="btn btn-ghost btn-sm" href={safeHref(source.url)} target="_blank" rel="noopener noreferrer">
                  {source.title}
                </a>
              ))}
              {editable ? (
                <button className="btn btn-secondary btn-sm" type="button" onClick={() => void toggle(rule)}>
                  {rule.checked ? 'Mark as not checked' : 'I have checked this'}
                </button>
              ) : null}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Summary() {
  const { business, businessPath } = useWorkspace();
  const today = new Date();
  const [from, setFrom] = useState(isoDate(new Date(today.getFullYear(), today.getMonth(), 1)));
  const [to, setTo] = useState(isoDate(today));
  const summary = useQuery({
    queryKey: keys.business(business.id, 'tax-summary', from, to),
    queryFn: ({ signal }) => request<TaxSummary>(businessPath(`/tax/summary?from=${from}&to=${to}`), { signal }),
    placeholderData: keepPreviousData,
  });
  const data = summary.data;
  return (
    <div className="card" id="tax-summary">
      <div className="card-header">
        <div>
          <h2 className="card-title">What is owed for the period</h2>
          <p className="card-subtitle">To help you file. Ferlance does not file with GRA or SSNIT.</p>
        </div>
      </div>
      <div className="toolbar toolbar-plain card-body">
        <label className="field field-inline">
          From
          <input className="input" type="date" value={from} max={to} onChange={(event) => setFrom(event.target.value)} />
        </label>
        <label className="field field-inline">
          To
          <input className="input" type="date" value={to} min={from} onChange={(event) => setTo(event.target.value)} />
        </label>
      </div>
      {data ? (
        <div className="card-body form-grid">
          {data.unchecked_rules.length ? (
            <Notice tone="warning" icon="alert">{`These figures use rates your accountant has not checked yet: ${data.unchecked_rules.join(', ')}.`}</Notice>
          ) : null}
          <ul className="pending-invites">
            {data.vat.map((item) => (
              <li key={item.name}>
                <span>{`${item.name} charged on invoices`}</span>
                <span className="num">{money(item.amount)}</span>
              </li>
            ))}
            {data.wht.map((item) => (
              <li key={item.kind}>
                <span>{`Withholding tax kept back (${item.kind.replace('_', '-')})`}</span>
                <span className="num">{money(item.amount)}</span>
              </li>
            ))}
            {data.payroll.map((item) => (
              <li key={item.month}>
                <span>{`${item.month}: PAYE ${money(item.paye)} · SSNIT ${money(item.ssnit_employee + item.ssnit_employer)}`}</span>
                <span className="num">{money(item.paye + item.ssnit_employee + item.ssnit_employer)}</span>
              </li>
            ))}
          </ul>
          {!data.vat.length && !data.wht.length && !data.payroll.length ? <p className="body-sm muted">Nothing owed to GRA or SSNIT in this period.</p> : null}
          <p className="footnote">{data.note}</p>
        </div>
      ) : (
        <SkeletonRows count={3} />
      )}
    </div>
  );
}

function Payroll() {
  const { business, businessPath } = useWorkspace();
  const queryClient = useQueryClient();
  const staff = useQuery({ queryKey: keys.business(business.id, 'employees'), queryFn: ({ signal }) => request<Employee[]>(businessPath('/payroll/employees'), { signal }) });
  const runs = useQuery({ queryKey: keys.business(business.id, 'payroll-runs'), queryFn: ({ signal }) => request<PayrollRun[]>(businessPath('/payroll/runs'), { signal }) });
  const [openRun, setOpenRun] = useState<string | null>(null);
  const detail = useQuery({
    queryKey: keys.business(business.id, 'payroll-run', openRun ?? ''),
    queryFn: ({ signal }) => request<RunDetail>(businessPath(`/payroll/runs/${openRun}`), { signal }),
    enabled: Boolean(openRun),
  });
  const [form, setForm] = useState({ name: '', basic: '', allowances: '', ssnit_number: '', tin: '' });
  const [month, setMonth] = useState(isoDate(new Date()).slice(0, 7));
  const [paidFrom, setPaidFrom] = useState('bank');
  const [paidOn, setPaidOn] = useState(isoDate(new Date()));
  const [status, setStatus] = useState<{ message: string; error: boolean } | null>(null);
  const refresh = () => queryClient.invalidateQueries({ queryKey: keys.business(business.id) });

  async function act(work: () => Promise<unknown>, done: string) {
    try {
      await work();
      toast(done);
      setStatus(null);
      await refresh();
    } catch (error) {
      setStatus({ message: (error as Error).message, error: true });
    }
  }

  async function payslip(lineId: string) {
    try {
      const blob = await request<Blob>(businessPath(`/payroll/runs/${openRun}/payslips/${lineId}`), { asBlob: true });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `payslip-${detail.data?.month ?? ''}.pdf`;
      link.click();
      URL.revokeObjectURL(link.href);
    } catch (error) {
      toast((error as Error).message, { error: true });
    }
  }

  return (
    <>
      <form
        className="card"
        id="payroll-staff"
        onSubmit={(event: FormEvent) => {
          event.preventDefault();
          void act(
            () => request(businessPath('/payroll/employees'), { method: 'POST', json: { ...form, basic: Number(form.basic), allowances: Number(form.allowances || 0) } }),
            `${form.name} added.`,
          ).then(() => setForm({ name: '', basic: '', allowances: '', ssnit_number: '', tin: '' }));
        }}
      >
        <div className="card-header">
          <div>
            <h2 className="card-title">Staff</h2>
            <p className="card-subtitle">Monthly basic salary and cash allowances. Only owners and accountants can see this.</p>
          </div>
        </div>
        <div className="table-wrap">
          <DataTable
            columns={[
              { label: 'Name', value: (item: Employee) => item.name },
              { label: 'Basic', num: true, value: (item: Employee) => money(item.basic) },
              { label: 'Allowances', num: true, value: (item: Employee) => money(item.allowances) },
            ]}
            rows={staff.data ?? []}
            rowKey={(item) => item.id}
            empty="No staff yet."
          />
        </div>
        <div className="card-body form-grid">
          <label className="field">
            Name
            <input className="input" required maxLength={120} value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
          </label>
          <label className="field">
            Basic salary (monthly)
            <input className="input" required inputMode="decimal" value={form.basic} onChange={(event) => setForm({ ...form, basic: event.target.value })} />
          </label>
          <label className="field">
            Allowances (monthly)
            <input className="input" inputMode="decimal" value={form.allowances} onChange={(event) => setForm({ ...form, allowances: event.target.value })} />
          </label>
          <label className="field">
            SSNIT number (optional)
            <input className="input" maxLength={30} value={form.ssnit_number} onChange={(event) => setForm({ ...form, ssnit_number: event.target.value })} />
          </label>
          <div className="button-row">
            <button className="btn btn-secondary" type="submit">
              Add staff
            </button>
          </div>
        </div>
      </form>

      <div className="card" id="payroll-runs">
        <div className="card-header">
          <div>
            <h2 className="card-title">Monthly payroll</h2>
            <p className="card-subtitle">A draft until you post it. Posting books wages, pays the net out of the account you choose, and records what is owed to GRA and SSNIT.</p>
          </div>
        </div>
        <div className="card-body form-grid">
          <label className="field">
            Month
            <input className="input" type="month" value={month} onChange={(event) => setMonth(event.target.value)} />
          </label>
          <div className="button-row">
            <button className="btn btn-primary" type="button" onClick={() => void act(() => request(businessPath('/payroll/runs'), { method: 'POST', json: { month } }), `Payroll for ${month} worked out.`)}>
              Work out payroll
            </button>
            <StatusText message={status?.message} error={status?.error} />
          </div>
        </div>
        {runs.data?.length ? (
          <ul className="debt-list">
            {runs.data.map((run) => (
              <li className="debt-card" key={run.id}>
                <div className="debt-head">
                  <div className="file-cell">
                    <strong>{`${run.month} · ${run.staff} staff`}</strong>
                    <small>{`Net ${money(run.net)} · PAYE ${money(run.paye)} · SSNIT ${money(run.ssnit)}${run.paid_on ? ` · paid ${formatDate(run.paid_on)} from ${METHOD_LABEL[run.paid_from ?? ''] ?? run.paid_from}` : ''}`}</small>
                  </div>
                  <div className="debt-amount">
                    <span className="num">{money(run.gross)}</span>
                    <Pill tone={run.status === 'posted' ? 'success' : run.status === 'void' ? '' : 'info'}>{run.status === 'posted' ? 'Posted' : run.status === 'void' ? 'Void' : 'Draft'}</Pill>
                  </div>
                </div>
                <div className="button-row">
                  <button className="btn btn-ghost btn-sm" type="button" aria-expanded={openRun === run.id} onClick={() => setOpenRun(openRun === run.id ? null : run.id)}>
                    {openRun === run.id ? 'Hide' : 'Details and payslips'}
                  </button>
                  {run.status !== 'void' ? (
                    <button className="btn btn-ghost btn-sm" type="button" onClick={() => window.confirm(`Void the ${run.month} payroll? Its entries are reversed.`) && void act(() => request(businessPath(`/payroll/runs/${run.id}/void`), { method: 'POST' }), 'Payroll voided.')}>
                      Void
                    </button>
                  ) : null}
                </div>
                {openRun === run.id && detail.data ? (
                  <div className="form-grid">
                    {detail.data.unchecked_rules.length ? <Notice tone="warning" icon="alert">{`Uses rates not yet checked by your accountant: ${detail.data.unchecked_rules.join(', ')}.`}</Notice> : null}
                    <div className="table-wrap">
                      <DataTable
                        columns={[
                          { label: 'Name', value: (line: RunDetail['lines'][number]) => line.name },
                          { label: 'Gross', num: true, value: (line: RunDetail['lines'][number]) => money(line.gross) },
                          { label: 'SSNIT 5.5%', num: true, value: (line: RunDetail['lines'][number]) => money(line.ssnit_employee) },
                          { label: 'PAYE', num: true, value: (line: RunDetail['lines'][number]) => money(line.paye) },
                          { label: 'Net', num: true, value: (line: RunDetail['lines'][number]) => money(line.net) },
                          {
                            label: '',
                            value: (line: RunDetail['lines'][number]) => (
                              <button className="btn btn-ghost btn-sm" type="button" onClick={() => void payslip(line.id)}>
                                <Icon name="download" />
                                <span className="btn-label">Payslip</span>
                              </button>
                            ),
                          },
                        ]}
                        rows={detail.data.lines}
                        rowKey={(line) => line.id}
                      />
                    </div>
                    {run.status === 'draft' ? (
                      <div className="form-grid">
                        <label className="field">
                          Paid from
                          <select className="select" value={paidFrom} onChange={(event) => setPaidFrom(event.target.value)}>
                            {['bank', 'cash', 'momo_mtn', 'momo_telecel', 'momo_at'].map((key) => (
                              <option key={key} value={key}>
                                {METHOD_LABEL[key]}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label className="field">
                          Paid on
                          <input className="input" type="date" max={isoDate(new Date())} value={paidOn} onChange={(event) => setPaidOn(event.target.value)} />
                        </label>
                        <div className="button-row">
                          <button className="btn btn-primary btn-sm" type="button" onClick={() => void act(() => request(businessPath(`/payroll/runs/${run.id}/post`), { method: 'POST', json: { paid_from: paidFrom, paid_on: paidOn } }), 'Payroll posted to the books.')}>
                            Post to the books
                          </button>
                        </div>
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState title="No payroll yet" />
        )}
      </div>
    </>
  );
}

export default function TaxPayroll() {
  const { business, can } = useWorkspace();
  const editable = can('manage_books');
  const [tab, setTab] = useState<'tax' | 'payroll'>('tax');
  return (
    <>
      <PageActions>
        <Segmented
          id="tax-tabs"
          label="Tax or payroll"
          mode="tabs"
          value={tab}
          onChange={setTab}
          options={[
            { value: 'tax', label: 'Tax' },
            { value: 'payroll', label: 'Payroll' },
          ]}
        />
      </PageActions>
      {tab === 'tax' ? (
        <>
          {editable ? <Summary /> : null}
          <Rules editable={editable} />
        </>
      ) : editable ? (
        <Payroll />
      ) : (
        <ReadOnlyNotice role={business.role ?? 'manager'} what="payroll" />
      )}
    </>
  );
}
