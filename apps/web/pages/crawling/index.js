const crawlingPage = {
  liveCatalog: null,
  liveCatalogDomain: 'all', // 'all' | 'product' | 'food'
  liveCatalogSource: '',
  liveCatalogAvailability: '',
  liveCatalogSearch: '',
  liveCatalogDate: '', // '' = 전체 날짜(날짜별 그룹), 'YYYY.MM.DD' = 특정 날짜 필터
  liveCatalogPeriodFilter: '', // '' = 전체 기간, 'YYYY.MM.DD ~ YYYY.MM.DD' = 기간 필터
  liveCatalogPage: 1,
  liveCatalogPageSize: 50,
  crawlDeletionRunning: false,

  // Older builds hid "deleted" offers only in this browser. Deletion is server-side now; drop that list
  // so it can never hide real catalog rows.
  purgeLocalDeletedOffers() {
    try { window.localStorage.removeItem('kkulpick-deleted-catalog-offers'); } catch { /* storage disabled */ }
  },

  updateCrawlSelection(form) {
    const choices = form.querySelectorAll('input[name="offer_id"]');
    const count = form.querySelectorAll('input[name="offer_id"]:checked').length;
    form.querySelector("[data-selection-count]").textContent = count.toLocaleString() + "건 선택";
    form.querySelector('button[type="submit"]').disabled = this.crawlDeletionRunning || count === 0;
    for (const choice of choices) choice.disabled = this.crawlDeletionRunning;
  },

  async deleteSelectedCrawlOffers(event) {
    event.preventDefault();
    const session = this.adminSession;
    if (session?.role !== "admin" || this.isLocalAuthDemo() || this.crawlDeletionRunning) return;
    const form = event.currentTarget;
    const offerIds = [...form.querySelectorAll('input[name="offer_id"]:checked')].map((input) => input.value);
    if (!offerIds.length || !window.confirm("선택한 상품 " + offerIds.length + "건을 삭제할까요? 제휴에 연결된 상품은 유지됩니다.")) return;

    this.crawlDeletionRunning = true;
    this.updateCrawlSelection(form);
    try {
      const result = await this.requestAdminAuth("/v2/admin/catalog/offers/delete", {
        method: "POST", token: session.token, body: { offer_ids: offerIds },
      });
      const { deleted_offer_ids: deleted, protected_offer_ids: protectedOffers, missing_offer_ids: missing } = result || {};
      if (![deleted, protectedOffers, missing].every(Array.isArray)) throw new Error("Invalid catalog deletion result");
      if (this.adminSession !== session) return;

      const removedIds = new Set([...deleted, ...missing]);
      if (this.liveCatalog) this.liveCatalog.items = this.liveCatalog.items.filter((item) => !removedIds.has(item.offer_id));
      this.state.offerCatalog = (this.state.offerCatalog || []).filter((item) => !removedIds.has(item.offer_id));
      const summary = [deleted.length + "건 삭제"];
      if (protectedOffers.length) summary.push("제휴 연결 " + protectedOffers.length + "건 유지");
      if (missing.length) summary.push("이미 없는 상품 " + missing.length + "건");
      this.showToast(summary.join(" · "));
      if (this.state.currentPage === "crawling") {
        await Promise.all([this.refreshLiveCatalog(), this.refreshLiveOverview()]);
      }
    } catch (error) {
      if (this.adminSession !== session) return;
      const messages = {
        401: "로그인 세션이 만료되었습니다. 다시 로그인해 주세요.",
        403: "카탈로그 상품을 삭제할 권한이 없습니다.",
        404: "팀 서버에 상품 삭제 기능이 아직 배포되지 않았습니다.",
      };
      this.showToast(messages[error.status] || "상품 삭제 결과를 확인하지 못했습니다. 목록을 새로고침해 주세요.");
    } finally {
      this.crawlDeletionRunning = false;
      if (form.isConnected) this.updateCrawlSelection(form);
    }
  },

  changeLiveCatalogDomain(domain) {
    if (!['all', 'product', 'food'].includes(domain)) return;
    this.liveCatalogDomain = domain;
    this.liveCatalogDate = '';
    this.liveCatalogPage = 1;
    return this.refreshLiveCatalog();
  },

  changeLiveCatalogSource(source) {
    this.liveCatalogSource = source || '';
    this.liveCatalogPage = 1;
    this.renderContent();
  },

  changeLiveCatalogAvailability(availability) {
    this.liveCatalogAvailability = availability || '';
    this.liveCatalogPage = 1;
    this.renderContent();
  },

  handleCatalogSearchInput(value) {
    this.liveCatalogSearch = value || '';
    this.liveCatalogPage = 1;
    if (!this.updateCatalogResultsDom()) {
      this.renderContent();
    }
  },

  changeLiveCatalogDate(dateStr) {
    const normalized = (dateStr || '').trim().replaceAll('-', '.');
    this.liveCatalogDate = /^\d{4}\.\d{2}\.\d{2}$/.test(normalized) ? normalized : '';
    this.liveCatalogPage = 1;
    this.renderContent();
  },

  changeLiveCatalogPage(page) {
    const next = Math.max(1, Number(page) || 1);
    this.liveCatalogPage = next;
    this.renderContent();
  },

  getOfferKstDate(offer) {
    const kst = this.formatKstDateTime(offer?.last_checked_at || offer?.last_seen_at || offer?.price_observed_at);
    return kst ? kst.slice(0, 10) : '날짜 미확인';
  },

  getOfferTimestamp(offer) {
    const ts = Date.parse(offer?.last_checked_at || offer?.last_seen_at || offer?.price_observed_at || '');
    return Number.isFinite(ts) ? ts : 0;
  },

  async fetchDomainOffersAll(domain, onBatch) {
    const url = new URL(this.getApiBase() + '/v2/offers'); // keep the /backend proxy prefix
    url.search = new URLSearchParams({
      selected_domain: domain, condition: 'all', availability: 'all', limit: '100',
    });

    const items = [];
    const cursors = new Set();
    for (let page = 0; page < 200; page++) {
      try {
        const response = await fetch(url, { signal: AbortSignal.timeout(15000) });
        if (!response.ok) {
          if (items.length) break;
          throw new Error('Catalog lookup failed');
        }
        const data = await response.json();
        if (!Array.isArray(data.items)) {
          if (items.length) break;
          throw new Error('Invalid catalog response');
        }
        for (const item of data.items) {
          items.push({ ...item, selected_domain: item.selected_domain || domain });
        }
        if (onBatch && (page === 0 || page % 5 === 0)) {
          onBatch(items);
        }
        const nextCursor = data.next_cursor;
        if (!nextCursor || !this.isUuid(nextCursor) || cursors.has(nextCursor)) {
          break;
        }
        cursors.add(nextCursor);
        url.searchParams.set('after', nextCursor);
      } catch (err) {
        if (items.length) break;
        throw err;
      }
    }
    if (onBatch) onBatch(items);
    return items;
  },

  refreshLiveCatalog() {
    return this.refreshAdminData('liveCatalog', async () => {
      const domains = this.liveCatalogDomain === 'all'
        ? ['product', 'food']
        : [this.liveCatalogDomain];

      this.purgeLocalDeletedOffers();

      const offers = new Map();
      const targetView = this.liveCatalog;
      const pushProgress = (batchItems) => {
        for (const item of batchItems) offers.set(item.offer_id, item);
        if (targetView && this.liveCatalog === targetView) {
          targetView.items = [...offers.values()].sort(
            (a, b) => this.getOfferTimestamp(b) - this.getOfferTimestamp(a)
          );
          targetView.phase = 'ready';
          if (this.state.currentPage === 'crawling') {
            if (document.activeElement?.id === 'catalog-search-input' && this.updateCatalogResultsDom()) {
              return;
            }
            this.renderContent();
          }
        }
      };

      const results = await Promise.allSettled(
        domains.map((domain) => this.fetchDomainOffersAll(domain, pushProgress))
      );

      let succeeded = 0;
      for (const res of results) {
        if (res.status === 'fulfilled') {
          succeeded += 1;
          for (const item of res.value) offers.set(item.offer_id, item);
        }
      }
      if (succeeded === 0) {
        throw new Error('Catalog lookup failed');
      }

      const sortedItems = [...offers.values()].sort(
        (a, b) => this.getOfferTimestamp(b) - this.getOfferTimestamp(a)
      );

      return { items: sortedItems };
    });
  },

  refreshCrawlingAll() {
    this.refreshLiveOverview();
    this.refreshLiveCatalog();
  },

  getAllDateRows(catalogItems) {
    const map = new Map();
    for (const offer of catalogItems) {
      const dateKey = this.getOfferKstDate(offer);
      if (dateKey === '날짜 미확인') continue;
      if (!map.has(dateKey)) {
        map.set(dateKey, { date: dateKey, productCount: 0, availableCount: 0, receivedCount: 0 });
      }
      const entry = map.get(dateKey);
      entry.productCount += 1;
      if (offer.availability === 'available') entry.availableCount += 1;
    }

    const rawDays = this.isLocalAuthDemo()
      ? this.state.crawlingData
      : (this.liveOverview?.crawlDays || []);
    for (const row of rawDays) {
      const dateKey = String(row.date || '').replaceAll('-', '.');
      if (!dateKey) continue;
      if (!map.has(dateKey)) {
        map.set(dateKey, {
          date: dateKey,
          productCount: Number(row.applied ?? row.count ?? 0),
          availableCount: 0,
          receivedCount: Number(row.count || 0),
        });
      } else {
        map.get(dateKey).receivedCount = Number(row.count || 0);
      }
    }

    let rows = [...map.values()].sort((a, b) => b.date.localeCompare(a.date));
    const range = this.liveCatalogPeriodFilter ? this.parseDateRange(this.liveCatalogPeriodFilter) : null;
    if (range) {
      const [start, end] = range;
      rows = rows.filter((item) => item.date >= start && item.date <= end);
    }
    return rows;
  },

  getCatalogDateSummary(items) {
    const counts = new Map();
    for (const offer of items) {
      const dateKey = this.getOfferKstDate(offer);
      counts.set(dateKey, (counts.get(dateKey) || 0) + 1);
    }
    return [...counts.entries()].sort((a, b) => {
      if (a[0] === '날짜 미확인') return 1;
      if (b[0] === '날짜 미확인') return -1;
      return b[0].localeCompare(a[0]);
    });
  },

  computeCrawlingViewState() {
    const view = this.liveCatalog;
    const source = this.liveCatalogSource;
    const availability = this.liveCatalogAvailability;
    const searchQuery = this.liveCatalogSearch.trim().toLowerCase();
    const selectedDate = this.liveCatalogDate;
    const sourceNames = { domeggook: '도매꾹', '11st': '11번가', elevenst: '11번가', coupang: '쿠팡', naver: '네이버' };

    const allCatalogItems = view?.items || [];
    const rows = this.getAllDateRows(allCatalogItems);
    const totalDays = rows.length;
    // 전체 상품 수는 실제 카탈로그 건수. 날짜별 합계는 과거 수집 실행의 적재 건수까지 더해져(같은 상품 재수집) 더 커질 수 있다.
    const totalProductCount = (this.isLocalAuthDemo() ? rows.reduce((acc, r) => acc + r.productCount, 0) : allCatalogItems.length).toLocaleString();

    const sourceSet = new Set(['domeggook', '11st']);
    for (const offer of allCatalogItems) {
      if (offer.source) sourceSet.add(offer.source);
    }
    const availableSources = [...sourceSet].sort((a, b) => {
      const labelA = sourceNames[a] || a;
      const labelB = sourceNames[b] || b;
      return labelA.localeCompare(labelB, 'ko');
    });

    const periodRange = this.liveCatalogPeriodFilter ? this.parseDateRange(this.liveCatalogPeriodFilter) : null;
    const baseFilteredItems = allCatalogItems.filter((offer) => {
      if (source && offer.source !== source) return false;
      if (availability && offer.availability !== availability) return false;
      if (searchQuery) {
        const searchable = `${offer.name || ''} ${offer.source || ''} ${offer.offer_id || ''}`.toLowerCase();
        if (!searchable.includes(searchQuery)) return false;
      }
      if (periodRange) {
        const d = this.getOfferKstDate(offer);
        if (d < periodRange[0] || d > periodRange[1]) return false;
      }
      return true;
    });

    const dateSummary = this.getCatalogDateSummary(baseFilteredItems);
    const filteredCatalogItems = selectedDate
      ? baseFilteredItems.filter((offer) => this.getOfferKstDate(offer) === selectedDate)
      : baseFilteredItems;

    const totalPages = Math.max(1, Math.ceil(filteredCatalogItems.length / this.liveCatalogPageSize));
    const currentPage = Math.min(Math.max(1, this.liveCatalogPage), totalPages);
    const pageStart = (currentPage - 1) * this.liveCatalogPageSize;
    const pagedItems = filteredCatalogItems.slice(pageStart, pageStart + this.liveCatalogPageSize);

    const groupedByDate = [];
    const groupIndexMap = new Map();
    for (const offer of pagedItems) {
      const dateKey = this.getOfferKstDate(offer);
      if (!groupIndexMap.has(dateKey)) {
        groupIndexMap.set(dateKey, groupedByDate.length);
        groupedByDate.push({ date: dateKey, items: [] });
      }
      groupedByDate[groupIndexMap.get(dateKey)].items.push(offer);
    }

    const totalCountByDate = new Map(dateSummary);
    return {
      view,
      rows,
      totalDays,
      totalProductCount,
      availableSources,
      baseFilteredItems,
      dateSummary,
      filteredCatalogItems,
      totalPages,
      currentPage,
      groupedByDate,
      totalCountByDate,
    };
  },

  getCatalogDateOptionsHtml(baseFilteredItems, dateSummary, selectedDate) {
    return `
      <option value="" ${selectedDate === '' ? 'selected' : ''}>전체 날짜 (${baseFilteredItems.length.toLocaleString()}건)</option>
      ${dateSummary.map(([dateKey, count]) => `
        <option value="${this.escapeHtml(dateKey)}" ${selectedDate === dateKey ? 'selected' : ''}>${this.escapeHtml(dateKey)} (${count.toLocaleString()}건)</option>
      `).join('')}
    `;
  },

  getCatalogResultsBodyHtml(computed) {
    const { view, groupedByDate, totalCountByDate, totalPages, currentPage } = computed;
    const selectedDate = this.liveCatalogDate;
    const states = { available: '판매 중', out_of_stock: '품절', ended: '종료', suspect: '확인 필요' };
    const sourceNames = { domeggook: '도매꾹', '11st': '11번가', elevenst: '11번가', coupang: '쿠팡', naver: '네이버' };

    if (view?.phase !== 'ready') {
      return this.renderAdminDataStatus(view, '<button type="button" class="btn-secondary" onclick="app.refreshLiveCatalog()">다시 시도</button>');
    }

    return `
      ${groupedByDate.length ? `
        <form onchange="app.updateCrawlSelection(this)" onsubmit="app.deleteSelectedCrawlOffers(event)">
          <div class="mb-3 flex items-center justify-end gap-3">
            <span data-selection-count role="status" class="text-xs text-slate-600">0건 선택</span>
            <button type="submit" disabled class="rounded-lg border border-red-200 bg-white px-3 py-2 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:opacity-40">
              선택 삭제
            </button>
          </div>
        <div class="space-y-5">
          ${groupedByDate.map((group) => {
      const dayTotal = totalCountByDate.get(group.date) ?? group.items.length;
      return `
              <div class="overflow-hidden rounded-xl border border-slate-200 bg-white">
                <div class="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-4 py-3">
                  <div class="flex items-center gap-2">
                    <span class="text-sm font-bold text-slate-900">${this.escapeHtml(group.date)}</span>
                    <span class="rounded-full bg-[#ebf3ff] px-2.5 py-0.5 text-xs font-semibold text-[#0066ff]">${dayTotal.toLocaleString()}건</span>
                  </div>
                  ${selectedDate !== group.date && group.date !== '날짜 미확인' ? `<button type="button" class="text-xs font-semibold text-[#0066ff] hover:underline" onclick="app.changeLiveCatalogDate('${this.escapeHtml(group.date)}')">이 날짜만 보기</button>` : ''}
                </div>
                <div class="overflow-x-auto">
                  <table class="w-full min-w-[820px] text-left text-sm">
                    <thead class="border-b border-slate-200 text-xs text-slate-600"><tr>
                      <th class="p-4"><span class="sr-only">선택</span></th>
                      <th class="p-4">구분</th><th class="p-4">상품명</th><th class="p-4">수집처</th><th class="p-4">가격</th>
                      <th class="p-4">URL</th><th class="p-4">상품 상태</th><th class="p-4">현재 상태</th><th class="p-4">마지막 확인 · KST</th>
                    </tr></thead>
                    <tbody class="divide-y divide-slate-200">
                      ${group.items.map((offer) => {
        const rawUrl = offer.current_url || '';
        const safeUrl = /^https?:\/\//i.test(rawUrl) ? this.escapeHtml(rawUrl) : '';
        return `
                        <tr>
                          <td class="p-4">
                            <input type="checkbox" name="offer_id" class="h-4 w-4 accent-blue-600"
                              value="${this.escapeHtml(offer.offer_id)}"
                              aria-label="${this.escapeHtml(offer.name || offer.offer_id)} 선택"
                              ${this.crawlDeletionRunning ? "disabled" : ""} />
                          </td>
                          <td class="p-4 whitespace-nowrap text-xs text-slate-500">${offer.selected_domain === 'food' ? '식품' : '일반'}</td>
                          <td class="p-4 font-semibold">${this.escapeHtml(offer.name || '—')}</td>
                          <td class="p-4 whitespace-nowrap">${this.escapeHtml(sourceNames[offer.source] || offer.source || '—')}</td>
                          <td class="p-4 whitespace-nowrap">${this.escapeHtml(this.formatOfferPrice ? this.formatOfferPrice(offer) : `${offer.price || 0}원`)}</td>
                          <td class="p-4 max-w-[220px] truncate text-xs text-slate-500" title="${this.escapeHtml(rawUrl || '—')}">
                            ${safeUrl ? `<a href="${safeUrl}" target="_blank" rel="noopener noreferrer" class="text-[#0066ff] hover:underline">${safeUrl}</a>` : '—'}
                          </td>
                          <td class="p-4 whitespace-nowrap">${this.escapeHtml(({ new: '새 상품', used: '중고', unknown: '미확인' })[offer.condition] || '미확인')}</td>
                          <td class="p-4 whitespace-nowrap">${this.escapeHtml(states[offer.availability] || '—')}</td>
                          <td class="whitespace-nowrap p-4">${this.escapeHtml(this.formatKstDateTime(offer.last_checked_at || offer.last_seen_at || offer.price_observed_at) || '—')}</td>
                        </tr>
                      `;
      }).join('')}
                    </tbody>
                  </table>
                </div>
              </div>
            `;
    }).join('')}
        </div>
        </form>
      ` : `
        <div class="rounded-xl border border-slate-200 bg-white p-5 text-sm text-slate-600">
          ${selectedDate ? `${this.escapeHtml(selectedDate)} 날짜에 확인된 카탈로그 상품이 없습니다.` : '조건에 일치하는 카탈로그 상품이 없습니다.'}
        </div>
      `}

      ${totalPages > 1 ? `
        <div class="mt-4 flex items-center justify-between gap-2 text-sm">
          <span class="text-slate-500">페이지 ${currentPage} / ${totalPages}</span>
          <div class="flex items-center gap-2">
            <button type="button" class="btn-secondary disabled:opacity-50" ${currentPage <= 1 ? 'disabled' : ''} onclick="app.changeLiveCatalogPage(${currentPage - 1})">이전</button>
            <button type="button" class="btn-secondary disabled:opacity-50" ${currentPage >= totalPages ? 'disabled' : ''} onclick="app.changeLiveCatalogPage(${currentPage + 1})">다음</button>
          </div>
        </div>
      ` : ''}
    `;
  },

  updateCatalogResultsDom() {
    const bodyEl = document.getElementById('catalog-results-body');
    if (!bodyEl) return false;
    const computed = this.computeCrawlingViewState();
    const selectedDate = this.liveCatalogDate;

    const summaryEl = document.getElementById('catalog-total-summary');
    if (summaryEl) {
      summaryEl.textContent = computed.view?.phase === 'ready'
        ? `총 ${computed.filteredCatalogItems.length.toLocaleString()}건${selectedDate ? ` (${selectedDate})` : ` · ${computed.dateSummary.length}개 일자`}`
        : '';
    }

    const dateSelectEl = document.getElementById('catalog-date-select');
    if (dateSelectEl) {
      dateSelectEl.innerHTML = this.getCatalogDateOptionsHtml(
        computed.baseFilteredItems,
        computed.dateSummary,
        selectedDate
      );
    }

    bodyEl.innerHTML = this.getCatalogResultsBodyHtml(computed);
    return true;
  },

  getCrawlingHtml() {
    const demo = this.isLocalAuthDemo();
    const domain = this.liveCatalogDomain;
    const source = this.liveCatalogSource;
    const availability = this.liveCatalogAvailability;
    const selectedDate = this.liveCatalogDate;
    const sourceNames = { domeggook: '도매꾹', '11st': '11번가', elevenst: '11번가', coupang: '쿠팡', naver: '네이버' };

    const computed = this.computeCrawlingViewState();
    const {
      view,
      rows,
      totalDays,
      totalProductCount,
      availableSources,
      baseFilteredItems,
      dateSummary,
      filteredCatalogItems,
    } = computed;

    const dateInputValue = selectedDate ? selectedDate.replaceAll('.', '-') : '';

    return `
      ${this.renderPageHeader(
      '상품 크롤링 검토',
      '기간 제한 없이 DB에 등록된 전체 상품의 일자별 현황과 날짜별 카탈로그 상품 목록을 관리합니다.',
      demo ? '' : '<button type="button" class="btn-secondary" onclick="app.refreshCrawlingAll()">새로고침</button>'
    )}

      <!-- 일자별 전체 상품 수집 현황 (전체 기간 대상) -->
      <section aria-label="일자별 상품 수집 현황" class="mb-8">
        <div class="mb-5">
          <label class="block text-xs font-bold text-slate-600 mb-1.5">조회 기간 (전체 기간 · KST)</label>
          <div class="flex flex-wrap items-center gap-2.5">
            <input
              id="crawling-period-input"
              type="text"
              value="${this.escapeHtml(this.liveCatalogPeriodFilter)}"
              placeholder="전체 기간 (기간 지정 시 YYYY.MM.DD ~ YYYY.MM.DD)"
              class="form-input max-w-full w-[380px]"
              onkeydown="if(event.key==='Enter') app.handleCrawlingSearch()"
            />
            <button type="button" onclick="app.handleCrawlingSearch()" class="btn-primary">
              조회
            </button>
            ${this.liveCatalogPeriodFilter ? '<button type="button" onclick="app.resetCrawlingPeriod()" class="btn-secondary">전체 기간 보기</button>' : ''}
          </div>
        </div>

        <div class="w-full">
          <div class="grid grid-cols-2 items-center px-6 py-3 text-xs font-bold text-slate-500 border-b border-slate-200">
            <div>확인 일자</div>
            <div>등록 상품 수</div>
          </div>

          <div class="space-y-2 mt-2">
            ${rows.length ? rows
        .map((row) => {
          const isSelectedDay = !demo && selectedDate === row.date;
          const rowStyle = isSelectedDay
            ? 'border-[#0066ff] ring-1 ring-[#0066ff]/20 bg-[#ebf3ff]'
            : 'border-slate-200/90 bg-white hover:border-slate-300';
          return `
              <div
                ${demo ? '' : `onclick="app.changeLiveCatalogDate('${this.escapeHtml(row.date)}')"`}
                class="grid grid-cols-2 items-center border ${rowStyle} rounded-lg px-6 py-3.5 text-sm text-slate-800 shadow-[0_1px_2px_rgba(15,23,42,0.02)] ${demo ? '' : 'cursor-pointer transition-colors'}"
                title="${demo ? '' : '클릭하면 아래 카탈로그 목록을 이 날짜로 필터링합니다'}"
              >
                <div class="font-medium text-slate-900">${this.escapeHtml(row.date)}</div>
                <div class="font-semibold text-slate-800">${row.productCount.toLocaleString()}건</div>
              </div>
            `;
        })
        .join('') : `<div class="bg-slate-100/80 text-slate-500 rounded-lg p-4 text-sm">${view?.phase === 'loading' ? '전체 상품 데이터를 불러오는 중입니다...' : '조회된 수집 일자 내역이 없습니다.'}</div>`}
          </div>
        </div>

        <div class="mt-3 text-sm text-slate-500">
          총 ${totalDays}일 · 전체 상품 ${totalProductCount}건
        </div>
      </section>

      ${demo ? '' : `
      <!-- 카탈로그 등록 상품 목록 영역 (전체 상품, 날짜별 조회·그룹핑) -->
      <section aria-label="카탈로그 등록 상품 검토">
        <div class="flex flex-wrap items-center justify-between gap-2 mb-3">
          <h2 class="text-base font-bold text-slate-900">카탈로그 등록 상품 목록</h2>
          <span id="catalog-total-summary" class="text-xs text-slate-500">${view?.phase === 'ready' ? `총 ${filteredCatalogItems.length.toLocaleString()}건${selectedDate ? ` (${this.escapeHtml(selectedDate)})` : ` · ${dateSummary.length}개 일자`}` : ''}</span>
        </div>

        <div class="mb-4 flex flex-wrap items-end gap-3">
          <label class="text-xs font-bold text-slate-600">카탈로그 유형
            <select class="form-input mt-1.5 block font-normal" onchange="app.changeLiveCatalogDomain(this.value)">
              <option value="all" ${domain === 'all' ? 'selected' : ''}>전체 (일반 + 식품)</option>
              <option value="product" ${domain === 'product' ? 'selected' : ''}>일반 상품</option>
              <option value="food" ${domain === 'food' ? 'selected' : ''}>식품</option>
            </select>
          </label>
          <label class="text-xs font-bold text-slate-600">수집처
            <select class="form-input mt-1.5 block font-normal" onchange="app.changeLiveCatalogSource(this.value)">
              <option value="" ${source === '' ? 'selected' : ''}>전체 수집처</option>
              ${availableSources.map((src) => `
                <option value="${this.escapeHtml(src)}" ${source === src ? 'selected' : ''}>${this.escapeHtml(sourceNames[src] || src)}</option>
              `).join('')}
            </select>
          </label>
          <label class="text-xs font-bold text-slate-600">현재 상태
            <select class="form-input mt-1.5 block font-normal" onchange="app.changeLiveCatalogAvailability(this.value)">
              <option value="" ${availability === '' ? 'selected' : ''}>전체 상태</option>
              <option value="available" ${availability === 'available' ? 'selected' : ''}>판매 중</option>
              <option value="out_of_stock" ${availability === 'out_of_stock' ? 'selected' : ''}>품절</option>
              <option value="ended" ${availability === 'ended' ? 'selected' : ''}>종료</option>
              <option value="suspect" ${availability === 'suspect' ? 'selected' : ''}>확인 필요</option>
            </select>
          </label>
          <label class="text-xs font-bold text-slate-600">날짜별 보기
            <select id="catalog-date-select" class="form-input mt-1.5 block font-normal min-w-[190px]" onchange="app.changeLiveCatalogDate(this.value)">
              ${this.getCatalogDateOptionsHtml(baseFilteredItems, dateSummary, selectedDate)}
            </select>
          </label>
          <label class="text-xs font-bold text-slate-600">날짜 직접 선택
            <input
              type="date"
              value="${this.escapeHtml(dateInputValue)}"
              class="form-input mt-1.5 block font-normal"
              onchange="app.changeLiveCatalogDate(this.value)"
            />
          </label>
          <label class="text-xs font-bold text-slate-600">상품 검색
            <input
              id="catalog-search-input"
              type="search"
              value="${this.escapeHtml(this.liveCatalogSearch)}"
              placeholder="상품명, 수집처, ID 검색"
              class="form-input mt-1.5 block font-normal w-[220px]"
              oninput="app.handleCatalogSearchInput(this.value)"
            />
          </label>
          ${selectedDate ? '<button type="button" class="btn-secondary" onclick="app.changeLiveCatalogDate(\'\')">전체 날짜 보기</button>' : ''}
        </div>

        <div id="catalog-results-body">
          ${this.getCatalogResultsBodyHtml(computed)}
        </div>
      </section>
      `}
    `;
  },

  handleCrawlingSearch() {
    const input = document.getElementById('crawling-period-input');
    const raw = (input?.value || '').trim();
    if (!raw) {
      this.liveCatalogPeriodFilter = '';
      this.liveCatalogDate = '';
      this.liveCatalogPage = 1;
      this.renderContent();
      return;
    }
    const range = this.parseDateRange(raw);
    if (!range) {
      this.showToast('조회 기간을 YYYY.MM.DD ~ YYYY.MM.DD 형식으로 입력하거나 비워 전체 기간을 조회해 주세요.');
      return;
    }
    this.liveCatalogPeriodFilter = range.join(' ~ ');
    this.liveCatalogDate = '';
    this.liveCatalogPage = 1;
    this.renderContent();
  },

  resetCrawlingPeriod() {
    this.liveCatalogPeriodFilter = '';
    this.liveCatalogDate = '';
    this.liveCatalogPage = 1;
    this.renderContent();
  },
};
