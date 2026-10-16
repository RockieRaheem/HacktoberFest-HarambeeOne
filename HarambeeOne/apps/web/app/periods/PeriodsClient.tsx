'use client';

import { CalendarDays, CheckCircle2, Edit3, LoaderCircle, LockKeyhole, Plus, Trash2, X } from 'lucide-react';
import { FormEvent, useEffect, useMemo, useState } from 'react';
import { PageHeader } from '@/components/ui';
import { AcademicPeriod, clearPeriods, getAcademicPeriods, selectPeriod } from '@/lib/period';
import { getPrimarySchool, School } from '@/lib/school';

const API = '/api/backend';
type TermDraft = { name: string; opening_date: string; due_date: string; closing_date: string };
const blankTerms = (): TermDraft[] => ['Term 1', 'Term 2', 'Term 3'].map(name => ({ name, opening_date: '', due_date: '', closing_date: '' }));

export default function PeriodsClient() {
  const [school, setSchool] = useState<School | null>(null);
  const [periods, setPeriods] = useState<AcademicPeriod[]>([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<AcademicPeriod | null>(null);
  const [terms, setTerms] = useState<TermDraft[]>(blankTerms);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  async function load() {
    setLoading(true); setError(''); clearPeriods();
    try {
      const [institution, rows] = await Promise.all([getPrimarySchool(), getAcademicPeriods()]);
      setSchool(institution); setPeriods(rows);
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Calendar unavailable'); }
    finally { setLoading(false); }
  }
  useEffect(() => { load(); }, []);
  const operational = useMemo(() => periods.find(item => item.is_operational), [periods]);

  async function createYear(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!school) return; setSaving(true); setError('');
    const form = new FormData(event.currentTarget);
    const year = Number(form.get('year'));
    const response = await fetch(`${API}/api/v1/academic-years`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ school_id: school.id, name: form.get('name'), year, start_date: form.get('start_date'), end_date: form.get('end_date'), periods: terms.map((term, index) => ({ ...term, sequence: index + 1 })) }) });
    if (!response.ok) { const body = await response.json(); setError(typeof body.detail === 'string' ? body.detail : 'Check the calendar dates.'); setSaving(false); return; }
    setOpen(false); setTerms(blankTerms()); setSaving(false); await load();
  }

  async function transition(period: AcademicPeriod, status: 'open'|'closing'|'closed') {
    let reason: string | undefined;
    if (period.status === 'closed') { reason = window.prompt('Why is this closed period being reopened?')?.trim(); if (!reason) return; }
    const response = await fetch(`${API}/api/v1/academic-periods/${period.id}/transition`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status, reason }) });
    if (!response.ok) { const body = await response.json(); setError(body.detail ?? 'Unable to change period status.'); return; }
    clearPeriods(); await selectPeriod(period.id); await load();
  }

  async function remove(period: AcademicPeriod) {
    if (!window.confirm(`Delete unused draft period “${period.name}”?`)) return;
    const response = await fetch(`${API}/api/v1/academic-periods/${period.id}`, { method: 'DELETE' });
    if (!response.ok) { const body = await response.json(); setError(body.detail ?? 'Unable to delete period.'); return; }
    await load();
  }

  async function correct(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!editing) return; setSaving(true);
    const form = new FormData(event.currentTarget);
    const response = await fetch(`${API}/api/v1/academic-periods/${editing.id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: form.get('name'), opening_date: form.get('opening_date'), due_date: form.get('due_date'), closing_date: form.get('closing_date') }) });
    if (!response.ok) { const body = await response.json(); setError(body.detail ?? 'Unable to save correction.'); setSaving(false); return; }
    setEditing(null); setSaving(false); await load();
  }

  if (loading) return <div className="page-state"><LoaderCircle className="spin"/><h1>Loading academic calendar</h1><p>Checking operational and historical periods.</p></div>;
  return <>
    <PageHeader eyebrow="Control · Academic calendar" title="Academic periods" description="Open one working term, preserve closed history, and use the same period throughout the bursar workspace." actions={<button className="btn primary" onClick={() => setOpen(true)}><Plus size={16}/> New academic year</button>} />
    {error && <div className="notice period-error">{error}<button onClick={() => setError('')}><X size={15}/></button></div>}
    <section className="metric-grid period-metrics"><div className="metric-card"><CalendarDays/><span>Configured periods</span><strong>{periods.length}</strong><small>Across {new Set(periods.map(item => item.academic_year_id)).size} academic years</small></div><div className="metric-card"><CheckCircle2/><span>Operational period</span><strong>{operational?.name ?? 'Not opened'}</strong><small>{operational?.academic_year_name ?? 'Open a draft period to begin work'}</small></div><div className="metric-card"><LockKeyhole/><span>Closed history</span><strong>{periods.filter(item => item.status === 'closed').length}</strong><small>Protected against ordinary changes</small></div></section>
    <section className="panel period-register"><header className="panel-title"><div><span>Calendar register</span><h2>Terms and lifecycle</h2></div></header>{!periods.length ? <div className="empty-register"><CalendarDays/><strong>No academic year yet</strong><span>Create the school calendar before registering term activity.</span></div> : <div className="table-wrap"><table className="data-table"><thead><tr><th>Academic year</th><th>Period</th><th>Dates</th><th>Payment due</th><th>Status</th><th>Activity</th><th>Actions</th></tr></thead><tbody>{periods.map(period => <tr key={period.id}><td><strong>{period.academic_year_name}</strong><small>{period.academic_year}</small></td><td>{period.name}</td><td>{period.opening_date} — {period.closing_date}</td><td>{period.due_date}</td><td><span className={`status ${period.status}`}>{period.status}</span></td><td>{period.activity_count} records</td><td><div className="row-actions"><button title="Correct period" onClick={() => setEditing(period)} disabled={period.status === 'closed'}><Edit3 size={15}/></button>{period.status === 'draft' && <button onClick={() => transition(period, 'open')}>Open</button>}{period.status === 'open' && <button onClick={() => transition(period, 'closing')}>Start closing</button>}{period.status === 'closing' && <button onClick={() => transition(period, 'closed')}>Close</button>}{period.status === 'closed' && school?.role === 'owner' && <button onClick={() => transition(period, 'open')}>Reopen</button>}{period.status === 'draft' && <button title="Delete draft" onClick={() => remove(period)}><Trash2 size={15}/></button>}</div></td></tr>)}</tbody></table></div>}</section>
    {open && <div className="modal-backdrop"><section className="modal registration-modal"><header><div><h2>Create academic year</h2><p>Ugandan schools commonly use three terms. Keep, rename, add, or remove periods to match this school.</p></div><button onClick={() => setOpen(false)}><X size={20}/></button></header><form className="modal-form" onSubmit={createYear}><div className="form-grid"><label>Calendar year<input name="year" type="number" min="2000" max="2100" required /></label><label>Display name<input name="name" placeholder="2027 Academic Year" required /></label><label>Year opens<input name="start_date" type="date" required /></label><label>Year closes<input name="end_date" type="date" required /></label></div><div className="period-builder"><div className="form-section-title"><h3>School periods</h3><button type="button" className="btn compact" onClick={() => setTerms(items => [...items, {name:`Period ${items.length + 1}`,opening_date:'',due_date:'',closing_date:''}])}><Plus size={14}/> Add period</button></div>{terms.map((term, index) => <div className="period-draft" key={index}><strong>{index + 1}</strong><label>Name<input value={term.name} onChange={event => setTerms(items => items.map((item, i) => i === index ? {...item,name:event.target.value} : item))} required /></label><label>Opens<input type="date" value={term.opening_date} onChange={event => setTerms(items => items.map((item, i) => i === index ? {...item,opening_date:event.target.value} : item))} required /></label><label>Payment due<input type="date" value={term.due_date} onChange={event => setTerms(items => items.map((item, i) => i === index ? {...item,due_date:event.target.value} : item))} required /></label><label>Closes<input type="date" value={term.closing_date} onChange={event => setTerms(items => items.map((item, i) => i === index ? {...item,closing_date:event.target.value} : item))} required /></label>{terms.length > 1 && <button type="button" onClick={() => setTerms(items => items.filter((_, i) => i !== index))}><Trash2 size={15}/></button>}</div>)}</div><footer><button type="button" className="btn" onClick={() => setOpen(false)}>Cancel</button><button className="btn primary" disabled={saving}>{saving ? 'Creating…' : 'Create calendar'}</button></footer></form></section></div>}
    {editing && <div className="modal-backdrop"><section className="modal"><header><div><h2>Correct period</h2><p>Corrections are audited. Closed periods must be reopened first.</p></div><button onClick={() => setEditing(null)}><X size={20}/></button></header><form className="modal-form" onSubmit={correct}><label>Period name<input name="name" defaultValue={editing.name} required /></label><label>Opening date<input name="opening_date" type="date" defaultValue={editing.opening_date} required /></label><label>Payment due date<input name="due_date" type="date" defaultValue={editing.due_date} required /></label><label>Closing date<input name="closing_date" type="date" defaultValue={editing.closing_date} required /></label><footer><button type="button" className="btn" onClick={() => setEditing(null)}>Cancel</button><button className="btn primary" disabled={saving}>Save correction</button></footer></form></section></div>}
  </>;
}
