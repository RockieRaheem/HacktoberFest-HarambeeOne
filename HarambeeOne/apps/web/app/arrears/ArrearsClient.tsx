'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { AlertTriangle, Banknote, CalendarClock, Phone, Users } from 'lucide-react';
import { FilterSearch, MetricCard, PageHeader, RegisterFilters, SectionHeader, Status } from '@/components/ui';
import { getPrimarySchool } from '@/lib/school';
import { getSelectedPeriod } from '@/lib/period';

const API = '/api/backend';
type Account = { student_id:string; admission_no:string; student_name:string; class_name:string; guardian_name:string|null; guardian_phone:string|null; billed:string; paid:string; balance:string; overdue_amount:string; overdue_since:string; days_overdue:number; severity:string };
type Register = { as_of:string; total_accounts:number; total_overdue:string; critical_accounts:number; items:Account[] };
const money = (value:string|number) => `UGX ${Number(value).toLocaleString('en-UG')}`;

export default function ArrearsClient() {
  const [data, setData] = useState<Register|null>(null);
  const [query, setQuery] = useState('');
  const [severity, setSeverity] = useState('all');
  const [classFilter, setClassFilter] = useState('all');
  const [error, setError] = useState('');
  useEffect(() => { Promise.all([getPrimarySchool(), getSelectedPeriod()]).then(([school, period]) => fetch(`${API}/api/v1/arrears?school_id=${school.id}&period_id=${period.id}`)).then(response => { if (!response.ok) throw new Error(); return response.json(); }).then(setData).catch(() => setError('The arrears register is temporarily unavailable.')); }, []);
  const classes = useMemo(() => Array.from(new Set((data?.items ?? []).map(item => item.class_name))).sort(), [data]);
  const items = useMemo(() => (data?.items ?? []).filter(item => (severity === 'all' || item.severity === severity) && (classFilter === 'all' || item.class_name === classFilter) && `${item.student_name} ${item.admission_no} ${item.class_name} ${item.guardian_name ?? ''} ${item.guardian_phone ?? ''}`.toLowerCase().includes(query.toLowerCase())), [classFilter, data, query, severity]);
  const oldest = data?.items.reduce((days, item) => Math.max(days, item.days_overdue), 0) ?? 0;
  return <><PageHeader eyebrow="Bursar · Collections control" title="Overdue accounts" description="Prioritise learner accounts that have missed an installment deadline using the authoritative fee ledger." actions={<Link className="btn primary" href="/payments"><Banknote size={16}/>Record payment</Link>}/>
    {error && <div className="form-error page-error">{error}</div>}
    <section className="metric-grid"><MetricCard icon={Banknote} label="Amount overdue" value={money(data?.total_overdue ?? 0)} note={`As at ${data ? new Date(`${data.as_of}T00:00:00`).toLocaleDateString('en-UG') : 'today'}`} tone="amber"/><MetricCard icon={Users} label="Accounts overdue" value={String(data?.total_accounts ?? 0)} note="Active learners requiring follow-up" tone="blue"/><MetricCard icon={AlertTriangle} label="Critical accounts" value={String(data?.critical_accounts ?? 0)} note="At least 30 days overdue"/><MetricCard icon={CalendarClock} label="Oldest overdue" value={`${oldest} days`} note="Based on unpaid installment order" tone="green"/></section>
    <section className="panel"><SectionHeader title="Collections worklist" subtitle="Payments are applied oldest-installment-first when determining overdue age."/><RegisterFilters shown={items.length} total={data?.items.length ?? 0} active={Boolean(query || severity !== 'all' || classFilter !== 'all')} onReset={() => { setQuery(''); setSeverity('all'); setClassFilter('all'); }}><FilterSearch value={query} onChange={setQuery} placeholder="Search learner, guardian, phone or admission"/><select className="select-control" aria-label="Arrears priority" value={severity} onChange={event => setSeverity(event.target.value)}><option value="all">All priorities</option><option value="critical">Critical · 30+ days</option><option value="warning">Recently overdue</option></select><select className="select-control" aria-label="Learner class" value={classFilter} onChange={event => setClassFilter(event.target.value)}><option value="all">All classes</option>{classes.map(name => <option key={name} value={name}>{name}</option>)}</select></RegisterFilters><div className="table-wrap"><table className="data-table"><thead><tr><th>Learner</th><th>Guardian</th><th>Overdue since</th><th>Outstanding now</th><th>Priority</th><th>Action</th></tr></thead><tbody>{items.map(item => <tr key={item.student_id}><td className="entity"><Link href={`/students/${item.student_id}`}><strong>{item.student_name}</strong></Link><small>{item.admission_no} · {item.class_name}</small></td><td className="entity"><strong>{item.guardian_name || 'No guardian'}</strong><small>{item.guardian_phone || 'No phone recorded'}</small></td><td className="entity"><strong>{new Date(`${item.overdue_since}T00:00:00`).toLocaleDateString('en-UG')}</strong><small>{item.days_overdue} days overdue</small></td><td className="amount"><strong>{money(item.overdue_amount)}</strong><small>{money(item.balance)} total balance</small></td><td><Status tone={item.severity === 'critical' ? 'danger' : 'warning'}>{item.severity}</Status></td><td>{item.guardian_phone ? <a className="text-button" href={`tel:${item.guardian_phone}`}><Phone size={14}/>Call</a> : <Link className="text-button" href={`/students/${item.student_id}`}>Review</Link>}</td></tr>)}{data && !items.length && <tr><td colSpan={6}><div className="empty-register"><Users/><strong>No matching overdue accounts</strong><span>{data.items.length ? 'Reset or change the filters to see other accounts.' : 'All installment accounts are currently up to date.'}</span></div></td></tr>}</tbody></table></div></section>
  </>;
}
