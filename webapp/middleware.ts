import NextAuth from 'next-auth';
import { authConfig } from './lib/auth-config';

const { auth } = NextAuth(authConfig);

export default auth((req) => {
  const isLoggedIn = !!req.auth;
  const { pathname } = req.nextUrl;

  // 認証不要ページ
  if (pathname.startsWith('/api/auth') || pathname === '/landing') {
    return;
  }

  // 未ログインはランディングページかログインページへ
  if (!isLoggedIn) {
    if (pathname === '/login') return;
    return Response.redirect(new URL('/landing', req.url));
  }

  // ログイン済みでログイン・ランディングページにアクセスしたらダッシュボードへ
  if (isLoggedIn && (pathname === '/login' || pathname === '/landing')) {
    return Response.redirect(new URL('/', req.url));
  }
});

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico|public/).*)'],
};
