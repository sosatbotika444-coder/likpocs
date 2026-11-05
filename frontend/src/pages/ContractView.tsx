import { useRef } from 'react';
import { uz } from '../locales/uz';
import type { Contract } from '../types';

/** Read-only lease agreement. `onReadAll` fires once the reader has scrolled to the end. */
export default function ContractView({ contract, onReadAll }: { contract: Contract; onReadAll?: () => void }) {
  const fired = useRef(false);
  const check = (element: HTMLDivElement) => {
    if (fired.current || !onReadAll) return;
    if (element.scrollHeight - element.scrollTop - element.clientHeight < 24) { fired.current = true; onReadAll(); }
  };
  return <div className="contract-box" role="document" tabIndex={0} aria-label={contract.title}
    style={{ maxHeight: 360, overflowY: 'auto', border: '1px solid #d9ded8', borderRadius: 8, padding: 16, background: '#fbfcfb' }}
    onScroll={(event) => check(event.currentTarget)}
    ref={(element) => { if (element && onReadAll && !fired.current && element.scrollHeight <= element.clientHeight + 24) { fired.current = true; onReadAll(); } }}>
    <h3 style={{ textAlign: 'center', marginBottom: 4 }}>{contract.title}</h3>
    <p style={{ textAlign: 'center', marginTop: 0 }}>{contract.number} · {contract.date} · {contract.city}</p>
    {contract.sections.map((section) => <section key={section.title}>
      <h4>{section.title}</h4>
      {section.clauses.map((clause) => <p key={clause} style={{ margin: '6px 0' }}>{clause}</p>)}
    </section>)}
    {onReadAll && <small>{uz.contract.scrollHint}</small>}
  </div>;
}
