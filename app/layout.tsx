import type { Metadata } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import './globals.css';

const geistSans = Geist({ variable: '--font-geist-sans', subsets: ['latin'] });
const geistMono = Geist_Mono({ variable: '--font-geist-mono', subsets: ['latin'] });

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? 'http://localhost:3000'),
  title: 'CodeAtlas — Ask your codebase',
  description: 'A local-first, evidence-grounded RAG copilot for understanding software repositories.',
  openGraph: {
    title: 'CodeAtlas — Ask your codebase',
    description: 'Follow repository evidence from question to exact files, symbols, and line ranges.',
    type: 'website',
    images: [{ url: '/og.png', width: 1672, height: 941, alt: 'CodeAtlas — Ask your codebase. Follow the evidence.' }],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'CodeAtlas — Ask your codebase',
    description: 'Follow repository evidence from question to exact files, symbols, and line ranges.',
    images: ['/og.png'],
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable}`}>{children}</body>
    </html>
  );
}
