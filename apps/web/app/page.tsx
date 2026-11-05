export default function Page() {
  return <main className="mx-auto max-w-3xl p-10">
    <p className="text-sm font-bold text-teal-700">KKULPICK · DEVELOPMENT</p>
    <h1 className="my-5 text-4xl font-bold">함께 개발할 준비</h1>
    <p className="mb-8 text-lg">이 화면은 공통 환경의 연결 확인용입니다. 회원·OCR·추천 기능은 각 담당 코드로 구현합니다.</p>
    <div className="grid gap-4 rounded-xl bg-white p-6 shadow-sm">
      <a className="text-teal-700 underline" href="/api/dev/status">웹 → 백엔드 연결 확인</a>
      <a className="text-teal-700 underline" href="/api/dev/offers">공통 DB의 상품 목록 확인</a>
      <p>상품·식품·판매정보의 원본은 공통 API에서 조회합니다.</p>
    </div>
    <p className="mt-8 text-sm">OCR·추천·수집 서비스는 연결용 틀이며 실제 분석을 수행하지 않습니다. Claude 호출은 기본 비활성입니다.</p>
  </main>;
}
