import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ML Studio",
  description: "Visual ML. Real code. Reproducible experiments.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <div className="shell">
          <header>
            <span className="mark" aria-hidden="true">
              M
            </span>
            <span>ML Studio</span>
            <span className="local">Local workspace</span>
          </header>
          {children}
          <footer>
            ML Studio{" "}
            <span>Visual ML. Real code. Reproducible experiments.</span>
          </footer>
        </div>
      </body>
    </html>
  );
}
