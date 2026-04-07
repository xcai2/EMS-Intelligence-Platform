import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import { Sidebar } from '@/components/layout/Sidebar';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'Flex Competitive Intelligence Platform | AI Powered',
  description: 'AI-powered competitive intelligence analysis for EMS companies - Analyze CapEx strategies, AI investments, and competitive dynamics',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <div className="flex h-screen min-w-0">
          <Sidebar />
          <main className="min-w-0 flex-1 overflow-auto bg-background text-foreground transition-colors">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
