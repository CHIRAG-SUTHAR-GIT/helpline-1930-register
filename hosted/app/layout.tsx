import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "1930 Helpline Register",
  description: "Private call records with permanent details, editable remarks, and complete exports.",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
