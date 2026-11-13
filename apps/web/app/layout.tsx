import type { ReactNode } from 'react';
import './globals.css';

export const metadata = {
  title: { default: 'AgentSync', template: '%s · AgentSync' },
  description: 'Intelligent coordination and conflict prevention for AI agent teams.',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
