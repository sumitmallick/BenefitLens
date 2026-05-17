import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { QueryProvider } from "@/components/QueryProvider";
import { AuthProvider } from "@/lib/auth";
import { LayoutShell } from "@/components/LayoutShell";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

export const metadata: Metadata = {
  title: {
    default: "ClaimsIQ — Insurance Claims Management",
    template: "%s | ClaimsIQ",
  },
  description: "Enterprise-grade insurance claims adjudication and management platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="min-h-screen" style={{ fontFamily: "'Inter', system-ui, sans-serif" }}>
        <QueryProvider>
          <AuthProvider>
            <LayoutShell>{children}</LayoutShell>
          </AuthProvider>
        </QueryProvider>
      </body>
    </html>
  );
}
