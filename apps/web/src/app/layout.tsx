import type { Metadata, Viewport } from 'next';
import { headers } from 'next/headers';
import './globals.css';
import { Providers } from '@/components/providers';

export const metadata: Metadata = {
  title: { default: 'ستاد کوینه‌پرو', template: '%s · ستاد کوینه‌پرو' },
  description: 'ستاد هلدینگ کوینه‌پرو',
  robots: { index: false, follow: false },
  icons: { icon: '/icon.svg' },
};

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
  themeColor: [
    { media: '(prefers-color-scheme: dark)', color: '#0B0D14' },
    { media: '(prefers-color-scheme: light)', color: '#F3EEE3' },
  ],
};

// Applies the saved theme before first paint (no flash). Night is the default.
const THEME_BOOT = `try{var t=localStorage.getItem('hq-theme');if(t==='day'||t==='night'){document.documentElement.dataset.theme=t}}catch(e){}`;

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const nonce = (await headers()).get('x-nonce') ?? undefined;
  return (
    <html lang="fa" dir="rtl" suppressHydrationWarning>
      <head>
        <script nonce={nonce} dangerouslySetInnerHTML={{ __html: THEME_BOOT }} />
      </head>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
