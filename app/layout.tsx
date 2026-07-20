import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PDP One | سامانه یکپارچه مدیریت",
  description: "نسخه آزمایشی سامانه مدیریت پروژه، قرارداد و مناقصات PDP One",
  other: { "codex-preview": "development" },
  icons: { icon: "/favicon.svg", shortcut: "/favicon.svg" },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="fa" dir="rtl"><body>{children}</body></html>;
}

