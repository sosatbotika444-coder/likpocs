import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import { Modal } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import { uz } from './locales/uz';
import { playSound } from './sound';

export type PaletteCommand = { key: string; label: string; group: string; icon?: ReactNode; keywords?: string; run: () => void };

// Normalises Uzbek apostrophe variants so "to'lov" matches "To‘lov".
function normalize(value: string) {
  return value.toLocaleLowerCase('uz-UZ').replace(/[‘’ʻʼ`']/g, "'");
}

export function CommandPalette({ open, onClose, commands }: { open: boolean; onClose: () => void; commands: PaletteCommand[] }) {
  const [query, setQuery] = useState('');
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setQuery(''); setActive(0);
    const timer = window.setTimeout(() => inputRef.current?.focus(), 40);
    return () => window.clearTimeout(timer);
  }, [open]);

  const results = useMemo(() => {
    const needle = normalize(query.trim());
    if (!needle) return commands;
    return commands.filter((item) => normalize(`${item.label} ${item.keywords ?? ''} ${item.group}`).includes(needle));
  }, [commands, query]);

  useEffect(() => { setActive(0); }, [query]);

  const execute = (command: PaletteCommand | undefined) => {
    if (!command) return;
    playSound('click');
    onClose();
    command.run();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'ArrowDown') { event.preventDefault(); setActive((value) => Math.min(results.length - 1, value + 1)); }
    if (event.key === 'ArrowUp') { event.preventDefault(); setActive((value) => Math.max(0, value - 1)); }
    if (event.key === 'Enter') { event.preventDefault(); execute(results[active]); }
  };

  let lastGroup = '';
  return <Modal open={open} onCancel={onClose} footer={null} closable={false} width={560} className="command-palette" destroyOnClose>
    <div className="palette-search"><SearchOutlined />
      <input ref={inputRef} value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={onKeyDown} placeholder={uz.palette.placeholder} aria-label={uz.palette.open} />
      <kbd>Esc</kbd>
    </div>
    <div className="palette-results" role="listbox">
      {results.length === 0 && <div className="palette-empty">{uz.palette.empty}</div>}
      {results.map((item, index) => {
        const header = item.group !== lastGroup ? <div className="palette-group" key={`g-${item.group}`}>{item.group}</div> : null;
        lastGroup = item.group;
        return [header, <button
          type="button" role="option" aria-selected={index === active} key={item.key}
          className={`palette-item${index === active ? ' is-active' : ''}`}
          onMouseEnter={() => setActive(index)} onClick={() => execute(item)}
        ><span className="palette-icon">{item.icon}</span><span>{item.label}</span><span className="palette-enter">↵</span></button>];
      })}
    </div>
  </Modal>;
}
