import type { Metadata } from "next";
import Nav from "@/components/Nav";
import AppLoader from "@/components/app/AppLoader";

export const metadata: Metadata = {
  title: "Your window",
  description:
    "Find the cleanest hour today or tomorrow for a walk, a run, children's play, cycling, yoga or the commute, and when to open the windows at home. From India's government air monitors.",
  alternates: { canonical: "/app" },
};

export default function AppPage() {
  return (
    <>
      <div className="wrap">
        <Nav />
      </div>
      <main id="main">
        <AppLoader />
      </main>
    </>
  );
}
