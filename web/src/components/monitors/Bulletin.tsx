import s from "./monitors.module.css";

function inline(text: string) {
  return text
    .split(/(\*\*[^*]+\*\*)/g)
    .map((part, i) =>
      part.startsWith("**") && part.endsWith("**") ? <strong key={i}>{part.slice(2, -2)}</strong> : <span key={i}>{part}</span>,
    );
}

const hi = (text: string) => (/[ऀ-ॿ]/.test(text) ? "hi" : undefined);

/** Renders the auditor's bulletin: paragraphs, bold headings and bullet lists. Everything else stays plain text. */
export default function Bulletin({ text }: { text: string }) {
  const blocks: React.ReactNode[] = [];
  let list: string[] = [];
  const flush = () => {
    if (list.length) {
      blocks.push(
        <ul key={`l${blocks.length}`}>
          {list.map((li, i) => (
            <li key={i} lang={hi(li)}>
              {inline(li)}
            </li>
          ))}
        </ul>,
      );
      list = [];
    }
  };
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (!line) {
      flush();
      continue;
    }
    if (/^[-*]\s+/.test(line)) {
      list.push(line.replace(/^[-*]\s+/, ""));
      continue;
    }
    flush();
    if (/^-{3,}$/.test(line)) {
      blocks.push(<hr key={`r${blocks.length}`} className={s.bRule} />);
      continue;
    }
    const heading = line.match(/^\*\*([^*]+)\*\*$/);
    if (heading)
      blocks.push(
        <p key={`h${blocks.length}`} className={s.bH} lang={hi(heading[1])}>
          {heading[1]}
        </p>,
      );
    else
      blocks.push(
        <p key={`p${blocks.length}`} lang={hi(line)}>
          {inline(line)}
        </p>,
      );
  }
  flush();
  return <div className={s.bulletin}>{blocks}</div>;
}
