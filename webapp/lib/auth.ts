import NextAuth from 'next-auth';
import Credentials from 'next-auth/providers/credentials';
import Google from 'next-auth/providers/google';
import { authConfig } from './auth-config';

export const { handlers, auth, signIn, signOut } = NextAuth({
  ...authConfig,
  providers: [
    Google({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
      authorization: {
        params: {
          scope: 'openid email profile https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send',
          access_type: 'offline',
          prompt: 'consent',
        },
      },
    }),
    Credentials({
      credentials: {
        email: { label: 'メール', type: 'email' },
        password: { label: 'パスワード', type: 'password' },
      },
      async authorize(credentials) {
        if (!credentials?.email || !credentials?.password) return null;

        const { getDb } = await import('./db');
        const bcrypt = await import('bcryptjs');
        const db = getDb();

        const user = db.prepare('SELECT * FROM users WHERE email = ?').get(credentials.email) as {
          id: number; name: string; email: string; password_hash: string;
        } | undefined;

        if (!user) return null;
        const ok = await bcrypt.compare(credentials.password as string, user.password_hash);
        if (!ok) return null;
        return { id: String(user.id), name: user.name, email: user.email };
      },
    }),
  ],
  callbacks: {
    async jwt({ token, account, user }) {
      if (account?.provider === 'google') {
        token.accessToken = account.access_token;
        token.refreshToken = account.refresh_token;
        token.accessTokenExpires = account.expires_at ? account.expires_at * 1000 : undefined;
      }
      if (user) token.id = user.id;
      return token;
    },
    async session({ session, token }) {
      session.user.id = token.id as string;
      session.accessToken = token.accessToken as string | undefined;
      if (token.accessToken) {
        try {
          const { getDb } = await import('./db');
          const db = getDb();
          const u = db.prepare('SELECT id FROM users WHERE email = ?').get(session.user.email!) as { id: number } | undefined;
          if (u) {
            db.prepare(`
              INSERT INTO user_tokens (user_id, google_access_token, google_refresh_token, google_token_expiry, updated_at)
              VALUES (?, ?, ?, ?, datetime('now','localtime'))
              ON CONFLICT(user_id) DO UPDATE SET
                google_access_token = excluded.google_access_token,
                google_refresh_token = COALESCE(excluded.google_refresh_token, google_refresh_token),
                google_token_expiry = excluded.google_token_expiry,
                updated_at = excluded.updated_at
            `).run(u.id, token.accessToken, token.refreshToken ?? null, token.accessTokenExpires ?? null);
            session.user.id = String(u.id);
          }
        } catch {}
      }
      return session;
    },
    async signIn({ account, profile }) {
      if (account?.provider === 'google' && profile?.email) {
        try {
          const { getDb } = await import('./db');
          const db = getDb();
          const existing = db.prepare('SELECT id FROM users WHERE email = ?').get(profile.email);
          if (!existing) {
            const count = (db.prepare('SELECT COUNT(*) as c FROM users').get() as { c: number }).c;
            const role = count === 0 ? 'admin' : 'member';
            db.prepare('INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)')
              .run(profile.name ?? profile.email, profile.email, '', role);
          }
        } catch {}
      }
      return true;
    },
  },
});
