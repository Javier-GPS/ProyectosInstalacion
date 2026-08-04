import type { Metadata } from "next";
import { headers } from "next/headers";
import "./globals.css";

export async function generateMetadata(): Promise<Metadata> {
  const incomingHeaders = await headers();
  const host = incomingHeaders.get("x-forwarded-host") ?? incomingHeaders.get("host") ?? "localhost:3000";
  const protocol = incomingHeaders.get("x-forwarded-proto") ?? (host.startsWith("localhost") ? "http" : "https");
  const origin = `${protocol}://${host}`;
  const description = "Diseño inverso de distribuciones fotométricas viarias dentro de Salvi Studio.";

  return {
    title: "SALVI Studio · Road LDT Designer",
    description,
    openGraph: {
      title: "SALVI STUDIO · ROAD LDT DESIGNER",
      description,
      type: "website",
      images: [{ url: `${origin}/og.png`, width: 1536, height: 1024, alt: "SALVI Studio Road LDT Designer" }],
    },
    twitter: {
      card: "summary_large_image",
      title: "SALVI STUDIO · ROAD LDT DESIGNER",
      description,
      images: [`${origin}/og.png`],
    },
  };
}

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}
