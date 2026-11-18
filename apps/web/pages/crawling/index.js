const crawlingPage = {
  getCrawlingHtml() {
    const [start, end] = this.parseDateRange(this.state.crawlingPeriod);
    const rows = this.state.crawlingData.filter((item) => item.date >= start && item.date <= end);

    const totalDays = rows.length;
    const totalCount = rows.reduce((acc, r) => acc + r.count, 0).toLocaleString();

    return `
      ${this.renderPageHeader('상품 크롤링 검토', '상품 데이터베이스 수집 내역을 날짜별로 확인하세요. · 예시 데이터')}

      <!-- 상단 검색 영역 -->
      <div class="mb-6">
        <label class="block text-xs font-bold text-slate-600 mb-1.5">조회 기간</label>
        <div class="flex flex-wrap items-center gap-2.5">
          <input
            id="crawling-period-input"
            type="text"
            value="${this.escapeHtml(this.state.crawlingPeriod)}"
            placeholder="2026.10.06 ~ 2026.10.12"
            class="form-input max-w-full w-[360px]"
            onkeydown="if(event.key==='Enter') app.handleCrawlingSearch()"
          />
          <button onclick="app.handleCrawlingSearch()" class="btn-primary">
            조회
          </button>
        </div>
      </div>

      <!-- 데이터 테이블 -->
      <div class="w-full">
        <!-- 컬럼 헤더 -->
        <div class="flex items-center px-6 py-3 text-xs font-bold text-slate-500 border-b border-slate-200">
          <div class="w-[35%] text-left">크롤링 일자</div>
          <div class="w-[65%] text-left">크롤링 건수</div>
        </div>

        <!-- 각 행(Row)은 흰색 배경 박스 형태(bg-white)로 행 사이 간격 배치 -->
        <div class="space-y-2 mt-2">
          ${rows.length ? '' : '<p class="px-6 py-4 text-sm text-slate-500">선택한 기간에 수집 내역이 없습니다.</p>'}
          ${rows
            .map(
              (row) => `
            <div class="flex items-center bg-white border border-slate-200/90 rounded-lg px-6 py-3.5 text-sm text-slate-800 shadow-[0_1px_2px_rgba(15,23,42,0.02)]">
              <div class="w-[35%] text-left font-medium text-slate-900">${row.date}</div>
              <div class="w-[65%] text-left font-semibold text-slate-800">${row.count}건</div>
            </div>
          `
            )
            .join('')}
        </div>
      </div>

      <!-- 하단 요약 문구 -->
      <div class="mt-4 text-sm text-slate-500">
        총 ${totalDays}일 · ${totalCount}건 &nbsp;&nbsp;/&nbsp;&nbsp; 날짜별 수집 건수입니다.
      </div>
    `;
  },

  handleCrawlingSearch() {
    const input = document.getElementById('crawling-period-input');
    const range = this.parseDateRange(input.value);
    if (!range) {
      this.showToast('조회 기간을 YYYY.MM.DD ~ YYYY.MM.DD 형식으로 입력해 주세요.');
      return;
    }
    this.state.crawlingPeriod = range.join(' ~ ');
    this.renderContent();
  },
};
