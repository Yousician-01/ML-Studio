import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ML Studio",
  description: "Visual ML. Real code. Reproducible experiments.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
