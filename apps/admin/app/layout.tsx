import './globals.css';
export const metadata = { title: '꿀픽 공동개발 환경' };
export default function Layout({ children }: { children: React.ReactNode }) {
  return <html lang="ko"><body>{children}</body></html>;
}
