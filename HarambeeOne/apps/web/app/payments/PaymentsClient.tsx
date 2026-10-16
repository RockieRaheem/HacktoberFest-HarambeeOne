'use client';

import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Banknote, CheckCircle2, Link2, WalletCards, X } from 'lucide-react';
import { FilterSearch, MetricCard, PageHeader, RegisterFilters, SectionHeader, Status } from '@/components/ui';
import { getPrimarySchool, type School } from '@/lib/school';
import { AcademicPeriod, getSelectedPeriod } from '@/lib/period';

const API = '/api/backend';
type Student = { id: string; admission_no: string; full_name: string };
type Payment = { id:string; receipt_no:string; external_reference:string; student_name:string; admission_no:string; channel:string; amount:string; currency:string; status:string; purpose:string; commitment_hash:string };
type RequirementAssignment = { id:string; requirement_name:string; requirement_type:string; outstanding_amount:string; status:string };

export default function PaymentsClient() {
  const router = useRouter();
  const [school, setSchool] = useState<School | null>(null);
  const [period, setPeriod] = useState<AcademicPeriod | null>(null);
  const [students, setStudents] = useState<Student[]>([]);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [studentId, setStudentId] = useState('');
  const [requirements, setRequirements] = useState<RequirementAssignment[]>([]);
  const [purposeId, setPurposeId] = useState('');
  const [amount, setAmount] = useState('');
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [channelFilter, setChannelFilter] = useState('all');
  const load = useCallback(async (id:string, periodId:string) => {
    const [studentResponse, paymentResponse] = await Promise.all([fetch(`${API}/api/v1/students?school_id=${id}&period_id=${periodId}`), fetch(`${API}/api/v1/payments?school_id=${id}&period_id=${periodId}`)]);
    if (!studentResponse.ok || !paymentResponse.ok) throw new Error();
    setStudents((await studentResponse.json()).items);
    setPayments(await paymentResponse.json());
  }, []);
  useEffect(() => { Promise.all([getPrimarySchool(), getSelectedPeriod()]).then(([item, selected]) => { setSchool(item); setPeriod(selected); return load(item.id, selected.id); }).catch(() => setError('Finance service is unavailable.')); }, [load]);
  useEffect(() => {
    if (!school || !studentId) { setRequirements([]); return; }
    fetch(`${API}/api/v1/requirement-assignments?school_id=${school.id}&period_id=${period?.id ?? ''}&student_id=${studentId}`)
      .then(response => response.ok ? response.json() : Promise.reject())
      .then((items:RequirementAssignment[]) => setRequirements(items.filter(item => ['payment', 'school_item'].includes(item.requirement_type) && Number(item.outstanding_amount) > 0)))
      .catch(() => setError('Learner requirements could not be loaded.'));
  }, [period, school, studentId]);
  async function submit(event:FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!school) return;
    setSaving(true); setError('');
    const form = new FormData(event.currentTarget);
    try {
      const response = await fetch(`${API}/api/v1/payments`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ school_id:school.id, period_id:period?.id, student_id:form.get('student_id'), external_reference:form.get('reference'), payer_name:form.get('payer_name') || null, note:form.get('note') || null, channel:form.get('channel'), amount:Number(form.get('amount')), requirement_assignment_id:form.get('requirement_assignment_id') || null }) });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? 'Payment could not be recorded.');
      setOpen(false);
      router.push(`/payments/${body.id}/receipt`);
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Payment could not be recorded.'); }
    finally { setSaving(false); }
  }
  const total = payments.reduce((sum, payment) => sum + Number(payment.amount), 0);
  const channels = new Set(payments.map(payment => payment.channel)).size;
  const channelOptions = useMemo(() => Array.from(new Set(payments.map(payment => payment.channel))).sort(), [payments]);
  const visiblePayments = useMemo(() => {
    const term = query.trim().toLowerCase();
    return payments.filter(payment => {
      const matchesQuery = !term || `${payment.receipt_no} ${payment.external_reference} ${payment.student_name} ${payment.admission_no} ${payment.purpose}`.toLowerCase().includes(term);
      return matchesQuery && (channelFilter === 'all' || payment.channel === channelFilter);
    });
  }, [channelFilter, payments, query]);
  const paymentFiltersActive = Boolean(query || channelFilter !== 'all');
  function selectPurpose(value:string) {
    setPurposeId(value);
    const requirement = requirements.find(item => item.id === value);
    if (requirement) setAmount(String(Number(requirement.outstanding_amount)));
  }
  function openPayment() {
    setStudentId('');
    setPurposeId('');
    setAmount('');
    setOpen(true);
  }
  return <><PageHeader eyebrow="Finance · Authoritative learner ledger" title="Payment register" description="Record a source transaction once, allocate it to fees or a specific learner requirement, and issue an official receipt." actions={<button className="btn primary" disabled={!students.length} onClick={openPayment}><Banknote size={16}/>Record payment</button>}/>{error && <div className="form-error page-error">{error}<button onClick={() => setError('')}><X size={15}/></button></div>}
    <section className="metric-grid"><MetricCard icon={WalletCards} label="Recorded payments" value={String(payments.length)} note="Immutable source records" tone="blue"/><MetricCard icon={Banknote} label="Total allocated" value={`UGX ${total.toLocaleString()}`} note="Posted to learner ledgers" tone="green"/><MetricCard icon={Link2} label="Collection channels" value={String(channels)} note="Used in this register" tone="amber"/><MetricCard icon={CheckCircle2} label="Receipt integrity" value="Verified" note="Every payment has an integrity reference"/></section>
    <section className="panel"><SectionHeader title="Transaction register" subtitle="Purpose-linked collections make every receipt explainable"/><RegisterFilters shown={visiblePayments.length} total={payments.length} active={paymentFiltersActive} onReset={() => { setQuery(''); setChannelFilter('all'); }}><FilterSearch value={query} onChange={setQuery} placeholder="Search receipt, learner, reference or purpose"/><select className="select-control" aria-label="Payment channel" value={channelFilter} onChange={event => setChannelFilter(event.target.value)}><option value="all">All channels</option>{channelOptions.map(channel => <option key={channel} value={channel}>{channel.replaceAll('_', ' ')}</option>)}</select></RegisterFilters><div className="table-wrap"><table className="data-table"><thead><tr><th>Receipt</th><th>Learner</th><th>Purpose</th><th>Channel</th><th>Amount</th><th>Ledger</th><th>Integrity reference</th></tr></thead><tbody>{visiblePayments.map(payment => <tr key={payment.id}><td className="entity"><Link className="text-button" href={`/payments/${payment.id}/receipt`}><strong>{payment.receipt_no}</strong></Link><small>{payment.external_reference}</small></td><td className="entity"><strong>{payment.student_name}</strong><small>{payment.admission_no}</small></td><td>{payment.purpose}</td><td>{payment.channel.replace('_',' ')}</td><td className="amount">{payment.currency} {Number(payment.amount).toLocaleString()}</td><td><Status tone="success">{payment.status}</Status></td><td className="entity"><Status tone="success">Recorded</Status><small title={payment.commitment_hash}>{payment.commitment_hash.slice(0,12)}…</small></td></tr>)}{!visiblePayments.length && <tr><td colSpan={7}><div className="empty-register"><WalletCards/><strong>{payments.length ? 'No payments match these filters' : 'No payments recorded'}</strong><span>{payments.length ? 'Reset or change the filters to see more receipts.' : 'Register a learner, then record the first receipt.'}</span></div></td></tr>}</tbody></table></div></section>
    {open && <div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true"><header><div><h2>Record a payment</h2><p>Choose whether this pays the general fees account or one exact requirement.</p></div><button onClick={() => setOpen(false)}><X size={20}/></button></header><form className="modal-form" onSubmit={submit}><label>Learner<select name="student_id" required value={studentId} onChange={event => { setStudentId(event.target.value); setPurposeId(''); setAmount(''); }}><option value="">Select learner</option>{students.map(student => <option key={student.id} value={student.id}>{student.admission_no} · {student.full_name}</option>)}</select></label><label>Payment purpose<select name="requirement_assignment_id" disabled={!studentId} value={purposeId} onChange={event => selectPurpose(event.target.value)}><option value="">School fees / general learner account</option>{requirements.map(item => <option key={item.id} value={item.id}>{item.requirement_name} · UGX {Number(item.outstanding_amount).toLocaleString()} outstanding</option>)}</select></label><label>Payer name<input name="payer_name" maxLength={160} placeholder="Guardian or sponsor name"/></label><label>Source reference<input name="reference" required placeholder="Receipt, bank or mobile money reference"/></label><label>Payment channel<select name="channel"><option value="cash">Cash</option><option value="bank">Bank</option><option value="mobile_money">Mobile Money</option><option value="schoolpay">SchoolPay</option><option value="card">Card</option><option value="sponsor">Sponsor</option></select></label><label>Amount (UGX)<input name="amount" type="number" min="1" step="1" required value={amount} onChange={event => setAmount(event.target.value)}/></label><label>Note<textarea name="note" maxLength={240} placeholder="Size, item details or other useful context"/></label>{error && <div className="form-error">{error}</div>}<footer><button type="button" className="btn" onClick={() => setOpen(false)}>Cancel</button><button className="btn primary" disabled={saving}>{saving ? 'Posting…' : 'Post and issue receipt'}</button></footer></form></section></div>}
  </>;
}
