import type { Metadata } from "next";
import "./globals.css";
import Sidebar from "@/components/Sidebar";
import SessionProvider from "@/components/SessionProvider";

export const metadata: Metadata = {
  title: "WorkFlow AI",
  description: "業務効率化AIアシスタント",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja" className="h-full">
      <body className="h-full flex bg-gray-50 text-gray-900 antialiased">
        <SessionProvider>
          <Sidebar />
          <main className="flex-1 overflow-auto p-8">{children}</main>
        </SessionProvider>
      </body>
    </html>
  );
}
