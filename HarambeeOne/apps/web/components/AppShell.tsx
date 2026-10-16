'use client';

import Image from 'next/image';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { AlertTriangle, BarChart3, BookOpen, CalendarDays, ChevronDown, ClipboardCheck, ExternalLink, FileUp, GraduationCap, HandHeart, LayoutDashboard, ListChecks, LogOut, Menu, ReceiptText, Settings, ShieldCheck, Users, WalletCards, X } from 'lucide-react';
import { useState } from 'react';
import { useEffect } from 'react';
import { clearPrimarySchool, getPrimarySchool } from '@/lib/school';
import { AcademicPeriod, clearPeriods, getAcademicPeriods, getSelectedPeriod, selectPeriod } from '@/lib/period';
import { createClient } from '@/lib/supabase/client';

const navGroups = [
  { label: 'Overview', items: [
    { label: 'Bursar command', href: '/dashboard', icon: LayoutDashboard },
  ]},
  { label: 'Learners', items: [
    { label: 'Student ledgers', href: '/students', icon: Users },
    { label: 'Import learners', href: '/students/import', icon: FileUp },
    { label: 'Classes & streams', href: '/classes', icon: BookOpen },
  ]},
  { label: 'Finance', items: [
    { label: 'Fees & installments', href: '/fees', icon: ReceiptText },
    { label: 'Requirements', href: '/requirements', icon: ClipboardCheck },
    { label: 'Payment register', href: '/payments', icon: WalletCards },
    { label: 'Reconciliation', href: '/reconciliation', icon: ListChecks },
    { label: 'Overdue accounts', href: '/arrears', icon: AlertTriangle },
    { label: 'Financial reports', href: '/reports', icon: BarChart3 },
  ]},
  { label: 'Support', items: [
    { label: 'Manage campaigns', href: '/support-admin', icon: HandHeart },
    { label: 'Public donor portal', href: '/support', icon: ExternalLink },
  ]},
  { label: 'Control', items: [
    { label: 'Academic periods', href: '/periods', icon: CalendarDays },
    { label: 'Audit trail', href: '/audit', icon: ShieldCheck },
  ]},
] as const;

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const authRoute = pathname === '/login' || pathname === '/signup' || pathname === '/onboarding' || pathname.startsWith('/auth/');
  const publicRoute = pathname === '/support' || pathname.startsWith('/support/');
  const portalRoute = pathname === '/workspace' || pathname === '/welcome' || pathname === '/guardian' || pathname.startsWith('/guardian/') || pathname === '/donor' || pathname.startsWith('/donor/');
  const [open, setOpen] = useState(false);
  const [schoolName, setSchoolName] = useState('Set up institution');
  const [userName, setUserName] = useState('Bursar');
  const [userEmail, setUserEmail] = useState('');
  const [userRole, setUserRole] = useState('Bursar');
  const [userOpen, setUserOpen] = useState(false);
  const [periods, setPeriods] = useState<AcademicPeriod[]>([]);
  const [periodId, setPeriodId] = useState('');
  useEffect(() => {
    if (authRoute || publicRoute || portalRoute) return;
    getPrimarySchool().then(async school => {
      setSchoolName(school.name); if (school.role) setUserRole(school.role);
      const rows = await getAcademicPeriods(); setPeriods(rows);
      if (rows.length) setPeriodId((await getSelectedPeriod()).id);
    }).catch(() => { if (pathname !== '/periods') window.location.assign('/onboarding'); });
    const supabase = createClient();
    const loadUser = async () => {
      const { data } = await supabase.auth.getUser();
      if (data.user) {
        setUserName(String(data.user.user_metadata.full_name || data.user.email?.split('@')[0] || 'Bursar'));
        setUserEmail(data.user.email ?? '');
      }
    };
    loadUser();
    const { data } = supabase.auth.onAuthStateChange(() => loadUser());
    return () => data.subscription.unsubscribe();
  }, [authRoute, pathname, portalRoute, publicRoute]);

  async function signOut() {
    clearPrimarySchool();
    clearPeriods();
    await createClient().auth.signOut();
    window.location.assign('/login');
  }

  async function changePeriod(value: string) {
    await selectPeriod(value); setPeriodId(value); window.location.reload();
  }

  if (authRoute || publicRoute || portalRoute) return <>{children}</>;
  const initials = userName.split(/\s+/).filter(Boolean).slice(0, 2).map(part => part[0]).join('').toUpperCase() || 'BU';
  return <div className="app-shell">
    {open && <button className="nav-scrim" aria-label="Close navigation" onClick={() => setOpen(false)} />}
    <aside className={`sidebar ${open ? 'is-open' : ''}`}>
      <div className="institution">
        <Image src="/harambeeone-logo.png" width={42} height={42} alt="HarambeeOne" priority />
        <div><strong>HarambeeOne</strong><span>Bursar workspace</span></div>
        <button className="sidebar-close" onClick={() => setOpen(false)} aria-label="Close navigation"><X size={20} /></button>
      </div>
      <Link href="/institution" className="school-switcher"><span className="school-mark">{schoolName.slice(0, 2).toUpperCase()}</span><span><small>Current institution</small><strong>{schoolName}</strong></span><ChevronDown size={16} /></Link>
      <nav className="primary-nav" aria-label="Primary navigation">
        {navGroups.map(group => <section className="nav-group" key={group.label} aria-labelledby={`nav-${group.label.toLowerCase()}`}>
          <span className="nav-label" id={`nav-${group.label.toLowerCase()}`}>{group.label}</span>
          {group.items.map(({ label, href, icon: Icon }) => {
            const active = pathname === href || (href !== '/dashboard' && pathname.startsWith(`${href}/`));
            return <Link className={active ? 'active' : ''} aria-current={active ? 'page' : undefined} href={href} key={href} onClick={() => setOpen(false)}><Icon size={17} strokeWidth={1.8} /><span>{label}</span></Link>;
          })}
        </section>)}
      </nav>
      <div className="sidebar-foot"><div className="sidebar-tools"><Link href="/institution"><Settings size={17} /> Institution settings</Link></div><div className="gateway"><span><i />Services</span><strong>Online</strong></div></div>
    </aside>
    <div className="workspace">
      <header className="top-nav">
        <button className="menu-button" onClick={() => setOpen(true)} aria-label="Open navigation"><Menu size={22} /></button>
        <div className="mobile-brand"><GraduationCap size={20} /><strong>HarambeeOne</strong></div>
        <div className="workspace-label"><span>School finance</span><strong>Bursar workspace</strong></div>
        {periods.length ? <label className="term-selector"><span>Academic period</span><select aria-label="Selected academic period" value={periodId} onChange={event => changePeriod(event.target.value)}>{periods.map(period => <option value={period.id} key={period.id}>{period.name} · {period.academic_year_name}{period.is_operational ? ' · Current' : ''}</option>)}</select><ChevronDown size={15} /></label> : <Link className="term-selector period-setup" href="/periods"><span>Academic period</span><strong>Set up calendar</strong><ChevronDown size={15}/></Link>}
        <Link className="quick-action" href="/payments"><ReceiptText size={17} /> Record payment</Link>
        <div className="user-area"><button className="user-menu" onClick={() => setUserOpen(value => !value)} aria-expanded={userOpen}><span>{initials}</span><div><strong>{userName}</strong><small>{userEmail || `${userRole} · Active`}</small></div><ChevronDown size={14} /></button>{userOpen && <div className="user-dropdown"><div><strong>{userName}</strong><span>{userEmail || userRole}</span></div><button onClick={signOut}><LogOut size={16}/>Sign out</button></div>}</div>
      </header>
      <main className="page-canvas">{children}</main>
    </div>
  </div>;
}
