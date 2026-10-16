import { createServerClient, type CookieOptions } from '@supabase/ssr';
import { NextResponse, type NextRequest } from 'next/server';
import { getSupabaseConfig } from '@/lib/supabase/config';

type PendingCookie = { name:string; value:string; options:CookieOptions };

function safeNext(value:string|null) {
  return value?.startsWith('/') && !value.startsWith('//') ? value : '/workspace';
}

function loginError(request:NextRequest, message:string) {
  const loginUrl = new URL('/login', request.nextUrl.origin);
  loginUrl.searchParams.set('error', message);
  return NextResponse.redirect(loginUrl);
}

export async function GET(request:NextRequest) {
  const providerError = request.nextUrl.searchParams.get('error_description');
  if (providerError) {
    console.error('[auth/callback] Provider rejected sign-in', providerError);
    return loginError(request, 'Google did not complete the sign-in. Please try again.');
  }

  const code = request.nextUrl.searchParams.get('code');
  if (!code) return loginError(request, 'The sign-in response was incomplete. Please try again.');

  const pendingCookies:PendingCookie[] = [];
  const { url, publishableKey } = getSupabaseConfig();
  const supabase = createServerClient(url, publishableKey, {
    cookies: {
      getAll: () => request.cookies.getAll(),
      setAll: cookies => { pendingCookies.push(...cookies); },
    },
  });
  const { error } = await supabase.auth.exchangeCodeForSession(code);
  if (error) {
    console.error('[auth/callback] Code exchange failed', error.code ?? 'exchange_failed', error.message);
    return loginError(request, 'Your Google sign-in session expired or could not be verified. Please start again.');
  }

  const response = NextResponse.redirect(new URL(safeNext(request.nextUrl.searchParams.get('next')), request.nextUrl.origin));
  pendingCookies.forEach(cookie => response.cookies.set(cookie.name, cookie.value, cookie.options));
  return response;
}
