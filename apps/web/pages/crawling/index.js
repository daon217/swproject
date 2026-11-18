const crawlingPage = {
  liveCatalog: null,
  liveCatalogDomain: 'product',
  liveCatalogSource: '',

  changeLiveCatalogDomain(domain) {
    if (!['product', 'food'].includes(domain)) return;
    this.liveCatalogDomain = domain;
    return this.refreshLiveCatalog();
  },

  changeLiveCatalogSource(source) {
    if (!['', 'domeggook'].includes(source)) return;
    this.liveCatalogSource = source;
    return this.refreshLiveCatalog();
  },

  refreshLiveCatalog(cursor = null) {
    return this.refreshAdminData('liveCatalog', async () => {
      const url = new URL('/v2/offers', this.getApiBase());
      url.search = new URLSearchParams({
        selected_domain: this.liveCatalogDomain, condition: 'all', availability: 'all', limit: '50',
      });
      if (this.liveCatalogSource) url.searchParams.set('source', this.liveCatalogSource);
      if (cursor) url.searchParams.set('after', cursor);
      const response = await fetch(url, { signal: AbortSignal.timeout(5000) });
      if (!response.ok) throw new Error('Catalog lookup failed');
      const data = await response.json();
      if (!Array.isArray(data.items)) throw new Error('Invalid catalog response');
      return {
        items: data.items, cursor,
        nextCursor: data.next_cursor !== cursor && this.isUuid(data.next_cursor) ? data.next_cursor : null,
      };
    });
  },

  getLiveCatalogHtml() {
    const view = this.liveCatalog;
    const domain = this.liveCatalogDomain;
    const source = this.liveCatalogSource;
    const header = this.renderPageHeader('상품 크롤링 검토', '카탈로그에 등록된 상품의 마지막 확인 시각을 조회합니다. 일자별 크롤링 집계는 팀 API에서 제공되지 않습니다.');
    const states = { available: '판매 중', out_of_stock: '품절', ended: '종료', suspect: '확인 필요' };
    return `
      ${header}
      <div class="mb-4 flex flex-wrap items-end gap-3">
        <label class="text-sm">카탈로그 유형
          <select class="form-input mt-1 block" onchange="app.changeLiveCatalogDomain(this.value)">
            <option value="product" ${domain === 'product' ? 'selected' : ''}>일반 상품</option>
            <option value="food" ${domain === 'food' ? 'selected' : ''}>식품</option>
          </select>
        </label>
        <label class="text-sm">수집처
          <select class="form-input mt-1 block" onchange="app.changeLiveCatalogSource(this.value)">
            <option value="" ${source === '' ? 'selected' : ''}>전체 수집처</option>
            <option value="domeggook" ${source === 'domeggook' ? 'selected' : ''}>도매꾹</option>
          </select>
        </label>
        <button type="button" class="btn-secondary" onclick="app.refreshLiveCatalog()">새로고침</button>
      </div>
      ${view?.phase !== 'ready' ? this.renderAdminDataStatus(view, '') : `
        <div class="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table class="w-full min-w-[600px] text-left text-sm">
            <thead class="border-b border-slate-200 text-xs text-slate-600"><tr>
              <th class="p-4">상품명</th><th class="p-4">수집처</th><th class="p-4">현재 상태</th>
              <th class="p-4">마지막 확인 · KST</th>
            </tr></thead>
            <tbody class="divide-y divide-slate-200">
              ${view.items.length ? view.items.map((offer) => `
                <tr>
                  <td class="p-4 font-semibold">${this.escapeHtml(offer.name || '—')}</td>
                  <td class="p-4">${offer.source === 'domeggook' ? '도매꾹' : this.escapeHtml(offer.source || '—')}</td>
                  <td class="p-4">${this.escapeHtml(states[offer.availability] || '—')}</td>
                  <td class="whitespace-nowrap p-4">${this.escapeHtml(this.formatKstDateTime(offer.last_checked_at) || '—')}</td>
                </tr>
              `).join('') : `<tr><td colspan="4" class="p-4 text-slate-600">${source === 'domeggook' ? '이 유형에 등록된 도매꾹 상품이 없습니다.' : '조회된 상품이 없습니다.'}</td></tr>`}
            </tbody>
          </table>
        </div>
        <div class="mt-4 flex items-center justify-end gap-2">
          ${view.cursor ? '<button type="button" class="btn-secondary" onclick="app.refreshLiveCatalog()">첫 페이지</button>' : ''}
          ${view.nextCursor ? '<button type="button" class="btn-secondary" onclick="app.refreshLiveCatalog(app.liveCatalog.nextCursor)">다음 페이지</button>' : ''}
        </div>
      `}
    `;
  },

  getCrawlingHtml() {
    if (!this.isLocalAuthDemo()) return this.getLiveCatalogHtml();
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
