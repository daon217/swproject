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
    if (!['', 'domeggook', '11st', 'elevenst'].includes(source)) return;
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

  refreshCrawlingAll() {
    this.refreshLiveOverview();
    this.refreshLiveCatalog();
  },

  getCrawlDaysRows() {
    const rawDays = this.isLocalAuthDemo()
      ? this.state.crawlingData
      : (this.liveOverview?.crawlDays || []);
    const normalized = rawDays.map((row) => ({
      date: String(row.date || '').replaceAll('-', '.'),
      count: Number(row.count || 0),
      applied: row.applied != null ? Number(row.applied) : Number(row.count || 0),
    }));
    const range = this.parseDateRange(this.state.crawlingPeriod);
    if (!range) return normalized;
    const [start, end] = range;
    return normalized.filter((item) => item.date >= start && item.date <= end);
  },

  getCrawlingHtml() {
    const demo = this.isLocalAuthDemo();
    const rows = this.getCrawlDaysRows();
    const totalDays = rows.length;
    const totalCount = rows.reduce((acc, r) => acc + r.count, 0).toLocaleString();
    const totalApplied = rows.reduce((acc, r) => acc + r.applied, 0).toLocaleString();

    const view = this.liveCatalog;
    const domain = this.liveCatalogDomain;
    const source = this.liveCatalogSource;
    const states = { available: '판매 중', out_of_stock: '품절', ended: '종료', suspect: '확인 필요' };
    const sourceNames = { domeggook: '도매꾹', '11st': '11번가', elevenst: '11번가' };

    return `
      ${this.renderPageHeader(
        '상품 크롤링 검토',
        '팀 서버 DB의 최근 30일 일자별 수집 집계와 카탈로그 상품 상태를 확인합니다.',
        demo ? '' : '<button type="button" class="btn-secondary" onclick="app.refreshCrawlingAll()">새로고침</button>'
      )}

      <!-- 일자별 수집 건수 영역 (GET /v2/admin/overview -> crawl_days) -->
      <section aria-label="일자별 크롤링 집계" class="mb-8">
        <div class="mb-5">
          <label class="block text-xs font-bold text-slate-600 mb-1.5">조회 기간 (최근 30일 KST)</label>
          <div class="flex flex-wrap items-center gap-2.5">
            <input
              id="crawling-period-input"
              type="text"
              value="${this.escapeHtml(this.state.crawlingPeriod)}"
              placeholder="YYYY.MM.DD ~ YYYY.MM.DD"
              class="form-input max-w-full w-[360px]"
              onkeydown="if(event.key==='Enter') app.handleCrawlingSearch()"
            />
            <button onclick="app.handleCrawlingSearch()" class="btn-primary">
              조회
            </button>
          </div>
        </div>

        <div class="w-full">
          <div class="grid grid-cols-3 items-center px-6 py-3 text-xs font-bold text-slate-500 border-b border-slate-200">
            <div>크롤링 일자</div>
            <div>수신 건수</div>
            <div>DB 반영 건수</div>
          </div>

          <div class="space-y-2 mt-2">
            ${rows.length ? rows
              .map(
                (row) => `
              <div class="grid grid-cols-3 items-center bg-white border border-slate-200/90 rounded-lg px-6 py-3.5 text-sm text-slate-800 shadow-[0_1px_2px_rgba(15,23,42,0.02)]">
                <div class="font-medium text-slate-900">${this.escapeHtml(row.date)}</div>
                <div class="font-semibold text-slate-800">${row.count.toLocaleString()}건</div>
                <div class="font-semibold text-[#0066ff]">${row.applied.toLocaleString()}건</div>
              </div>
            `
              )
              .join('') : '<div class="bg-slate-100/80 text-slate-500 rounded-lg p-4 text-sm">선택한 기간에 수집된 크롤링 내역이 없습니다.</div>'}
          </div>
        </div>

        <div class="mt-3 text-sm text-slate-500">
          총 ${totalDays}일 · 수신 ${totalCount}건 · 반영 ${totalApplied}건
        </div>
      </section>

      ${demo ? '' : `
      <!-- 카탈로그 상품 목록 영역 (GET /v2/offers) -->
      <section aria-label="카탈로그 등록 상품 검토">
        <h2 class="text-base font-bold text-slate-900 mb-3">카탈로그 등록 상품 목록</h2>
        <div class="mb-4 flex flex-wrap items-end gap-3">
          <label class="text-xs font-bold text-slate-600">카탈로그 유형
            <select class="form-input mt-1.5 block font-normal" onchange="app.changeLiveCatalogDomain(this.value)">
              <option value="product" ${domain === 'product' ? 'selected' : ''}>일반 상품</option>
              <option value="food" ${domain === 'food' ? 'selected' : ''}>식품</option>
            </select>
          </label>
          <label class="text-xs font-bold text-slate-600">수집처
            <select class="form-input mt-1.5 block font-normal" onchange="app.changeLiveCatalogSource(this.value)">
              <option value="" ${source === '' ? 'selected' : ''}>전체 수집처</option>
              <option value="domeggook" ${source === 'domeggook' ? 'selected' : ''}>도매꾹</option>
              <option value="11st" ${source === '11st' ? 'selected' : ''}>11번가</option>
            </select>
          </label>
        </div>

        ${view?.phase !== 'ready' ? this.renderAdminDataStatus(view, '<button type="button" class="btn-secondary" onclick="app.refreshLiveCatalog()">다시 시도</button>') : `
          <div class="overflow-x-auto rounded-xl border border-slate-200 bg-white">
            <table class="w-full min-w-[640px] text-left text-sm">
              <thead class="border-b border-slate-200 text-xs text-slate-600"><tr>
                <th class="p-4">상품명</th><th class="p-4">수집처</th><th class="p-4">가격</th>
                <th class="p-4">현재 상태</th><th class="p-4">마지막 확인 · KST</th>
              </tr></thead>
              <tbody class="divide-y divide-slate-200">
                ${view.items.length ? view.items.map((offer) => `
                  <tr>
                    <td class="p-4 font-semibold">${this.escapeHtml(offer.name || '—')}</td>
                    <td class="p-4">${this.escapeHtml(sourceNames[offer.source] || offer.source || '—')}</td>
                    <td class="p-4 whitespace-nowrap">${this.escapeHtml(this.formatPriceKrw ? this.formatPriceKrw(offer.price) : `${offer.price || 0}원`)}</td>
                    <td class="p-4">${this.escapeHtml(states[offer.availability] || '—')}</td>
                    <td class="whitespace-nowrap p-4">${this.escapeHtml(this.formatKstDateTime(offer.last_checked_at) || '—')}</td>
                  </tr>
                `).join('') : `<tr><td colspan="5" class="p-4 text-slate-600">${source ? '선택한 수집처에 등록된 상품이 없습니다.' : '조회된 카탈로그 상품이 없습니다.'}</td></tr>`}
              </tbody>
            </table>
          </div>
          <div class="mt-4 flex items-center justify-end gap-2">
            ${view.cursor ? '<button type="button" class="btn-secondary" onclick="app.refreshLiveCatalog()">첫 페이지</button>' : ''}
            ${view.nextCursor ? '<button type="button" class="btn-secondary" onclick="app.refreshLiveCatalog(app.liveCatalog.nextCursor)">다음 페이지</button>' : ''}
          </div>
        `}
      </section>
      `}
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
