import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "AI 模拟面试",
  description: "华为 · 硬件技术工程师（射频技术方向）实习生 AI 面试平台",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col bg-neutral-950 text-neutral-100">
        <nav className="border-b border-neutral-800 px-6 py-3 flex items-center gap-6 text-sm">
          <Link href="/" className="font-semibold text-sky-400 hover:text-sky-300">
            🎤 AI 面试
          </Link>
          <Link href="/history" className="text-neutral-400 hover:text-neutral-200">
            历史记录
          </Link>
        </nav>
        <main className="flex-1">{children}</main>
      </body>
    </html>
  );
}
