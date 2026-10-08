import type { Metadata, Viewport } from "next";
import { ServiceWorkerRegistration } from "@/components/service-worker-registration";
import "./styles.css";

export const metadata: Metadata = {
  title: "3M — Assistant personnel",
  description: "Votre interface personnelle intelligente, privée et extensible.",
  manifest: "/manifest.webmanifest",
  appleWebApp: { capable: true, statusBarStyle: "black-translucent", title: "3M" },
  icons: { apple: "/icon.svg", icon: "/icon.svg" },
};

export const viewport: Viewport = {
  themeColor: "#07110f",
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="fr">
      <body>
        {children}
        <ServiceWorkerRegistration />
      </body>
    </html>
  );
}

