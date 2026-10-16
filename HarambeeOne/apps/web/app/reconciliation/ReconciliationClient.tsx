'use client';

import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { CheckCircle2, FileUp, Landmark, ListChecks, Search, X } from 'lucide-react';
import { FilterSearch, MetricCard, PageHeader, RegisterFilters, SectionHeader, Status } from '@/components/ui';
import { getPrimarySchool, type School } from '@/lib/school';

const API = '/api/backend';
type Student = { id:string; admission_no:string; full_name:string };
type Tx = { id:string; transaction_date:string; source_reference:string; description:string; amount:string; status:string; suggested_student_id:string|null; suggested_student_name:string|null; confidence:string|null; payment_id:string|null };
const money = (value:string|number) => `UGX ${Number(value).toLocaleString('en-UG')}`;

function csvLine(line:string) {
  const values:string[] = []; let value = '', quoted = false;
  for (let index = 0; index < line.length; index++) {
    const character = line[index];
    if (character === '"' && line[index + 1] === '"') { value += '"'; index++; }
    else if (character === '"') quoted = !quoted;
    else if (character === ',' && !quoted) { values.push(value.trim()); value = ''; }
    else value += character;
  }
  values.push(value.trim()); return values;
}

export default function ReconciliationClient() {
  const [school, setSchool] = useState<School|null>(null), [students, setStudents] = useState<Student[]>([]), [items, setItems] = useState<Tx[]>([]);
  const [open, setOpen] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [choices, setChoices] = useState<Record<string,string>>({}), [query, setQuery] = useState(''), [statusFilter, setStatusFilter] = useState('all');
  const load = useCallback(async (id:string) => {
    const [studentResponse, transactionResponse] = await Promise.all([fetch(`${API}/api/v1/students?school_id=${id}`), fetch(`${API}/api/v1/reconciliation/transactions?school_id=${id}`)]);
    if (!studentResponse.ok || !transactionResponse.ok) throw new Error();
    setStudents((await studentResponse.json()).items); setItems(await transactionResponse.json());
  }, []);
  useEffect(() => { getPrimarySchool().then(item => { setSchool(item); return load(item.id); }).catch(() => setError('Reconciliation service is unavailable.')); }, [load]);

  async function upload(event:FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!school) return; setBusy(true); setError('');
    const form = new FormData(event.currentTarget), file = form.get('file') as File;
    try {
      const lines = (await file.text()).split(/\r?\n/).filter(Boolean), headers = csvLine(lines[0]).map(value => value.toLowerCase());
      for (const required of ['date', 'reference', 'amount']) if (!headers.includes(required)) throw new Error(`CSV is missing the ${required} column.`);
      const rows = lines.slice(1).map(line => { const cells = csvLine(line), get = (name:string) => cells[headers.indexOf(name)] ?? ''; return { transaction_date:get('date'), source_reference:get('reference'), description:get('description'), amount:Number(get('amount').replaceAll(',', '')) }; });
      const response = await fetch(`${API}/api/v1/reconciliation/imports`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ school_id:school.id, file_name:file.name, rows }) });
      const body = await response.json(); if (!response.ok) throw new Error(body.detail ?? 'Statement import failed.');
      setOpen(false); setNotice(`${body.row_count} source transactions imported for review.`); await load(school.id);
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Statement import failed.'); } finally { setBusy(false); }
  }

  async function confirm(item:Tx) {
    if (!school) return; const studentId = choices[item.id] || item.suggested_student_id;
    if (!studentId) return setError('Select a learner before confirming the match.');
    setBusy(true); setError('');
    const response = await fetch(`${API}/api/v1/reconciliation/transactions/${item.id}/confirm`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({student_id:studentId}) });
    const body = await response.json();
    if (!response.ok) { setBusy(false); return setError(body.detail ?? 'Match could not be confirmed.'); }
    setNotice(`Transaction reconciled. Receipt ${body.receipt_no}.`); await load(school.id); setBusy(false);
  }

  const pending = items.filter(item => item.status !== 'reconciled'), suggested = pending.filter(item => item.status === 'suggested').length;
  const total = pending.reduce((sum, item) => sum + Number(item.amount), 0);
  const statuses = useMemo(() => Array.from(new Set(items.map(item => item.status))).sort(), [items]);
  const visibleItems = useMemo(() => { const term = query.trim().toLowerCase(); return items.filter(item => (statusFilter === 'all' || item.status === statusFilter) && (!term || `${item.source_reference} ${item.description} ${item.suggested_student_name ?? ''}`.toLowerCase().includes(term))); }, [items, query, statusFilter]);

  return <><PageHeader eyebrow="Bursar · Source reconciliation" title="Statement reconciliation" description="Import source transactions, review learner matches, and post only after human confirmation." actions={<button className="btn primary" onClick={() => setOpen(true)}><FileUp size={16}/>Import CSV</button>}/>
    {error && <div className="form-error page-error">{error}<button onClick={() => setError('')}><X size={15}/></button></div>}{notice && <div className="success-banner">{notice}</div>}
    <section className="metric-grid"><MetricCard icon={ListChecks} label="Awaiting review" value={String(pending.length)} note={money(total)} tone="amber"/><MetricCard icon={Search} label="Suggested matches" value={String(suggested)} note="Exact learner references" tone="blue"/><MetricCard icon={CheckCircle2} label="Reconciled" value={String(items.length - pending.length)} note="Posted to learner ledgers" tone="green"/><MetricCard icon={Landmark} label="Control rule" value="Human" note="Confirmation required"/></section>
    <section className="panel"><SectionHeader title="Source transaction register" subtitle="Imported rows never change balances until confirmed."/><RegisterFilters shown={visibleItems.length} total={items.length} active={Boolean(query || statusFilter !== 'all')} onReset={() => { setQuery(''); setStatusFilter('all'); }}><FilterSearch value={query} onChange={setQuery} placeholder="Search reference, description or learner"/><select className="select-control" aria-label="Reconciliation status" value={statusFilter} onChange={event => setStatusFilter(event.target.value)}><option value="all">All statuses</option>{statuses.map(status => <option key={status} value={status}>{status.replaceAll('_', ' ')}</option>)}</select></RegisterFilters><div className="table-wrap"><table className="data-table"><thead><tr><th>Date</th><th>Source</th><th>Amount</th><th>Suggested learner</th><th>Status</th><th>Action</th></tr></thead><tbody>{visibleItems.map(item => <tr key={item.id}><td>{new Date(`${item.transaction_date}T00:00:00`).toLocaleDateString('en-UG')}</td><td className="entity"><strong>{item.source_reference}</strong><small>{item.description || 'No description'}</small></td><td className="amount">{money(item.amount)}</td><td><select className="select-control" disabled={item.status === 'reconciled'} value={choices[item.id] ?? item.suggested_student_id ?? ''} onChange={event => setChoices({...choices, [item.id]:event.target.value})}><option value="">Select learner</option>{students.map(student => <option key={student.id} value={student.id}>{student.admission_no} · {student.full_name}</option>)}</select></td><td><Status tone={item.status === 'reconciled' ? 'success' : item.status === 'suggested' ? 'warning' : 'danger'}>{item.status}</Status></td><td>{item.payment_id ? <Link className="text-button" href={`/payments/${item.payment_id}/receipt`}>Receipt</Link> : <button className="text-button" disabled={busy} onClick={() => confirm(item)}>Confirm match</button>}</td></tr>)}{!visibleItems.length && <tr><td colSpan={6}><div className="empty-register"><Landmark/><strong>{items.length ? 'No transactions match these filters' : 'No statement rows'}</strong><span>{items.length ? 'Reset or change the filters to see more transactions.' : 'Import a CSV with date, reference, description and amount columns.'}</span></div></td></tr>}</tbody></table></div></section>
    {open && <div className="modal-backdrop"><section className="modal"><header><div><h2>Import statement CSV</h2><p>Required columns: date, reference, amount. Description is optional.</p></div><button onClick={() => setOpen(false)}><X/></button></header><form className="modal-form" onSubmit={upload}><label>Statement file<input name="file" type="file" accept=".csv,text/csv" required/></label><div className="notice">Duplicate source references are rejected to prevent double posting.</div><footer><button type="button" className="btn" onClick={() => setOpen(false)}>Cancel</button><button className="btn primary" disabled={busy}>{busy ? 'Importing…' : 'Import for review'}</button></footer></form></section></div>}
  </>;
}
