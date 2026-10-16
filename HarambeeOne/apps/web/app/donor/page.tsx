import Link from 'next/link';
import { redirect } from 'next/navigation';
import { HandHeart, ReceiptText, ShieldCheck } from 'lucide-react';
import PortalShell from '@/components/PortalShell';
import { authorizedBackendFetch } from '@/lib/api/server';

type Profile={display_name:string;show_public_name:boolean};

export default async function DonorPage(){
  const response=await authorizedBackendFetch('/api/v1/donor/profile');
  if(!response.ok)redirect('/welcome');
  const profile:Profile=await response.json();
  return <PortalShell label="Donor workspace"><section className="portal-intro"><span>Welcome, {profile.display_name}</span><h1>Support verified school obligations.</h1><p>Your dashboard will keep contributions, school-issued receipts and privacy-safe outcome updates together.</p></section><section className="donor-summary"><article><HandHeart/><span>Contributions</span><strong>None yet</strong><small>Authenticated contributions will appear here.</small></article><article><ReceiptText/><span>Receipts</span><strong>None yet</strong><small>Issued only after school settlement verification.</small></article><article><ShieldCheck/><span>Public name</span><strong>{profile.show_public_name?'Enabled':'Private'}</strong><small>Learner identity always stays private.</small></article></section><div className="portal-empty"><HandHeart/><h2>Choose a verified campaign</h2><p>Pending pledges do not increase campaign totals until the school confirms the funds.</p><Link className="btn primary" href="/support">Browse campaigns</Link></div></PortalShell>;
}
