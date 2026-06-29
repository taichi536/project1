import NextAuth from 'next-auth';
import Credentials from 'next-auth/providers/credentials';
import { authConfig } from './auth-config';

export const { handlers, auth, signIn, signOut } = NextAuth({
  ...authConfig,
  providers: [
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

        const user = db.prepare(`SELECT * FROM users WHERE email = ?`).get(credentials.email) as {
          id: number; name: string; email: string; password_hash: string;
        } | undefined;

        if (!user) return null;
        const ok = await bcrypt.compare(credentials.password as string, user.password_hash);
        if (!ok) return null;
        return { id: String(user.id), name: user.name, email: user.email };
      },
    }),
  ],
});
