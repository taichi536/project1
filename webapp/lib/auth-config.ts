import type { NextAuthConfig } from 'next-auth';

// Edge Runtime対応：DBを使わない設定のみ（middleware用）
export const authConfig: NextAuthConfig = {
  providers: [],
  pages: { signIn: '/login' },
  session: { strategy: 'jwt' },
  callbacks: {
    authorized({ auth, request: { nextUrl } }) {
      const isLoggedIn = !!auth?.user;
      const isLoginPage = nextUrl.pathname === '/login';
      const isApiAuth = nextUrl.pathname.startsWith('/api/auth');

      if (isApiAuth) return true;
      if (isLoginPage) return true;
      return isLoggedIn;
    },
  },
};
