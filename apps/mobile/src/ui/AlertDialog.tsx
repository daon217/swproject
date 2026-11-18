import { ConfirmDialog } from './components';

/** 안내 팝업(제목·본문 + 확인). null이면 닫힘 */
export type Alert = { title: string; body: string } | null;

export function AlertDialog({ alert, onClose }: { alert: Alert; onClose: () => void }) {
  return <ConfirmDialog visible={!!alert} title={alert?.title ?? ''} body={alert?.body ?? ''} confirmLabel="확인" cancelLabel={null} onConfirm={onClose} />;
}
