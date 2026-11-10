import Link from "next/link";
import { GITHUB_URL, TELEGRAM_URL } from "@/lib/site";
import s from "./Footer.module.css";

export default function Footer() {
  return (
    <footer className={s.foot}>
      <div className="wrap">
        <div className={s.grid}>
          <div className={s.brand}>
            <p className={s.mark}>
              Khidki{" "}
              <span lang="hi" className={s.hi}>
                खिड़की
              </span>
            </p>
            <p className={s.tag}>The cleanest hour over your street, published the night before and checked the day after.</p>
          </div>
          <nav className={s.cols} aria-label="Footer">
            <div>
              <Link href="/app">Your window</Link>
              <Link href="/ledger">Ledger</Link>
              <Link href="/monitors">Monitor health</Link>
              <Link href="/impact">Impact</Link>
            </div>
            <div>
              <Link href="/developers">Developers</Link>
              <Link href="/developers#embed">Embed card</Link>
              <a href={TELEGRAM_URL} rel="noopener">
                Telegram
              </a>
              <a href={GITHUB_URL} rel="noopener">
                Source on GitHub
              </a>
            </div>
          </nav>
        </div>
        <div className={s.credits}>
          <p>
            PM2.5: CPCB and state boards via OpenAQ · Forecast: CAMS (ECMWF/Copernicus) via Open-Meteo · Inhalation rates: US EPA
            Exposure Factors Handbook
          </p>
          <p>
            Open source under the MIT licence ·{" "}
            <a className="link" href={GITHUB_URL} rel="noopener">
              github.com/RaYYeR220/khidki
            </a>
          </p>
        </div>
      </div>
    </footer>
  );
}
