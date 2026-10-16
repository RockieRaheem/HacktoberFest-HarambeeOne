'use client';

import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { BarChart3, Banknote, Download, ReceiptText, Target } from 'lucide-react';
import { FilterSearch, MetricCard, PageHeader, RegisterFilters, SectionHeader, Status } from '@/components/ui';
import { getPrimarySchool, type School } from '@/lib/school';
import { getSelectedPeriod } from '@/lib/period';

const API = '/api/backend';
type Breakdown = { label:string; amount:string };
type Transaction = { id:string; receipt_no:string; received_at:string; student_name:string; admission_no:string; class_name:string; channel:string; reference:string; amount:string };
type Report = { start_date:string; end_date:string; billed:string; collected:string; outstanding:string; collection_rate:number; transaction_count:number; average_payment:string; by_channel:Breakdown[]; by_class:Breakdown[]; transactions:Transaction[] };
const money = (value:string|number) => `UGX ${Number(value).toLocaleString('en-UG', {maximumFractionDigits:0})}`;
const today = new Date().toISOString().slice(0, 10), yearStart = `${new Date().getFullYear()}-01-01`;

export default function ReportsClient() {
  const [school, setSchool] = useState<School|null>(null), [report, setReport] = useState<Report|null>(null);
  const [start, setStart] = useState(yearStart), [end, setEnd] = useState(today), [error, setError] = useState('');
  const [query, setQuery] = useState(''), [classFilter, setClassFilter] = useState('all'), [channelFilter, setChannelFilter] = useState('all');
  const load = useCallback(async (schoolId:string, from:string, to:string) => {
    setError(''); const period = await getSelectedPeriod(); const response = await fetch(`${API}/api/v1/reports/collections?school_id=${schoolId}&period_id=${period.id}&start_date=${from}&end_date=${to}`, {cache:'no-store'});
    if (!response.ok) { const body = await response.json(); throw new Error(body.detail ?? 'Report could not be generated.'); }
    setReport(await response.json());
  }, []);
  useEffect(() => { getPrimarySchool().then(item => { setSchool(item); return load(item.id, yearStart, today); }).catch(reason => setError(reason instanceof Error ? reason.message : 'Reporting service is unavailable.')); }, [load]);
  function generate(event:FormEvent) { event.preventDefault(); if (school) load(school.id, start, end).catch(reason => setError(reason.message)); }

  const classes = useMemo(() => Array.from(new Set((report?.transactions ?? []).map(item => item.class_name))).sort(), [report]);
  const channels = useMemo(() => Array.from(new Set((report?.transactions ?? []).map(item => item.channel))).sort(), [report]);
  const visibleTransactions = useMemo(() => {
    const term = query.trim().toLowerCase();
    return (report?.transactions ?? []).filter(item => (!term || `${item.receipt_no} ${item.reference} ${item.student_name} ${item.admission_no}`.toLowerCase().includes(term)) && (classFilter === 'all' || item.class_name === classFilter) && (channelFilter === 'all' || item.channel === channelFilter));
  }, [channelFilter, classFilter, query, report]);
  function exportCsv() {
    if (!report) return;
    const escape = (value:string|number) => `"${String(value).replaceAll('"', '""')}"`;
    const rows = [['Receipt', 'Date', 'Learner', 'Admission', 'Class', 'Channel', 'Reference', 'Amount'], ...visibleTransactions.map(item => [item.receipt_no, item.received_at, item.student_name, item.admission_no, item.class_name, item.channel, item.reference, item.amount])];
    const url = URL.createObjectURL(new Blob([rows.map(row => row.map(escape).join(',')).join('\r\n')], {type:'text/csv;charset=utf-8'})), link = document.createElement('a');
    link.href = url; link.download = `harambeeone-collections-${report.start_date}-${report.end_date}.csv`; link.click(); URL.revokeObjectURL(url);
  }
  const maximum = Math.max(1, ...(report?.by_class ?? []).map(item => Number(item.amount)));

  return <><PageHeader eyebrow="Finance · Management reporting" title="Collection report" description="Audit-ready collections, channel mix, class performance and receipt detail from the authoritative ledger." actions={<button className="btn primary" disabled={!report || !visibleTransactions.length} onClick={exportCsv}><Download size={16}/>Export visible CSV</button>}/>
    {error && <div className="form-error page-error">{error}</div>}
    <form className="filter-bar" onSubmit={generate}><label>From <input className="select-control" type="date" value={start} max={end} onChange={event => setStart(event.target.value)} required/></label><label>To <input className="select-control" type="date" value={end} min={start} onChange={event => setEnd(event.target.value)} required/></label><button className="btn">Generate report</button></form>
    <section className="metric-grid"><MetricCard icon={Banknote} label="Collected" value={money(report?.collected ?? 0)} note={`${report?.transaction_count ?? 0} posted receipts`} tone="green"/><MetricCard icon={Target} label="Collection rate" value={`${(report?.collection_rate ?? 0).toFixed(1)}%`} note={`${money(report?.billed ?? 0)} billed`} tone="blue"/><MetricCard icon={ReceiptText} label="Outstanding" value={money(report?.outstanding ?? 0)} note="Against assigned fees" tone="amber"/><MetricCard icon={BarChart3} label="Average receipt" value={money(report?.average_payment ?? 0)} note="Within selected period"/></section>
    <div className="content-grid"><section className="panel"><SectionHeader title="Collections by class" subtitle="Posted receipts in the selected period."/><div className="report-bars">{report?.by_class.map(item => <div key={item.label}><span><strong>{item.label}</strong><b>{money(item.amount)}</b></span><i><em style={{width:`${Number(item.amount) / maximum * 100}%`}}/></i></div>)}{report && !report.by_class.length && <div className="empty-register">No collection activity in this period.</div>}</div></section><section className="panel"><SectionHeader title="Payment channels" subtitle="Source mix for posted payments."/><div className="attention-list">{report?.by_channel.map(item => <div className="attention-item" key={item.label}><div className="attention-icon blue"><Banknote size={15}/></div><div><strong>{item.label}</strong><small>Cleared collection channel</small></div><time>{money(item.amount)}</time></div>)}</div></section></div>
    <section className="panel"><SectionHeader title="Receipt detail" subtitle="Filters also control the CSV export."/><RegisterFilters shown={visibleTransactions.length} total={report?.transactions.length ?? 0} active={Boolean(query || classFilter !== 'all' || channelFilter !== 'all')} onReset={() => { setQuery(''); setClassFilter('all'); setChannelFilter('all'); }}><FilterSearch value={query} onChange={setQuery} placeholder="Search receipt, learner, admission or reference"/><select className="select-control" aria-label="Receipt class" value={classFilter} onChange={event => setClassFilter(event.target.value)}><option value="all">All classes</option>{classes.map(value => <option key={value} value={value}>{value}</option>)}</select><select className="select-control" aria-label="Receipt channel" value={channelFilter} onChange={event => setChannelFilter(event.target.value)}><option value="all">All channels</option>{channels.map(value => <option key={value} value={value}>{value.replaceAll('_', ' ')}</option>)}</select></RegisterFilters><div className="table-wrap"><table className="data-table"><thead><tr><th>Date</th><th>Receipt</th><th>Learner</th><th>Class</th><th>Channel</th><th>Amount</th></tr></thead><tbody>{visibleTransactions.map(item => <tr key={item.id}><td>{new Date(item.received_at).toLocaleDateString('en-UG')}</td><td><Link className="text-button" href={`/payments/${item.id}/receipt`}>{item.receipt_no}</Link></td><td className="entity"><strong>{item.student_name}</strong><small>{item.admission_no}</small></td><td>{item.class_name}</td><td><Status tone="success">{item.channel.replace('_', ' ')}</Status></td><td className="amount">{money(item.amount)}</td></tr>)}{report && !visibleTransactions.length && <tr><td colSpan={6}><div className="empty-register"><ReceiptText/><strong>No receipts match this view</strong><span>{report.transactions.length ? 'Reset or change the receipt filters.' : 'Adjust the report period or record a payment.'}</span></div></td></tr>}</tbody></table></div></section>
  </>;
}
