import { useEffect, useId, useState, type InputHTMLAttributes, type ReactNode } from 'react';
import { ALLERGEN_GROUPS } from '../shared/allergens';
import { IconBack, IconCheck, IconChevronDown, IconChevronRight } from '../shared/ui/icons';
import { useNav } from './nav';

export function SubHeader({ title, onBack }: { title: string; onBack?: () => void }) {
  const nav = useNav();
  return (
    <header className="sp-subheader">
      <button className="kp-icon-btn sp-back" onClick={onBack ?? nav.pop} aria-label="뒤로">
        <IconBack size={22} />
      </button>
      <h1>{title}</h1>
    </header>
  );
}

/** 본문 스크롤 + 하단 고정 버튼 레이아웃 */
export function Page({ children, footer, className }: { children: ReactNode; footer?: ReactNode; className?: string }) {
  return (
    <div className={`sp-page ${className ?? ''}`}>
      <div className="sp-page-body">{children}</div>
      {footer && <div className="sp-page-footer">{footer}</div>}
    </div>
  );
}

export function Field({ label, error, ...input }: { label: string; error?: string | null } & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId();
  return (
    <div className="sp-field">
      <label htmlFor={id}>{label}</label>
      <input id={id} className={`sp-input ${error ? 'is-error' : ''}`} aria-invalid={!!error} {...input} />
      {error && <p className="sp-error">{error}</p>}
    </div>
  );
}

export function Note({ children }: { children: ReactNode }) {
  return <div className="sp-note">{children}</div>;
}

export function Toggle({ checked, onChange, label, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <button
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      className={`sp-toggle ${checked ? 'is-on' : ''}`}
      onClick={() => onChange(!checked)}
    >
      <span />
    </button>
  );
}

export function RowButton({ children, onClick, danger }: { children: ReactNode; onClick: () => void; danger?: boolean }) {
  return (
    <button className={`sp-row ${danger ? 'is-danger' : ''}`} onClick={onClick}>
      <span>{children}</span>
      {!danger && <IconChevronRight size={20} />}
    </button>
  );
}

export function ConfirmDialog({
  title,
  body,
  confirmLabel,
  cancelLabel = '취소',
  onConfirm,
  onCancel,
  danger,
}: {
  title: string;
  body: ReactNode;
  confirmLabel: string;
  cancelLabel?: string | null;
  onConfirm: () => void;
  onCancel?: () => void;
  danger?: boolean;
}) {
  return (
    <div className="sp-dim" role="dialog" aria-modal="true" aria-label={title}>
      <div className="sp-dialog">
        <h2>{title}</h2>
        <div className="sp-dialog-body">{body}</div>
        <div className="sp-dialog-actions">
          {cancelLabel && onCancel && (
            <button className="kp-btn kp-btn-outline" onClick={onCancel}>
              {cancelLabel}
            </button>
          )}
          <button className={`kp-btn kp-btn-primary ${danger ? 'sp-btn-danger' : ''}`} onClick={onConfirm} autoFocus>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

export function Toast({ message, onDone }: { message: string; onDone: () => void }) {
  useEffect(() => {
    const t = setTimeout(onDone, 2600);
    return () => clearTimeout(t);
  }, [message, onDone]);
  return (
    <div className="sp-toast" role="status">
      {message}
    </div>
  );
}

export function Checkbox({ checked, onChange, children }: { checked: boolean; onChange: (v: boolean) => void; children: ReactNode }) {
  return (
    <label className="sp-check">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span className="sp-check-box" aria-hidden="true">
        {checked && <IconCheck size={14} strokeWidth={3} />}
      </span>
      <span>{children}</span>
    </label>
  );
}

/** 알레르기 선택(가입·개인정보 수정 공용). 그룹별 접기/펼치기. */
export function AllergyPicker({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  const [open, setOpen] = useState<Record<string, boolean>>({ [ALLERGEN_GROUPS[0].group]: true });
  const toggle = (code: string, on: boolean) => onChange(on ? [...value, code] : value.filter((c) => c !== code));
  return (
    <div className="sp-allergy">
      {ALLERGEN_GROUPS.map((g) => {
        const isOpen = !!open[g.group];
        const picked = g.items.filter((i) => value.includes(i.code)).length;
        return (
          <div key={g.group} className="sp-allergy-group">
            <button className="sp-allergy-head" aria-expanded={isOpen} onClick={() => setOpen({ ...open, [g.group]: !isOpen })}>
              {isOpen ? <IconChevronDown size={16} /> : <IconChevronRight size={16} />}
              <span>{g.group}</span>
              {picked > 0 && <span className="sp-allergy-count">{picked}</span>}
            </button>
            {isOpen &&
              g.items.map((i) => (
                <Checkbox key={i.code} checked={value.includes(i.code)} onChange={(on) => toggle(i.code, on)}>
                  {i.label}
                </Checkbox>
              ))}
          </div>
        );
      })}
    </div>
  );
}

export function GenderSelect({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const id = useId();
  return (
    <div className="sp-field">
      <label htmlFor={id}>성별</label>
      <select id={id} className="sp-input" value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">선택하세요</option>
        <option value="female">여성</option>
        <option value="male">남성</option>
        <option value="prefer_not_to_say">응답하지 않음</option>
      </select>
    </div>
  );
}
