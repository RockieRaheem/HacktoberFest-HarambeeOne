'use client';

import Image from 'next/image';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Eye, EyeOff, LoaderCircle, LockKeyhole, Mail } from 'lucide-react';
import { FormEvent, useState } from 'react';
import { createClient } from '@/lib/supabase/client';

type AuthFormProps = {
  mode: 'login' | 'signup';
  nextPath?: string;
  initialError?: string;
};

function GoogleLogo() {
  return <svg className="google-logo" viewBox="0 0 18 18" aria-hidden="true">
    <path fill="#4285F4" d="M17.64 9.205c0-.638-.057-1.252-.164-1.841H9v3.481h4.844a4.14 4.14 0 0 1-1.797 2.716v2.259h2.909c1.703-1.568 2.684-3.878 2.684-6.615Z" />
    <path fill="#34A853" d="M9 18c2.43 0 4.468-.806 5.956-2.18l-2.909-2.259c-.806.54-1.835.859-3.047.859-2.344 0-4.328-1.585-5.037-3.714H.956v2.332A9 9 0 0 0 9 18Z" />
    <path fill="#FBBC05" d="M3.963 10.706A5.41 5.41 0 0 1 3.682 9c0-.592.102-1.168.281-1.706V4.962H.956A9 9 0 0 0 0 9c0 1.452.347 2.827.956 4.038l3.007-2.332Z" />
    <path fill="#EA4335" d="M9 3.58c1.321 0 2.507.454 3.441 1.346l2.581-2.581C13.464.892 11.427 0 9 0A9 9 0 0 0 .956 4.962l3.007 2.332C4.672 5.165 6.656 3.58 9 3.58Z" />
  </svg>;
}

export default function AuthForm({ mode, nextPath = '/dashboard', initialError = '' }: AuthFormProps) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [googleBusy, setGoogleBusy] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState(initialError);
  const [notice, setNotice] = useState('');
  const isLogin = mode === 'login';

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError('');
    setNotice('');

    const form = new FormData(event.currentTarget);
    const email = String(form.get('email') ?? '').trim();
    const password = String(form.get('password') ?? '');

    try {
      const supabase = createClient();
      if (isLogin) {
        const { error: signInError } = await supabase.auth.signInWithPassword({ email, password });
        if (signInError) throw signInError;
        router.replace(nextPath);
        router.refresh();
        return;
      }

      const fullName = String(form.get('fullName') ?? '').trim();
      const confirmation = String(form.get('confirmation') ?? '');
      if (password !== confirmation) throw new Error('The passwords do not match.');
      if (password.length < 8) throw new Error('Use at least 8 characters for your password.');

      const callbackUrl = `${window.location.origin}/auth/callback?next=${encodeURIComponent(nextPath)}`;
      const { data, error: signUpError } = await supabase.auth.signUp({
        email,
        password,
        options: { data: { full_name: fullName }, emailRedirectTo: callbackUrl },
      });
      if (signUpError) throw signUpError;
      if (data.session) {
        router.replace(nextPath);
        router.refresh();
      } else {
        setNotice('Check your email to confirm your account, then return here to sign in.');
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Authentication could not be completed.');
    } finally {
      setBusy(false);
    }
  }

  function continueWithGoogle() {
    setGoogleBusy(true);
    setError('');
    window.location.assign(`/auth/google?next=${encodeURIComponent(nextPath)}`);
  }

  return <main className="auth-page">
    <section className="auth-story" aria-label="About HarambeeOne">
      <Link className="auth-brand" href="/">
        <Image src="/harambeeone-logo.png" width={48} height={48} alt="" priority />
        <span><strong>HarambeeOne</strong><small>School finance, clearly managed</small></span>
      </Link>
      <div className="auth-story-copy">
        <span className="auth-kicker">Built for the bursar&apos;s office</span>
        <h1>Every learner account, payment and balance in one dependable place.</h1>
        <p>Keep daily collections organised, issue accountable receipts, and understand what the school is owed without adding complexity to the work.</p>
      </div>
      <footer>Secure access powered by Supabase</footer>
    </section>

    <section className="auth-panel">
      <div className="auth-card">
        <div className="auth-heading">
          <span>{isLogin ? 'Welcome back' : 'Create your account'}</span>
          <h2>{isLogin ? 'Sign in to your workspace' : 'Start using HarambeeOne'}</h2>
          <p>{isLogin ? 'Use your work email to continue.' : 'First secure your account, then configure the school levels and classes.'}</p>
        </div>

        {error && <div className="auth-message error" role="alert">{error}</div>}
        {notice && <div className="auth-message success" role="status">{notice}</div>}

        <button className="google-button" type="button" onClick={continueWithGoogle} disabled={googleBusy || busy}>
          {googleBusy ? <LoaderCircle className="spin" size={18} /> : <GoogleLogo />}
          Continue with Google
        </button>
        <div className="auth-divider"><span>or use email</span></div>

        <form className="auth-form" onSubmit={submit}>
          {!isLogin && <label>Full name<input name="fullName" autoComplete="name" required placeholder="Your full name" /></label>}
          <label>Email address<div className="auth-input"><Mail size={17} /><input name="email" type="email" autoComplete="email" required placeholder="name@school.ac.ug" /></div></label>
          <label>Password<div className="auth-input"><LockKeyhole size={17} /><input name="password" type={showPassword ? 'text' : 'password'} autoComplete={isLogin ? 'current-password' : 'new-password'} minLength={8} required placeholder="At least 8 characters" /><button type="button" onClick={() => setShowPassword(value => !value)} aria-label={showPassword ? 'Hide password' : 'Show password'}>{showPassword ? <EyeOff size={17} /> : <Eye size={17} />}</button></div></label>
          {!isLogin && <label>Confirm password<input name="confirmation" type={showPassword ? 'text' : 'password'} autoComplete="new-password" minLength={8} required placeholder="Repeat your password" /></label>}
          <button className="auth-submit" disabled={busy || googleBusy}>{busy && <LoaderCircle className="spin" size={18} />}{isLogin ? 'Sign in' : 'Create account'}</button>
        </form>

        <p className="auth-switch">{isLogin ? 'New to HarambeeOne?' : 'Already have an account?'} <Link href={isLogin ? '/signup' : '/login'}>{isLogin ? 'Create an account' : 'Sign in'}</Link></p>
        <p className="auth-terms">By continuing, you agree to protect learner and financial information entrusted to your account.</p>
      </div>
    </section>
  </main>;
}
