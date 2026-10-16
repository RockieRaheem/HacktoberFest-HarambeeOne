'use client';

import Link from 'next/link';
import { Bot, CheckCircle2, Copy, ExternalLink, HandHeart, Plus, ShieldCheck, UserRoundPlus, X } from 'lucide-react';
import { FormEvent, useCallback, useEffect, useState } from 'react';
import { MetricCard, PageHeader, SectionHeader, Status } from '@/components/ui';
import { getSelectedPeriod } from '@/lib/period';
import { getPrimarySchool, type School } from '@/lib/school';

const API = '/api/backend';
type Student = { id:string; admission_no:string; full_name:string };
type Requirement = { id:string; requirement_name:string; requirement_type:string; outstanding_amount:string };
type Eligibility = { general_outstanding:string; eligible:boolean };
type Case = { id:string; public_code:string; student_name:string; admission_no:string; title:string; target_amount:string; verified_amount:string; pending_amount:string; status:string; has_ai_review:boolean };
type Detail = { id:string; public_code:string; student:{name:string;admission_no:string}; title:string; public_summary:string; status:string; risk_level:string; guardians:{id:string;name:string;relationship:string}[]; consent:null|{method:string;gemma_processing:boolean;cross_border_processing:boolean;child_assent_status:string}; ai_review:null|{summary:string;risk_level:string;observed_factors:string[];missing_information:string[];consistency_flags:string[];recommended_action:string;safe_public_summary:string} };
type GemmaStatus = {configured:boolean;model:string;decision_authority:string};
type Pledge = { id:string; public_reference:string; external_reference:string; donor_display_name:string; amount:string; status:string };
type Candidate = {student_id:string;student_name:string;admission_no:string;class_name:string;overdue_amount:string;days_overdue:number;priority_band:string;guardian_link_id:string|null;guardian_email:string|null;guardian_portal_linked:boolean;referral_id:string|null;referral_status:string|null};
const money = (value:string|number) => `UGX ${Number(value).toLocaleString('en-UG')}`;

export default function SupportAdmin() {
  const [school, setSchool] = useState<School|null>(null);
  const [periodId, setPeriodId] = useState('');
  const [students, setStudents] = useState<Student[]>([]);
  const [cases, setCases] = useState<Case[]>([]);
  const [selected, setSelected] = useState<Detail|null>(null);
  const [pledges, setPledges] = useState<Pledge[]>([]);
  const [modal, setModal] = useState<'case'|'consent'|'review'|'proof'|null>(null);
  const [gemma, setGemma] = useState<GemmaStatus|null>(null);
  const [caseStudentId, setCaseStudentId] = useState('');
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [requirementId, setRequirementId] = useState('');
  const [targetAmount, setTargetAmount] = useState('');
  const [generalOutstanding, setGeneralOutstanding] = useState(0);
  const [obligationsLoading, setObligationsLoading] = useState(false);
  const [modalError, setModalError] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [guardianInvite, setGuardianInvite] = useState<{guardianId:string;email:string;path:string}|null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);

  const load = useCallback(async (schoolId:string, period:string) => {
    const [studentResponse, caseResponse, candidateResponse, gemmaResponse] = await Promise.all([
      fetch(`${API}/api/v1/students?school_id=${schoolId}&period_id=${period}`),
      fetch(`${API}/api/v1/support/cases?school_id=${schoolId}`),
      fetch(`${API}/api/v1/support/referral-candidates?school_id=${schoolId}&period_id=${period}`),
      fetch(`${API}/api/v1/support/gemma`),
    ]);
    const studentBody = await apiBody<{items:Student[];detail?:string}>(studentResponse);
    const caseBody = await apiBody<Case[] & {detail?:string}>(caseResponse);
    if (!studentResponse.ok || !caseResponse.ok) throw new Error(studentBody.detail ?? caseBody.detail ?? 'Learner support could not be loaded.');
    setStudents(studentBody.items);
    setCases(caseBody);
    if (candidateResponse.ok) setCandidates((await apiBody<{items:Candidate[]}>(candidateResponse)).items);
    if (gemmaResponse.ok) setGemma(await apiBody<GemmaStatus>(gemmaResponse));
  }, []);

  useEffect(() => {
    Promise.all([getPrimarySchool(), getSelectedPeriod()])
      .then(([currentSchool, period]) => {
        setSchool(currentSchool);
        setPeriodId(period.id);
        return load(currentSchool.id, period.id);
      })
      .catch(reason => setError(reason.message ?? 'Learner support could not be loaded.'));
  }, [load]);

  useEffect(() => {
    if (!school || !caseStudentId) { setRequirements([]); setGeneralOutstanding(0); return; }
    let cancelled = false;
    setObligationsLoading(true); setModalError('');
    Promise.all([
      fetch(`${API}/api/v1/requirement-assignments?school_id=${school.id}&period_id=${periodId}&student_id=${caseStudentId}`),
      fetch(`${API}/api/v1/support/eligibility?school_id=${school.id}&period_id=${periodId}&student_id=${caseStudentId}`),
    ]).then(async ([requirementResponse, eligibilityResponse]) => {
      const requirementBody = await apiBody<Requirement[] | {detail?:unknown}>(requirementResponse);
      const eligibilityBody = await apiBody<Eligibility & {detail?:unknown}>(eligibilityResponse);
      if (!requirementResponse.ok) throw new Error(apiError('detail' in requirementBody ? requirementBody.detail : null, requirementResponse.status));
      if (!eligibilityResponse.ok) throw new Error(apiError(eligibilityBody.detail, eligibilityResponse.status));
      if (cancelled) return;
      const payable = (requirementBody as Requirement[]).filter(item => ['payment', 'school_item'].includes(item.requirement_type) && Number(item.outstanding_amount) > 0);
      const available = Number(eligibilityBody.general_outstanding);
      setRequirements(payable); setGeneralOutstanding(available); setTargetAmount(String(available || ''));
    }).catch(reason => { if (!cancelled) setModalError(reason instanceof Error ? reason.message : 'The learner obligations could not be loaded.'); })
      .finally(() => { if (!cancelled) setObligationsLoading(false); });
    return () => { cancelled = true; };
  }, [caseStudentId, periodId, school]);

  async function openCase(id:string) {
    setError('');
    const [caseResponse, pledgeResponse] = await Promise.all([
      fetch(`${API}/api/v1/support/cases/${id}`),
      fetch(`${API}/api/v1/support/cases/${id}/pledges`),
    ]);
    const body = await apiBody<Detail & {detail?:string}>(caseResponse);
    if (!caseResponse.ok) return setError(body.detail ?? 'Case could not be loaded.');
    setSelected(body);
    setPledges(pledgeResponse.ok ? await apiBody<Pledge[]>(pledgeResponse) : []);
  }

  async function mutate(path:string, body:unknown, success:string) {
    if (!school) return;
    setBusy(true); setError(''); setModalError(''); setNotice('');
    try {
      const response = await fetch(`${API}${path}`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body) });
      const result = await apiBody<{id?:string;detail?:unknown}>(response);
      if (!response.ok) throw new Error(apiError(result.detail, response.status));
      setNotice(success); setModal(null);
      await load(school.id, periodId);
      if (selected) await openCase(selected.id);
      return result;
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : 'Action could not be completed.';
      if (modal) setModalError(message); else setError(message);
    } finally { setBusy(false); }
  }

  function openCreate() {
    setCaseStudentId(''); setRequirements([]); setRequirementId(''); setTargetAmount(''); setGeneralOutstanding(0); setModalError(''); setModal('case');
  }

  function chooseRequirement(id:string) {
    setRequirementId(id);
    const requirement = requirements.find(item => item.id === id);
    setTargetAmount(String(requirement ? Number(requirement.outstanding_amount) : generalOutstanding || ''));
  }

  async function createCase(event:FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!school) return;
    const form = new FormData(event.currentTarget);
    const title = String(form.get('title') ?? '').trim();
    const publicSummary = String(form.get('public_summary') ?? '').trim();
    const learner = students.find(student => student.id === caseStudentId);
    const privateTokens = [learner?.admission_no, ...(learner?.full_name.split(/\s+/) ?? [])].filter((value):value is string => Boolean(value && value.length >= 3));
    const publicText = `${title} ${publicSummary}`.toLocaleLowerCase();
    if (privateTokens.some(token => publicText.includes(token.toLocaleLowerCase()))) {
      setModalError('Remove the learner name and admission number from the public title and summary. Use anonymous wording such as “A candidate needs examination support.”');
      return;
    }
    const selectedRequirement = requirements.find(item => item.id === requirementId);
    const available = selectedRequirement ? Number(selectedRequirement.outstanding_amount) : generalOutstanding;
    if (!available || Number(targetAmount) > available) {
      setModalError(`Enter a target no greater than the verified outstanding balance of ${money(available)}.`);
      return;
    }
    const result = await mutate('/api/v1/support/cases', {
      school_id:school.id,
      period_id:periodId,
      student_id:caseStudentId,
      requirement_assignment_id:requirementId || null,
      title,
      public_summary:publicSummary,
      need_category:form.get('need_category'),
      target_amount:Number(targetAmount),
    }, 'Private support case created. Complete consent and review before publication.');
    if (result?.id) await openCase(result.id);
  }

  async function consent(event:FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const form = new FormData(event.currentTarget);
    const gemmaProcessing = form.get('gemma_processing') === 'on';
    const crossBorder = form.get('cross_border_processing') === 'on';
    if (gemmaProcessing && !crossBorder) {
      setModalError('Gemma review requires a separate choice to allow processing outside Uganda.');
      return;
    }
    await mutate(`/api/v1/support/cases/${selected.id}/consent`, {
      guardian_link_id:form.get('guardian_link_id'), method:form.get('method'), anonymous_publication:true,
      gemma_processing:gemmaProcessing, cross_border_processing:crossBorder, child_assent_status:form.get('child_assent_status'),
    }, 'Guardian consent recorded.');
  }

  async function review(event:FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const form = new FormData(event.currentTarget);
    const file = (form.get('evidence') as File | null);
    const hasFile = Boolean(file && file.size);
    if (hasFile && file) {
      if (file.size > 6_000_000) {
        setModalError('Use a redacted image smaller than 6 MB.');
        return;
      }
      if (form.get('evidence_redacted') !== 'on') {
        setModalError('Confirm that names, faces, admission numbers and contacts are redacted.');
        return;
      }
      await mutate(`/api/v1/support/cases/${selected.id}/ai-review`, {
        evidence_image_base64: await fileBase64(file),
        evidence_mime_type: file.type,
        evidence_redacted: true,
      }, 'Gemma completed the anonymous multimodal case review.');
      return;
    }
    await mutate(`/api/v1/support/cases/${selected.id}/ai-review`, {}, 'Gemma completed the anonymous case review.');
  }

  async function publish() { if (selected) await mutate(`/api/v1/support/cases/${selected.id}/publish`, {}, 'Campaign published to the donor portal.'); }
  async function inviteGuardian(guardianId:string) {
    if (!school) return;
    setBusy(true); setError(''); setGuardianInvite(null);
    try {
      const response = await fetch(`${API}/api/v1/support/guardian-invitations`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({school_id:school.id,guardian_link_id:guardianId})});
      const body = await apiBody<{invited_email?:string;claim_path?:string;detail?:unknown}>(response);
      if (!response.ok || !body.claim_path || !body.invited_email) throw new Error(apiError(body.detail, response.status));
      setGuardianInvite({guardianId,email:body.invited_email,path:body.claim_path});
      setNotice('Guardian invitation created. Share the private link only with the invited guardian.');
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Guardian invitation could not be created.'); }
    finally { setBusy(false); }
  }
  async function createReferral(item:Candidate) {
    if (!school || !item.guardian_link_id) return;
    setBusy(true); setError('');
    try {
      const response = await fetch(`${API}/api/v1/support/referrals`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({school_id:school.id,period_id:periodId,student_id:item.student_id,guardian_link_id:item.guardian_link_id})});
      const body = await apiBody<{detail?:unknown}>(response);
      if (!response.ok) throw new Error(apiError(body.detail, response.status));
      setNotice('Private support referral sent to the guardian workspace.');
      await load(school.id, periodId);
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Referral could not be created.'); }
    finally { setBusy(false); }
  }
  async function decide(item:Pledge, action:'verify'|'reject') {
    const reason = action === 'reject' ? window.prompt('Why is this contribution being rejected?') : null;
    if (action === 'reject' && !reason) return;
    await mutate(`/api/v1/support/pledges/${item.id}/verify`, { action, reason }, action === 'verify' ? 'Contribution verified and posted to the learner account.' : 'Contribution rejected.');
  }
  async function proof(event:FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!selected) return;
    const form = new FormData(event.currentTarget);
    await mutate(`/api/v1/support/cases/${selected.id}/attestations`, { attestation_type:form.get('attestation_type'), statement:form.get('statement'), attendance_band:form.get('attendance_band') || null, is_public:true }, 'Public proof update recorded.');
  }

  const target = cases.reduce((sum, item) => sum + Number(item.target_amount), 0);
  const verified = cases.reduce((sum, item) => sum + Number(item.verified_amount), 0);
  const pending = cases.reduce((sum, item) => sum + Number(item.pending_amount), 0);
  const obligationLimit = requirementId ? Number(requirements.find(item => item.id === requirementId)?.outstanding_amount ?? 0) : generalOutstanding;

  return <>
    <PageHeader eyebrow="Learner support · Controlled assistance" title="Harambee Support" description="Create a case from a real learner balance, obtain consent, review it and publish it to the public donor portal." actions={<div className="page-header-actions"><Link className="btn" href="/support" target="_blank">Public portal <ExternalLink size={15}/></Link><button className="btn primary" onClick={openCreate} disabled={!students.length}><Plus size={16}/>New support case</button></div>}/>
    {error && <div className="form-error page-error">{error}<button onClick={() => setError('')}><X size={15}/></button></div>}
    {notice && <div className="success-banner">{notice}</div>}

    <section className="support-workflow" aria-label="Campaign publication workflow">
      <div><span>1</span><strong>Create case</strong><small>Select a learner and a live fee or requirement balance.</small></div>
      <div><span>2</span><strong>Record consent</strong><small>Guardian permission is mandatory before review.</small></div>
      <div><span>3</span><strong>Review safely</strong><small>{gemma?.configured ? `${gemma.model} checks anonymous facts; a human still decides.` : 'Add GEMINI_API_KEY on the server to enable Gemma, or publish after human review if Gemma was not consented.'}</small></div>
      <div><span>4</span><strong>Owner publishes</strong><small>Only approved cases appear in the public donor portal.</small></div>
    </section>

    <section className="metric-grid">
      <MetricCard icon={HandHeart} label="Verified support" value={money(verified)} note={`${cases.length} controlled cases`} tone="green"/>
      <MetricCard icon={ShieldCheck} label="Campaign targets" value={money(target)} note="Backed by learner obligations"/>
      <MetricCard icon={CheckCircle2} label="Pending settlement" value={money(pending)} note="Excluded until verified" tone="amber"/>
      <MetricCard icon={Bot} label="Gemma reviewed" value={String(cases.filter(item => item.has_ai_review).length)} note="Human approval remains required" tone="blue"/>
    </section>

    <section className="panel referral-register">
      <SectionHeader title="Arrears referral candidates" subtitle="Deterministic ledger facts only—these indicators support human outreach and do not predict dropout."/>
      <div className="table-wrap"><table className="data-table"><thead><tr><th>Learner</th><th>Class</th><th>Overdue</th><th>Priority</th><th>Guardian access</th><th>Action</th></tr></thead><tbody>{candidates.map(item=><tr key={item.student_id}><td className="entity"><strong>{item.student_name}</strong><small>{item.admission_no}</small></td><td>{item.class_name}</td><td><strong>{money(item.overdue_amount)}</strong><small>{item.days_overdue} days</small></td><td><Status tone={item.priority_band==='urgent'?'danger':item.priority_band==='high'?'warning':'neutral'}>{item.priority_band}</Status></td><td>{item.guardian_portal_linked?'Verified portal link':item.guardian_email||'Guardian email missing'}</td><td>{item.referral_id?<Status tone={item.referral_status==='consented'?'success':'info'}>{item.referral_status}</Status>:item.guardian_portal_linked?<button className="btn compact" disabled={busy} onClick={()=>createReferral(item)}>Send referral</button>:item.guardian_link_id?<button className="btn compact" disabled={busy||!item.guardian_email} onClick={()=>inviteGuardian(item.guardian_link_id!)}>Create invite</button>:<span className="muted-action">Add guardian</span>}</td></tr>)}{!candidates.length&&<tr><td colSpan={6}><div className="empty-register"><ShieldCheck/><strong>No overdue referral candidates</strong><span>Only learners with a calculated overdue installment appear here.</span></div></td></tr>}</tbody></table></div>
      {guardianInvite&&<div className="guardian-invite-result"><span>Private link for {guardianInvite.email}</span><code>{`${window.location.origin}${guardianInvite.path}`}</code><button className="btn compact" onClick={()=>navigator.clipboard.writeText(`${window.location.origin}${guardianInvite.path}`)}><Copy size={13}/>Copy link</button></div>}
    </section>

    <div className="content-grid support-admin-grid">
      <section className="panel">
        <SectionHeader title="Support cases" subtitle="Drafts remain private; published cases appear automatically in the donor portal."/>
        {cases.map(item => <button className={`support-case-row ${selected?.id === item.id ? 'selected' : ''}`} key={item.id} onClick={() => openCase(item.id)}>
          <div><strong>{item.student_name}</strong><small>{item.admission_no} · {item.public_code}</small></div>
          <div><span>{item.title}</span><small>{money(item.verified_amount)} of {money(item.target_amount)}</small></div>
          <Status tone={item.status === 'funded' ? 'success' : item.status === 'published' ? 'info' : 'neutral'}>{item.status}</Status>
        </button>)}
        {!cases.length && <div className="empty-register"><HandHeart/><strong>No learner support cases</strong><span>{students.length ? 'Start with a learner who has an outstanding fee or payable requirement.' : 'Register learners and publish their fees or requirements before creating a support case.'}</span>{students.length ? <button className="btn primary" onClick={openCreate}><Plus size={15}/>Create first case</button> : <div className="empty-actions"><Link className="btn" href="/students">Register learners</Link><Link className="btn" href="/requirements">Set requirements</Link></div>}</div>}
      </section>

      <aside className="panel support-case-detail">
        <SectionHeader title={selected?.title ?? 'Case workflow'} subtitle={selected ? `${selected.student.name} · ${selected.student.admission_no}` : 'Select a case to continue'}/>
        {selected && <div className="support-admin-body">
          <div className="support-admin-progress"><span>1. Consent <b>{selected.consent ? 'Complete' : 'Required'}</b></span><span>2. Gemma review <b>{selected.ai_review ? 'Complete' : selected.consent?.gemma_processing ? (gemma?.configured ? 'Required' : 'Not configured') : 'Not requested'}</b></span><span>3. Approval <b>{selected.status}</b></span></div>
          <p>{selected.public_summary}</p>
          {selected.consent?.gemma_processing && !gemma?.configured && !selected.ai_review && <div className="notice">Gemma consent is recorded, but GEMINI_API_KEY is not configured on the API server. Publication stays blocked until a review completes or Gemma consent is withdrawn.</div>}
          <div className="support-case-actions">
            {!selected.consent && <button className="btn" onClick={() => { setModalError(''); setModal('consent'); }}>Record consent</button>}
            {selected.consent?.gemma_processing && !selected.ai_review && <button className="btn primary" disabled={busy || !gemma?.configured} onClick={() => { setModalError(''); setModal('review'); }}>Run Gemma review</button>}
            {selected.consent && (!selected.consent.gemma_processing || selected.ai_review) && selected.status === 'review' && school?.role === 'owner' && <button className="btn primary" disabled={busy} onClick={publish}>Approve & publish</button>}
            {selected.consent && (!selected.consent.gemma_processing || selected.ai_review) && selected.status === 'review' && school?.role !== 'owner' && <span className="support-owner-note">An institution owner must approve publication.</span>}
            {['published','funded','closed'].includes(selected.status) && <><Link className="btn" href={`/support/${selected.public_code}`} target="_blank">Public record <ExternalLink size={14}/></Link><button className="btn" onClick={() => { setModalError(''); setModal('proof'); }}>Add proof update</button></>}
          </div>
          {selected.ai_review && <div className="support-review">
            <strong>Gemma review · {selected.ai_review.risk_level} risk</strong>
            <p>{selected.ai_review.summary}</p>
            <p><em>Recommended action:</em> {selected.ai_review.recommended_action}</p>
            <p><em>Safe public summary:</em> {selected.ai_review.safe_public_summary}</p>
            {selected.ai_review.observed_factors.length > 0 && <small>Observed: {selected.ai_review.observed_factors.join(' · ')}</small>}
            {selected.ai_review.missing_information.length > 0 && <small>Missing: {selected.ai_review.missing_information.join(' · ')}</small>}
            {selected.ai_review.consistency_flags.length > 0 && <small>Flags: {selected.ai_review.consistency_flags.join(' · ')}</small>}
            <small>Gemma does not publish campaigns or post payments.</small>
          </div>}
          <h3>Guardian portal access</h3>
          <p className="muted-action">Invitations expire after 72 hours, work once, and require the guardian&apos;s registered email.</p>
          {selected.guardians.map(guardian => <div className="guardian-access-row" key={guardian.id}><div><strong>{guardian.name}</strong><small>{guardian.relationship}</small></div><button className="btn compact" disabled={busy} onClick={() => inviteGuardian(guardian.id)}><UserRoundPlus size={14}/>Create invite</button></div>)}
          {guardianInvite && <div className="guardian-invite-result"><span>Private link for {guardianInvite.email}</span><code>{`${window.location.origin}${guardianInvite.path}`}</code><button className="btn compact" onClick={() => navigator.clipboard.writeText(`${window.location.origin}${guardianInvite.path}`)}><Copy size={13}/>Copy link</button></div>}
          <h3>Contributions</h3>
          {pledges.map(item => <div className="support-pledge-row" key={item.id}><div><strong>{item.donor_display_name}</strong><small>{item.public_reference} · {item.external_reference}</small></div><b>{money(item.amount)}</b>{item.status === 'pending' ? <span><button onClick={() => decide(item, 'verify')}>Verify</button><button onClick={() => decide(item, 'reject')}>Reject</button></span> : <Status tone={item.status === 'verified' ? 'success' : 'neutral'}>{item.status}</Status>}</div>)}
          {!pledges.length && <p className="muted-action">No contributions recorded.</p>}
        </div>}
      </aside>
    </div>

    {modal === 'case' && <Modal title="Create private support case" close={() => setModal(null)}><form className="modal-form" onSubmit={createCase}>
      <label>Learner<select required value={caseStudentId} onChange={event => { setCaseStudentId(event.target.value); setRequirementId(''); setTargetAmount(''); setGeneralOutstanding(0); setModalError(''); }}><option value="">Select learner</option>{students.map(student => <option key={student.id} value={student.id}>{student.admission_no} · {student.full_name}</option>)}</select></label>
      <label>Obligation being supported<select value={requirementId} disabled={!caseStudentId || obligationsLoading} onChange={event => chooseRequirement(event.target.value)}><option value="">{obligationsLoading ? 'Loading verified balance…' : `School fees / general balance · ${money(generalOutstanding)} outstanding`}</option>{requirements.map(item => <option key={item.id} value={item.id}>{item.requirement_name} · {money(item.outstanding_amount)} outstanding</option>)}</select><small>Choosing a requirement links every verified contribution to that exact obligation.</small></label>
      <label>Need category<select name="need_category"><option value="fees">School fees</option><option value="examination">Examination</option><option value="uniform">Uniform</option><option value="learning_materials">Learning materials</option><option value="meals">Meals</option><option value="transport">Transport</option><option value="other">Other</option></select></label>
      <label>Public campaign title<input name="title" minLength={4} required/></label>
      <label>Target amount (UGX)<input type="number" min="1" max={obligationLimit || undefined} required value={targetAmount} onChange={event => { setTargetAmount(event.target.value); setModalError(''); }}/><small>{caseStudentId && !obligationsLoading ? `${money(obligationLimit)} is the maximum verified amount for this obligation.` : 'Select a learner to load the verified amount.'}</small></label>
      <label>Anonymous public summary<textarea name="public_summary" minLength={20} required placeholder="Describe the verified need without a name, admission number, image or identifying family detail."/></label>
      {modalError && <div className="form-error modal-error" role="alert">{modalError}</div>}
      <div className="notice">Targets above the learner&apos;s live obligation and identifying public text are rejected.</div>
      <footer><button type="button" className="btn" onClick={() => setModal(null)}>Cancel</button><button className="btn primary" disabled={busy || obligationsLoading || !obligationLimit || Number(targetAmount) <= 0 || Number(targetAmount) > obligationLimit}>{busy ? 'Creating…' : 'Create case'}</button></footer>
    </form></Modal>}

    {modal === 'consent' && selected && <Modal title="Record scoped guardian consent" close={() => setModal(null)}><form className="modal-form" onSubmit={consent}>
      <label>Linked guardian<select name="guardian_link_id" required><option value="">Select guardian</option>{selected.guardians.map(guardian => <option key={guardian.id} value={guardian.id}>{guardian.name} · {guardian.relationship}</option>)}</select></label>
      <label>Consent evidence<select name="method"><option value="signed_form">Signed form</option><option value="witnessed_in_person">Witnessed in person</option><option value="otp">Verified OTP</option></select></label>
      <label>Learner assent<select name="child_assent_status"><option value="agreed">Learner agreed</option><option value="not_applicable">Not applicable</option><option value="unable_to_express">Unable to express</option><option value="declined">Learner declined</option></select></label>
      <label className="checkbox-row"><input type="checkbox" name="gemma_processing" defaultChecked={Boolean(gemma?.configured)}/> Allow privacy-safe Gemma review of anonymous facts</label>
      <label className="checkbox-row"><input type="checkbox" name="cross_border_processing" defaultChecked={Boolean(gemma?.configured)}/> Allow processing outside Uganda required for Gemma</label>
      {modalError && <div className="form-error modal-error" role="alert">{modalError}</div>}
      <div className="notice">Anonymous publication is always recorded. Gemma and cross-border processing are optional, separate choices. Gemma never sees the learner name and never makes the publication decision.</div>
      <footer><button type="button" className="btn" onClick={() => setModal(null)}>Cancel</button><button className="btn primary" disabled={busy}>Record consent</button></footer>
    </form></Modal>}

    {modal === 'review' && selected && <Modal title="Run Gemma review" close={() => setModal(null)}><form className="modal-form" onSubmit={review}>
      <p>Gemma receives only the anonymous campaign code, need category, target, rule-based risk and draft public summary. A school owner still decides publication.</p>
      <p>{gemma?.configured ? `Model ${gemma.model} is configured on the server.` : 'GEMINI_API_KEY is missing. Start the API with a Google AI Studio key before running this review.'}</p>
      <label>Optional redacted evidence image<input type="file" name="evidence" accept="image/jpeg,image/png,image/webp"/></label>
      <label className="checkbox-row"><input type="checkbox" name="evidence_redacted"/> I confirm names, faces, admission numbers and contacts are redacted</label>
      {modalError && <div className="form-error modal-error" role="alert">{modalError}</div>}
      <footer><button type="button" className="btn" onClick={() => setModal(null)}>Cancel</button><button className="btn primary" disabled={busy || !gemma?.configured}>{busy ? 'Reviewing…' : 'Run text-only or image review'}</button></footer>
    </form></Modal>}

    {modal === 'proof' && selected && <Modal title="Add public proof update" close={() => setModal(null)}><form className="modal-form" onSubmit={proof}>
      <label>Proof type<select name="attestation_type"><option value="fulfilment">Obligation fulfilled</option><option value="enrolment">Enrolment continuity</option><option value="guardian_acknowledgement">Guardian acknowledgement</option><option value="independent_audit">Independent audit</option></select></label>
      <label>Attendance band<select name="attendance_band"><option value="">Not applicable</option><option value="below_50">Below 50%</option><option value="50_to_69">50–69%</option><option value="70_to_79">70–79%</option><option value="80_to_89">80–89%</option><option value="90_plus">90%+</option></select></label>
      <label>Public statement<textarea name="statement" minLength={10} required placeholder="Anonymous, factual and independently checkable update."/></label>
      {modalError && <div className="form-error modal-error" role="alert">{modalError}</div>}
      <footer><button type="button" className="btn" onClick={() => setModal(null)}>Cancel</button><button className="btn primary" disabled={busy}>Publish proof</button></footer>
    </form></Modal>}
  </>;
}

function Modal({ title, close, children }:{title:string;close:()=>void;children:React.ReactNode}) {
  return <div className="modal-backdrop"><section className="modal"><header><h2>{title}</h2><button onClick={close}><X/></button></header>{children}</section></div>;
}

function fileBase64(file:File):Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',')[1] ?? '');
    reader.onerror = () => reject(new Error('Evidence image could not be read.'));
    reader.readAsDataURL(file);
  });
}

async function apiBody<T>(response:Response):Promise<T> {
  const text = await response.text();
  if (!text) return {} as T;
  try {
    return JSON.parse(text) as T;
  } catch {
    throw new Error(`The service returned an invalid response (${response.status}). Please retry.`);
  }
}

function apiError(detail:unknown, status:number):string {
  if (typeof detail === 'string' && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const messages = detail.flatMap(item => {
      if (!item || typeof item !== 'object') return [];
      const issue = item as {loc?:unknown;msg?:unknown};
      const field = Array.isArray(issue.loc) ? String(issue.loc.at(-1) ?? '').replaceAll('_', ' ') : '';
      const message = typeof issue.msg === 'string' ? issue.msg : '';
      return message ? [`${field ? `${field}: ` : ''}${message}`] : [];
    });
    if (messages.length) return messages.join(' · ');
  }
  return `The action could not be completed (${status}). Check the entered information and try again.`;
}
