'use client';

import Image from 'next/image';
import Link from 'next/link';
import { LogOut, PanelsTopLeft } from 'lucide-react';
import { createClient } from '@/lib/supabase/client';

export default function PortalShell({
  label,
  children,
}:{
  label:string;
  children:React.ReactNode;
}) {
  async function signOut() {
    await createClient().auth.signOut();
    window.location.assign('/login');
  }
  return <div className="portal-page">
    <header className="portal-header">
      <Link href="/workspace" className="portal-brand"><Image src="/harambeeone-logo.png" width={38} height={38} alt=""/><span><strong>HarambeeOne</strong><small>{label}</small></span></Link>
      <nav><Link href="/workspace"><PanelsTopLeft size={16}/>Workspaces</Link><button onClick={signOut}><LogOut size={16}/>Sign out</button></nav>
    </header>
    <main className="portal-main">{children}</main>
  </div>;
}
