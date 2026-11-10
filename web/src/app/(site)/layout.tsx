import Footer from "@/components/Footer";

export default function SiteLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <a className="skip" href="#main">
        Skip to content
      </a>
      <div className="grain" aria-hidden="true" />
      {children}
      <Footer />
    </>
  );
}
