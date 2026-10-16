'use client';

import { FormEvent, useEffect, useMemo, useState } from 'react';
import Image from 'next/image';
import { useRouter } from 'next/navigation';
import { Baby, Check, GraduationCap, LoaderCircle, School, ShieldCheck } from 'lucide-react';
import { getPrimarySchool, setPrimarySchool } from '@/lib/school';

const API = '/api/backend';
type Grade = {canonical_code:string; name:string};
type Template = {code:string; name:string; classes:Grade[]};
type Profile = {code:string; name:string; detail:string; programmes:string[]};
const profiles:Profile[] = [
  {code:'day_care', name:'Day care', detail:'Care programme without artificial academic classes', programmes:['day_care']},
  {code:'nursery', name:'Nursery / pre-primary', detail:'Baby, Middle and Top Class', programmes:['pre_primary']},
  {code:'primary', name:'Primary / junior school', detail:'Primary One through Primary Seven', programmes:['primary']},
  {code:'nursery_primary', name:'Nursery and primary', detail:'Baby Class through Primary Seven', programmes:['pre_primary', 'primary']},
  {code:'secondary_o', name:'O-Level secondary', detail:'Senior One through Senior Four', programmes:['lower_secondary']},
  {code:'secondary_full', name:'Full secondary', detail:'Senior One through Senior Six', programmes:['lower_secondary', 'upper_secondary']},
  {code:'mixed', name:'Mixed or custom school', detail:'Choose the exact programmes and classes offered', programmes:[]},
];

export default function OnboardingPage() {
  const router = useRouter();
  const [templates, setTemplates] = useState<Template[]>([]), [profile, setProfile] = useState(''), [programmes, setProgrammes] = useState<string[]>([]), [grades, setGrades] = useState<string[]>([]);
  const [streamMode, setStreamMode] = useState<'none'|'single'|'multiple'>('none'), [streams, setStreams] = useState('');
  const [loading, setLoading] = useState(true), [saving, setSaving] = useState(false), [error, setError] = useState('');
  useEffect(() => {
    getPrimarySchool().then(() => router.replace('/dashboard')).catch(() => {
      fetch(`${API}/api/v1/academic-structure/templates`).then(response => {
        if (!response.ok) throw new Error(); return response.json();
      }).then(setTemplates).catch(() => setError('School structure options could not be loaded.')).finally(() => setLoading(false));
    });
  }, [router]);

  const selectedTemplates = useMemo(() => templates.filter(item => programmes.includes(item.code)), [programmes, templates]);
  const availableGrades = selectedTemplates.flatMap(item => item.classes);
  function chooseProfile(item:Profile) {
    setProfile(item.code); setProgrammes(item.programmes);
    setGrades(templates.filter(template => item.programmes.includes(template.code)).flatMap(template => template.classes.map(grade => grade.canonical_code)));
  }
  function toggleProgramme(item:Template, checked:boolean) {
    setProfile('mixed');
    setProgrammes(current => checked ? [...current, item.code] : current.filter(code => code !== item.code));
    const codes = item.classes.map(grade => grade.canonical_code);
    setGrades(current => checked ? Array.from(new Set([...current, ...codes])) : current.filter(code => !codes.includes(code)));
  }
  async function submit(event:FormEvent<HTMLFormElement>) {
    event.preventDefault(); setSaving(true); setError('');
    const form = new FormData(event.currentTarget);
    const defaultStreams = streamMode === 'none' ? [] : streamMode === 'single' ? [streams.trim()].filter(Boolean) : streams.split(',').map(value => value.trim()).filter(Boolean);
    try {
      const response = await fetch('/api/current-school', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:form.get('name'), district:form.get('district') || null, emis_code:form.get('emis_code') || null, programme_codes:programmes, canonical_codes:grades, default_streams:defaultStreams})});
      const body = await response.json();
      if (!response.ok) { const detail = Array.isArray(body.detail) ? body.detail[0]?.msg : body.detail; throw new Error(detail || 'Institution setup could not be completed.'); }
      setPrimarySchool(body); router.replace('/dashboard'); router.refresh();
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Institution setup could not be completed.'); setSaving(false); }
  }
  const classProgrammeSelected = selectedTemplates.some(item => item.classes.length);
  const structureValid = programmes.length > 0 && (!classProgrammeSelected || grades.length > 0);

  return <main className="onboarding-page"><header className="onboarding-header"><div><Image src="/harambeeone-logo.png" width={42} height={42} alt="HarambeeOne"/><span><strong>HarambeeOne</strong><small>Institution setup</small></span></div><span><ShieldCheck size={15}/>Secure bursar onboarding</span></header>
    <form className="onboarding-shell" onSubmit={submit}><section className="onboarding-intro"><span>Account created · Step 2 of 2</span><h1>Tell us how your school is structured.</h1><p>Choose the closest Ugandan school profile. We attach the usual classes automatically, while leaving every level, name and stream editable.</p></section>
      {error && <div className="auth-message error" role="alert">{error}</div>}
      <section className="onboarding-section"><div className="onboarding-section-title"><span>1</span><div><h2>School profile</h2><p>This presets the programmes and usual classes; it does not lock the school into them.</p></div></div>{loading ? <div className="onboarding-loading"><LoaderCircle className="spin"/>Loading school structures…</div> : <div className="school-profile-grid">{profiles.map(item => <button type="button" key={item.code} className={profile === item.code ? 'selected' : ''} onClick={() => chooseProfile(item)}><span>{item.code === 'day_care' ? <Baby/> : item.code.includes('secondary') ? <GraduationCap/> : <School/>}</span><div><strong>{item.name}</strong><small>{item.detail}</small></div><Check/></button>)}</div>}</section>
      {profile && <><section className="onboarding-section"><div className="onboarding-section-title"><span>2</span><div><h2>Exact programmes and classes</h2><p>Remove levels the school does not currently offer. You can add, rename or delete them later.</p></div></div><div className="programme-toggles">{templates.map(item => <label key={item.code} className={programmes.includes(item.code) ? 'selected' : ''}><input type="checkbox" checked={programmes.includes(item.code)} onChange={event => toggleProgramme(item, event.target.checked)}/><span><strong>{item.name}</strong><small>{item.classes.length ? `${item.classes.length} standard classes` : 'No academic classes'}</small></span></label>)}</div>{availableGrades.length > 0 && <div className="onboarding-grades">{availableGrades.map(grade => <label key={grade.canonical_code} className={grades.includes(grade.canonical_code) ? 'selected' : ''}><input type="checkbox" checked={grades.includes(grade.canonical_code)} onChange={event => setGrades(current => event.target.checked ? [...current, grade.canonical_code] : current.filter(code => code !== grade.canonical_code))}/><strong>{grade.name}</strong><small>{grade.canonical_code}</small></label>)}</div>}</section>
        <section className="onboarding-section"><div className="onboarding-section-title"><span>3</span><div><h2>Institution details</h2><p>These details identify the school throughout every bursar register and report.</p></div></div><div className="onboarding-fields"><label>Registered school name<input name="name" required maxLength={160} placeholder="e.g. Kampala Junior School"/></label><label>District<input name="district" maxLength={80} placeholder="e.g. Kampala"/></label><label>EMIS code <small>Optional if not yet issued</small><input name="emis_code" maxLength={40}/></label><label>Initial stream structure<select value={streamMode} onChange={event => setStreamMode(event.target.value as typeof streamMode)}><option value="none">No streams</option><option value="single">One named stream per class</option><option value="multiple">Multiple streams per class</option></select></label>{streamMode !== 'none' && <label className="wide">{streamMode === 'single' ? 'Stream name' : 'Stream names'}<input required value={streams} onChange={event => setStreams(event.target.value)} placeholder={streamMode === 'single' ? 'Main' : 'East, West, Blue'}/><small>{streamMode === 'multiple' ? 'Separate stream names with commas.' : 'This can be changed independently for each class later.'}</small></label>}</div></section>
        <footer className="onboarding-actions"><div><strong>{programmes.length} programme{programmes.length === 1 ? '' : 's'} · {grades.length} class{grades.length === 1 ? '' : 'es'}</strong><span>Every page will use this institution and its selected structure.</span></div><button className="auth-submit" disabled={saving || !structureValid}>{saving && <LoaderCircle className="spin" size={18}/>}Create school workspace</button></footer></>}
    </form>
  </main>;
}
