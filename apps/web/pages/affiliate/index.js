const affiliatePage = {
  liveAffiliates: null,

  getAffiliateMetaStore() {
    try {
      return JSON.parse(window.localStorage.getItem('kkulpick-admin-affiliates-meta') || '{}');
    } catch {
      return {};
    }
  },

  saveAffiliateMetaStore(store) {
    try {
      window.localStorage.setItem('kkulpick-admin-affiliates-meta', JSON.stringify(store));
    } catch {
      // 브라우저 저장소를 사용할 수 없는 경우 메모리 상태만 유지한다.
    }
  },

  getRegisteredLocalAffiliates() {
    const store = this.getAffiliateMetaStore();
    return Array.isArray(store.registeredItems) ? store.registeredItems : [];
  },

  formatPriceKrw(raw) {
    if (raw === null || raw === undefined || raw === '') return '미확인';
    const cleaned = String(raw).replace(/[^\d.]/g, '');
    const num = Number(cleaned);
    if (!Number.isFinite(num) || cleaned === '') return String(raw).endsWith('원') ? String(raw) : `${raw}원`;
    return `${Math.round(num).toLocaleString()}원`;
  },

  formatPeriodSummary(startDateTime, endDateTime) {
    const startPart = startDateTime ? startDateTime.slice(5, 10) : '—';
    const endPart = endDateTime ? endDateTime.slice(5, 10) : '종료 없음';
    return `${startPart} ~ ${endPart}`;
  },

  refreshLiveAffiliates() {
    return this.refreshAdminData('liveAffiliates', async (token) => {
      const rows = await this.requestAdminList('/v2/admin/affiliate-offers', token, 'offer_id');
      const needsCatalogLookup = rows.some((row) => !row.name || row.price == null);
      let catalogOffers = this.state.offerCatalog || [];
      if (needsCatalogLookup && !catalogOffers.length) {
        catalogOffers = await this.fetchAllCatalogOffers();
        if (catalogOffers.length) this.state.offerCatalog = catalogOffers;
      }
      const catalogMap = new Map(catalogOffers.map((offer) => [offer.offer_id, offer]));
      const metaStore = this.getAffiliateMetaStore();
      const byIdMeta = metaStore.byId || {};

      const serverItems = rows.map((row) => {
        const offer = catalogMap.get(row.offer_id);
        const meta = byIdMeta[row.offer_id] || {};
        const startDateTime = this.formatKstDateTime(row.starts_at);
        const endDateTime = this.formatKstDateTime(row.ends_at);
        const sourceLabel = offer?.source === 'domeggook' ? '도매꾹' : (offer?.source || row.partner_name || '카탈로그');
        const name = meta.name || row.name || offer?.name || `${row.partner_name} 제휴상품`;
        const rawPrice = meta.rawPrice ?? row.price ?? offer?.price ?? '';
        const price = meta.price || (rawPrice !== '' ? this.formatPriceKrw(rawPrice) : '미확인');
        // 서버에 실제로 저장된 주소를 그대로 보여 준다(사용자가 받는 링크와 같아야 잘못된 링크를 찾을 수 있음, #69).
        const url = row.affiliate_url || meta.url || offer?.current_url || '';
        const domainLabel = (offer?.selected_domain || offer?.kind) === 'food' ? '식품' : '일반 상품';
        const shippingText = offer?.shipping_fee == null ? '수집 가격 기준' : `배송비 ${this.formatPriceKrw(offer.shipping_fee)}`;

        return {
          id: row.offer_id,
          offerId: row.offer_id,
          isServer: true,
          partner: row.partner_name,
          name,
          price,
          rawPrice: String(rawPrice),
          url,
          startsAt: row.starts_at,
          endsAt: row.ends_at,
          startDateTime,
          endDateTime,
          period: this.formatPeriodSummary(startDateTime, endDateTime),
          offerCode: `${row.offer_id} · ${name}`,
          offerTitle: `${domainLabel} · ${name} (${sourceLabel})`,
          offerSub: `${price} · ${shippingText}`,
          lastVerified: this.formatKstDateTime(row.updated_at || offer?.last_checked_at) || startDateTime,
          linkExpiry: endDateTime || '종료 없음',
          enabled: row.enabled,
          version: row.version,
          updatedAt: row.updated_at,
        };
      });

      const items = serverItems;
      if (!items.some((item) => item.id === this.state.selectedAffiliateId)) {
        this.state.selectedAffiliateId = items[0]?.id || null;
      }
      return { items };
    });
  },

  getAffiliateItems() {
    if (this.isLocalAuthDemo()) return this.state.affiliateProducts;
    return this.liveAffiliates?.items || [];
  },

  getAffiliateStatus(item, now) {
    if (item.enabled === false) return '비활성';
    const endMs = item.endsAt
      ? Date.parse(item.endsAt)
      : item.endDateTime
        ? Date.parse(item.endDateTime.replaceAll('.', '-').replace(' ', 'T') + ':00+09:00')
        : NaN;
    if (Number.isFinite(endMs) && endMs <= now) return '종료';
    const startMs = item.startsAt
      ? Date.parse(item.startsAt)
      : item.startDateTime
        ? Date.parse(item.startDateTime.replaceAll('.', '-').replace(' ', 'T') + ':00+09:00')
        : NaN;
    if (Number.isFinite(startMs) && startMs > now) return '시작 예정';
    return item.status || '제휴 중';
  },

  getAffiliateHtml() {
    const sub = this.state.affiliateSubView;
    if (sub === 'create') {
      return this.getAffiliateFormHtml('create');
    }
    if (sub === 'edit') {
      return this.getAffiliateFormHtml('edit');
    }
    return this.getAffiliateListHtml();
  },

  getAffiliateListHtml() {
    const demo = this.isLocalAuthDemo();
    const statusFilter = this.state.affiliateStatusFilter;
    const filtered = this.getFilteredAffiliateProducts();

    const headerActionHtml = demo ? '' : '<button type="button" class="btn-secondary" onclick="app.refreshLiveAffiliates()">새로고침</button>';

    return `
      ${this.renderPageHeader(
        '제휴상품 관리',
        '팀 서버 및 카탈로그 연동 제휴상품의 상품명, 금액, URL과 유효기간을 관리합니다.',
        headerActionHtml
      )}

      ${!demo && this.liveAffiliates?.phase === 'loading' && !this.liveAffiliates.items?.length
        ? '<p class="mb-4 text-sm text-slate-600" role="status">팀 서버의 제휴상품 목록을 불러오는 중입니다...</p>'
        : ''}
      ${!demo && this.liveAffiliates?.phase === 'error'
        ? `<div class="mb-4 flex items-center justify-between rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            <span>${this.escapeHtml(this.liveAffiliates.message)}</span>
            <button type="button" class="text-xs font-semibold text-[#0066ff] underline" onclick="app.refreshLiveAffiliates()">다시 시도</button>
          </div>`
        : ''}

      <!-- 상단 컨트롤 바 (한 줄 배치) -->
      <div class="flex flex-wrap items-end justify-between gap-4 mb-6">
        <div class="flex flex-wrap items-end gap-3">
          <div>
            <label class="block text-xs font-bold text-slate-600 mb-1.5">제휴상품 검색</label>
            <input
              id="affiliate-search-input"
              type="text"
              value="${this.escapeHtml(this.state.affiliateSearch)}"
              placeholder="상품명, 제휴사 또는 ID 검색"
              class="form-input max-w-full w-[340px]"
              oninput="app.handleAffiliateFilterChange(this.value, null)"
            />
          </div>
          <div>
            <label class="block text-xs font-bold text-slate-600 mb-1.5">상태</label>
            <select
              class="form-input max-w-full w-[150px] cursor-pointer"
              onchange="app.handleAffiliateFilterChange(null, this.value)"
            >
              <option value="전체" ${statusFilter === '전체' ? 'selected' : ''}>전체</option>
              <option value="제휴 중" ${statusFilter === '제휴 중' ? 'selected' : ''}>제휴 중</option>
              <option value="종료 예정" ${statusFilter === '종료 예정' ? 'selected' : ''}>7일 이내 종료 예정</option>
              <option value="종료" ${statusFilter === '종료' ? 'selected' : ''}>종료</option>
              <option value="시작 예정" ${statusFilter === '시작 예정' ? 'selected' : ''}>시작 예정</option>
              <option value="비활성" ${statusFilter === '비활성' ? 'selected' : ''}>비활성</option>
            </select>
          </div>
        </div>

        <!-- 우측 버튼 3개 나란히 -->
        <div class="flex items-center gap-2.5">
          <button onclick="app.openAffiliateCreate()" class="btn-primary">
            새 제휴 상품 등록
          </button>
          <button onclick="app.openAffiliateEdit()" class="btn-secondary">
            선택 편집
          </button>
          <button onclick="app.openAffiliateDeleteModal()" class="btn-secondary">
            ${demo ? '선택 삭제' : '선택 삭제/비활성화'}
          </button>
        </div>
      </div>

      <!-- 테이블 영역 -->
      <div class="w-full overflow-x-auto">
        <!-- 테이블 컬럼 헤더 -->
        <div class="grid min-w-[920px] grid-cols-12 items-center px-5 py-3 text-xs font-bold text-slate-500 border-b border-slate-200">
          <div class="col-span-1">제휴상품 ID</div>
          <div class="col-span-1">제휴사</div>
          <div class="col-span-2">상품명</div>
          <div class="col-span-1">금액</div>
          <div class="col-span-3">URL</div>
          <div class="col-span-1">제휴 상태</div>
          <div class="col-span-2">유효기간 · KST</div>
          <div class="col-span-1 text-right">선택</div>
        </div>

        <!-- 데이터 목록 또는 빈 상태 분기 -->
        <div id="affiliate-table-body" class="mt-2">
          ${this.getAffiliateRowsHtml(filtered)}
        </div>
      </div>
    `;
  },

  getAffiliateRowsHtml(filtered) {
    if (filtered.length === 0) {
      return `
        <div class="bg-slate-100/80 text-slate-500 rounded-lg p-4 text-sm">
          등록된 제휴상품이 없습니다. 우측 상단의 <strong>새 제휴 상품 등록</strong> 버튼으로 등록해 보세요.
        </div>
      `;
    }

    const now = Date.now();
    return `
      <div class="space-y-2">
        ${filtered
          .map((item) => {
            const isSelected = item.id === this.state.selectedAffiliateId;
            const rowBorder = isSelected
              ? 'border-[#0066ff] ring-1 ring-[#0066ff]/20 bg-[#ebf3ff]'
              : 'border-slate-200 bg-white hover:border-slate-300';
            const status = this.isAffiliateEndingSoon(item, now) ? '종료 예정' : this.getAffiliateStatus(item, now);
            const shortId = this.isUuid(item.id) ? item.id.slice(0, 8).toUpperCase() : item.id;
            const displayPeriod = item.period || this.formatPeriodSummary(item.startDateTime, item.endDateTime);
            return `
              <div
                data-id="${this.escapeHtml(item.id)}" onclick="app.selectAffiliateItem(this.dataset.id)"
                class="grid min-w-[920px] grid-cols-12 items-center px-5 py-4 rounded-lg border ${rowBorder} text-sm cursor-pointer transition-all"
              >
                <div class="col-span-1 truncate pr-2 font-semibold text-slate-900" title="${this.escapeHtml(item.id)}">${this.escapeHtml(shortId)}</div>
                <div class="col-span-1 truncate pr-2 text-slate-700" title="${this.escapeHtml(item.partner)}">${this.escapeHtml(item.partner)}</div>
                <div class="col-span-2 font-medium text-slate-900 pr-2 truncate" title="${this.escapeHtml(item.name || item.id)}">${this.escapeHtml(item.name || item.id)}</div>
                <div class="col-span-1 text-slate-800 pr-2 truncate">${this.escapeHtml(item.price || '미확인')}</div>
                <div class="col-span-3 text-slate-500 pr-3 truncate text-xs" title="${this.escapeHtml(item.url)}">${this.escapeHtml(item.url)}</div>
                <div class="col-span-1">
                  ${this.renderStatusBadge(status)}
                </div>
                <div class="col-span-2 text-slate-600 text-xs" title="${this.escapeHtml(item.startDateTime || '')} ~ ${this.escapeHtml(item.endDateTime || '종료 없음')}">
                  ${this.escapeHtml(displayPeriod)}
                </div>
                <div class="col-span-1 text-right">
                  <span class="${
                    isSelected ? 'text-[#0066ff] font-bold' : 'text-slate-400 hover:text-slate-600 font-medium'
                  }">
                    ${isSelected ? '선택됨' : '선택'}
                  </span>
                </div>
              </div>
            `;
          })
          .join('')}
      </div>
    `;
  },

  handleAffiliateFilterChange(searchVal, statusVal) {
    if (searchVal !== null) {
      this.state.affiliateSearch = searchVal;
    }
    if (statusVal !== null) {
      this.state.affiliateStatusFilter = statusVal;
    }

    const filtered = this.getFilteredAffiliateProducts();
    if (!filtered.some((item) => item.id === this.state.selectedAffiliateId)) {
      this.state.selectedAffiliateId = filtered[0]?.id || null;
    }

    const tbody = document.getElementById('affiliate-table-body');
    if (tbody) {
      tbody.innerHTML = this.getAffiliateRowsHtml(filtered);
    }
  },

  selectAffiliateItem(id) {
    if (this.state.showDeleteModal) return;
    this.state.selectedAffiliateId = id;
    this.handleAffiliateFilterChange(null, null);
  },

  openAffiliateCreate() {
    this.navigate('affiliate', 'create');
  },

  getFilteredAffiliateProducts() {
    const search = this.state.affiliateSearch.trim().toLowerCase();
    const statusFilter = this.state.affiliateStatusFilter;
    const now = Date.now();

    return this.getAffiliateItems().filter((item) => {
      const matchesSearch =
        !search ||
        (item.name || '').toLowerCase().includes(search) ||
        (item.partner || '').toLowerCase().includes(search) ||
        (item.id || '').toLowerCase().includes(search) ||
        (item.url || '').toLowerCase().includes(search);
      const matchesStatus = statusFilter === '종료 예정'
        ? this.isAffiliateEndingSoon(item, now)
        : statusFilter === '전체' || this.getAffiliateStatus(item, now) === statusFilter;
      return matchesSearch && matchesStatus;
    });
  },

  isAffiliateEndingSoon(item, now) {
    if (this.getAffiliateStatus(item, now) !== '제휴 중' || !item.endDateTime) return false;
    const end = Date.parse(item.endsAt || item.endDateTime.replaceAll('.', '-').replace(' ', 'T') + ':00+09:00');
    return end >= now && end <= now + 7 * 24 * 60 * 60 * 1000;
  },

  getVisibleAffiliateSelection() {
    return this.getFilteredAffiliateProducts().find((item) => item.id === this.state.selectedAffiliateId);
  },

  openAffiliateEdit() {
    const current = this.getVisibleAffiliateSelection();
    if (!current) {
      this.showToast('목록에서 편집할 제휴 상품을 선택해 주세요.');
      return;
    }
    this.navigate('affiliate', 'edit', current.id);
  },

  openAffiliateDeleteModal() {
    const selected = this.getVisibleAffiliateSelection();
    if (!selected) {
      this.showToast('목록에서 제휴 상품을 선택해 주세요.');
      return;
    }
    this.state.showDeleteModal = true;
    this.renderModal();
  },

  closeDeleteModal() {
    this.state.showDeleteModal = false;
    this.renderModal();
  },

  async confirmDeleteAffiliate() {
    const item = this.getVisibleAffiliateSelection();
    const targetId = item?.id;
    if (!this.state.showDeleteModal || !targetId) {
      this.closeDeleteModal();
      return;
    }

    if (!this.isLocalAuthDemo() && item.isServer && item.enabled !== false) {
      const button = document.getElementById('affiliate-delete-submit');
      const status = document.getElementById('affiliate-delete-status');
      if (button) button.disabled = true;
      if (status) status.textContent = '팀 서버에 처리 요청 중입니다...';
      try {
        const query = new URLSearchParams({ expected_version: String(item.version ?? 1) });
        await this.requestAdminAuth(`/v2/admin/affiliate-offers/${encodeURIComponent(item.id)}?${query}`, {
          token: this.adminSession?.token,
          method: 'DELETE',
        });
        this.state.showDeleteModal = false;
        this.renderModal();
        await this.refreshLiveAffiliates();
        this.showToast('제휴 상품을 비활성화했습니다.');
        return;
      } catch (error) {
        if (status) {
          status.textContent = error.status === 403
            ? '비활성화 권한이 없습니다.'
            : '서버 비활성화 처리에 실패했습니다.';
        }
        if (button) button.disabled = false;
        return;
      }
    }

    // 콘솔 등록 제휴 상품 삭제 처리
    this.state.affiliateProducts = this.state.affiliateProducts.filter((p) => p.id !== targetId);
    const metaStore = this.getAffiliateMetaStore();
    if (Array.isArray(metaStore.registeredItems)) {
      metaStore.registeredItems = metaStore.registeredItems.filter((p) => p.id !== targetId);
    }
    this.saveAffiliateMetaStore(metaStore);

    if (this.liveAffiliates?.items) {
      this.liveAffiliates.items = this.liveAffiliates.items.filter((p) => p.id !== targetId);
    }

    this.state.showDeleteModal = false;
    const remaining = this.getAffiliateItems();
    this.state.selectedAffiliateId = remaining[0]?.id || null;
    this.renderModal();
    this.renderContent();
    this.showToast(`${targetId} 제휴 상품이 삭제되었습니다.`);
  },

  // 새 제휴 상품 등록 / 제휴 상품 편집 공통 폼 화면
  getAffiliateFormHtml(mode) {
    const isEdit = mode === 'edit';
    const items = this.getAffiliateItems();
    const item = isEdit
      ? items.find((p) => p.id === this.state.selectedAffiliateId) || items[0]
      : null;

    const title = isEdit ? '제휴 상품 편집' : '새 제휴 상품 등록';
    const subtitle = '제휴사, 상품명, 금액, 판매정보 및 URL을 입력하세요.';

    const defaultStart = this.formatKstDateTime(Date.now());

    const partnerVal = isEdit ? (item?.partner || '') : '';
    const nameVal = isEdit ? (item?.name || '') : '';
    const priceVal = isEdit ? (item?.price || '') : '';
    const offerVal = isEdit ? (item?.offerId || (this.isUuid(item?.id) ? item.id : '') || '') : '';
    const offerLabel = isEdit && offerVal ? (item?.offerCode || `${offerVal} · ${item?.name || item?.partner}`) : '';
    const urlVal = isEdit ? (item?.url || '') : '';
    const startVal = isEdit ? (item?.startDateTime || defaultStart) : defaultStart;
    const endVal = isEdit ? (item?.endDateTime || '') : '';

    const infoBoxTitle = isEdit ? (item?.offerTitle || `${item?.name || ''} · ${item?.partner || ''}`) : '상품명 · 브랜드 · 구분';
    const infoBoxSub = isEdit ? (item?.offerSub || `${item?.price || ''} · 카탈로그 연동`) : '판매정보를 선택하면 상품명·가격·URL이 자동 입력됩니다.';

    const autoManageText = isEdit && item
      ? `제휴상품 ID &nbsp;<strong class="text-slate-800">${this.escapeHtml(item.id)}</strong> &nbsp;&nbsp;·&nbsp;&nbsp; 최근 검증 &nbsp;<strong class="text-slate-800">${this.escapeHtml(item.lastVerified || startVal)}</strong> &nbsp;&nbsp;·&nbsp;&nbsp; 링크 유효기한 &nbsp;<strong class="text-slate-800">${this.escapeHtml(item.linkExpiry || endVal || '종료 없음')}</strong>`
      : '제휴상품 ID, 최근 검증일시, 링크 유효기한은 등록·검증 결과에 따라 자동 표시됩니다.';

    return `
      ${this.renderPageHeader(title, subtitle)}

      <div class="space-y-5">
        <!-- 카드 1 (제휴 연결 정보) -->
        <div class="bg-white border border-slate-200 rounded-xl p-6">
          <h2 class="text-sm font-bold text-slate-900 mb-4">제휴 연결 정보</h2>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
            <!-- 제휴사 * -->
            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1.5">제휴사 <span class="text-[#0066ff]">*</span></label>
              <input
                id="aff-form-partner"
                type="text"
                value="${this.escapeHtml(partnerVal)}"
                placeholder="제휴사명 입력 (예: 도매꾹, 11번가)"
                class="form-input w-full"
              />
            </div>

            <!-- 금액 * -->
            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1.5">금액 <span class="text-[#0066ff]">*</span></label>
              <input
                id="aff-form-price" readonly title="가격은 수집 API에서 갱신됩니다"
                type="text"
                value="${this.escapeHtml(priceVal)}"
                placeholder="금액 입력 (원)"
                class="form-input w-full"
              />
            </div>

            <!-- 판매정보 셀렉트 -->
            <div>
              <label for="aff-form-offer" class="block text-xs font-bold text-slate-700 mb-1.5">판매정보 <span class="text-[#0066ff]">*</span></label>
              <select
                id="aff-form-offer"
                class="form-input w-full cursor-pointer mb-2"
                onchange="app.handleOfferSelectChange(this.value)"
                ${isEdit && item?.isServer ? 'disabled' : ''}
              >
                <option value="">판매정보 선택</option>
                ${isEdit && offerVal ? `<option value="${this.escapeHtml(offerVal)}" selected>${this.escapeHtml(offerLabel)}</option>` : ''}
              </select>
              <input
                id="aff-offer-search"
                type="search"
                aria-label="판매정보 검색"
                aria-controls="aff-form-offer"
                placeholder="상품명, 판매처 또는 ID 검색"
                class="form-input w-full"
                oninput="app.filterOfferCatalog(this.value)"
                disabled
              />
              <p id="aff-offer-status" class="text-xs text-slate-500 mt-1" role="status"></p>
              <button id="aff-offer-retry" type="button" hidden class="text-xs text-[#0066ff] mt-1" onclick="app.loadOfferCatalog()">다시 시도</button>
            </div>

            <!-- 회색 안내 박스 -->
            <div class="flex flex-col justify-end">
              <div id="aff-offer-info-box" class="bg-slate-50 border border-slate-200 rounded-lg px-4 py-3 min-h-[64px] flex flex-col justify-center">
                <div id="aff-offer-info-title" class="text-xs font-bold ${isEdit ? 'text-slate-800' : 'text-slate-600'}">
                  ${this.escapeHtml(infoBoxTitle)}
                </div>
                <div id="aff-offer-info-sub" class="text-xs text-slate-500 mt-0.5">
                  ${this.escapeHtml(infoBoxSub)}
                </div>
                <div id="aff-offer-info-id" class="text-xs text-slate-500 mt-0.5 break-all">${isEdit && (item?.offerId || item?.id) ? `판매정보 ID ${this.escapeHtml(item.offerId || item.id)}` : ''}</div>
              </div>
            </div>

            <!-- 상품명 * -->
            <div class="md:col-span-2">
              <label class="block text-xs font-bold text-slate-700 mb-1.5">상품명 <span class="text-[#0066ff]">*</span></label>
              <input
                id="aff-form-name"
                type="text"
                value="${this.escapeHtml(nameVal)}"
                placeholder="카탈로그 판매정보 선택 시 자동 입력됩니다"
                class="form-input w-full"
              />
            </div>
          </div>
        </div>

        <!-- 카드 2 (URL 및 유효일시) -->
        <div class="bg-white border border-slate-200 rounded-xl p-6 space-y-5">
          <!-- 상단 전체 너비 URL 입력 * -->
          <div>
            <label class="block text-xs font-bold text-slate-700 mb-1.5">URL 입력 <span class="text-[#0066ff]">*</span></label>
            <input
              id="aff-form-url"
              type="text"
              value="${this.escapeHtml(urlVal)}"
              placeholder="https://..."
              class="form-input w-full"
            />
          </div>

          <!-- 하단 2열 유효 시작일시 / 유효 종료일시 -->
          <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1.5">유효 시작일시 <span class="text-[#0066ff]">*</span></label>
              <input
                id="aff-form-start"
                type="text"
                value="${this.escapeHtml(startVal)}"
                placeholder="YYYY.MM.DD HH:mm"
                class="form-input w-full"
              />
            </div>
            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1.5">유효 종료일시 (선택)</label>
              <input
                id="aff-form-end"
                type="text"
                value="${this.escapeHtml(endVal)}"
                placeholder="종료일 없음 (또는 YYYY.MM.DD HH:mm)"
                class="form-input w-full"
              />
            </div>
          </div>
        </div>

        <!-- 카드 3 (자동 관리 정보) -->
        <div class="bg-white border border-slate-200 rounded-xl p-5">
          <div class="text-xs font-bold text-slate-500 mb-1">자동 관리 정보</div>
          <div class="text-sm text-slate-600">
            ${autoManageText}
          </div>
        </div>

        <p id="affiliate-save-status" class="text-sm text-slate-600 empty:hidden" role="status"></p>

        <!-- 우측 하단 버튼 -->
        <div class="flex items-center justify-end gap-3 pt-2">
          <button type="button" onclick="app.navigate('affiliate', 'list')" class="btn-secondary">
            취소
          </button>
          <button id="affiliate-save-submit" type="button" onclick="app.submitAffiliateForm('${mode}')" class="btn-primary disabled:opacity-50">
            ${isEdit ? '변경사항 저장' : '제휴 상품 등록'}
          </button>
        </div>
      </div>
    `;
  },

  async loadOfferCatalog() {
    const select = document.getElementById('aff-form-offer');
    const search = document.getElementById('aff-offer-search');
    const status = document.getElementById('aff-offer-status');
    const retry = document.getElementById('aff-offer-retry');
    if (!select || !search || !status || !retry) return;
    const keepDisabledSelect = select.hasAttribute('disabled') && this.state.affiliateSubView === 'edit';
    select.disabled = true;
    search.disabled = true;
    retry.hidden = true;
    status.textContent = '판매정보를 불러오는 중입니다.';
    try {
      const offers = await this.fetchAllCatalogOffers();
      if (!select.isConnected) return;
      this.state.offerCatalog = offers;
      this.filterOfferCatalog(search.value);
      search.disabled = !offers.length;
    } catch {
      if (!select.isConnected) return;
      status.textContent = window.location.protocol === 'file:'
        ? '판매정보를 불러오려면 로컬 웹 서버에서 이 화면을 열고 카탈로그 API를 실행해 주세요.'
        : '판매정보를 불러오지 못했습니다. API 연결을 확인해 주세요.';
      retry.hidden = false;
    } finally {
      if (select.isConnected && !keepDisabledSelect) {
        select.disabled = false;
      }
    }
  },

  formatOfferPrice(offer) {
    if (!offer || offer.price == null || offer.price === '') return '미확인';
    const num = Number(offer.price);
    if (!Number.isFinite(num)) return String(offer.price);
    if (offer.currency && offer.currency !== 'KRW') {
      return `${num.toLocaleString(undefined, { maximumFractionDigits: 2 })} ${offer.currency}`;
    }
    return this.formatPriceKrw(offer.price);
  },

  filterOfferCatalog(query) {
    const select = document.getElementById('aff-form-offer');
    const status = document.getElementById('aff-offer-status');
    if (!select || !status) return;
    const selectedId = select.value;
    const selectedLabel = select.selectedOptions[0]?.text;
    const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const matches = this.state.offerCatalog.filter((offer) => {
      const searchable = `${offer.name} ${offer.source} ${offer.offer_id}`.toLowerCase();
      return terms.every((term) => searchable.includes(term));
    });

    select.options.length = 1;
    for (const offer of matches) {
      const sourceName = offer.source === 'domeggook' ? '도매꾹' : offer.source;
      const priceText = this.formatOfferPrice(offer);
      const label = `${offer.name} · ${sourceName} · ${priceText}`;
      select.add(new Option(label, offer.offer_id));
    }
    if (selectedId && !matches.some((offer) => offer.offer_id === selectedId)) {
      select.add(new Option(selectedLabel || selectedId, selectedId));
    }
    select.value = selectedId;

    if (matches.length) {
      status.textContent = `카탈로그 판매정보 ${matches.length}건 조회됨`;
    } else {
      status.textContent = terms.length ? '검색 결과가 없습니다.' : '선택할 수 있는 카탈로그 판매정보가 없습니다.';
    }
  },

  handleOfferSelectChange(id) {
    const found = this.state.offerCatalog.find((offer) => offer.offer_id === id);
    const titleEl = document.getElementById('aff-offer-info-title');
    const subEl = document.getElementById('aff-offer-info-sub');
    const idEl = document.getElementById('aff-offer-info-id');
    const partnerEl = document.getElementById('aff-form-partner');
    const nameEl = document.getElementById('aff-form-name');
    const priceEl = document.getElementById('aff-form-price');
    const urlEl = document.getElementById('aff-form-url');

    if (idEl) idEl.textContent = found ? `판매정보 ID ${found.offer_id}` : '';
    if (found) {
      const sourceName = found.source === 'domeggook' ? '도매꾹' : found.source;
      if (titleEl) {
        titleEl.textContent = `${found.name} · ${sourceName}`;
        titleEl.className = 'text-xs font-bold text-slate-800';
      }
      if (subEl) subEl.textContent = this.formatCatalogOfferPrice(found);
      if (partnerEl && !partnerEl.value.trim()) {
        partnerEl.value = sourceName;
      }
      if (nameEl) {
        nameEl.value = found.name;
        nameEl.dataset.catalogValue = nameEl.value;
      }
      if (priceEl) {
        priceEl.value = this.formatOfferPrice(found);
        priceEl.dataset.catalogValue = priceEl.value;
      }
      if (urlEl) {
        urlEl.value = found.current_url;
        urlEl.dataset.catalogValue = urlEl.value;
      }
    } else {
      for (const input of [nameEl, priceEl, urlEl]) {
        if (input && input.value === input.dataset.catalogValue) input.value = '';
      }
      if (titleEl) {
        titleEl.textContent = '상품명 · 브랜드 · 구분';
        titleEl.className = 'text-xs font-bold text-slate-600';
      }
      if (subEl) subEl.textContent = '판매정보를 선택하면 상품명·가격·URL이 자동 입력됩니다.';
    }
  },

  formatCatalogOfferPrice(offer) {
    const shipping = offer.shipping_fee == null ? '미확인' : this.formatPriceKrw(offer.shipping_fee);
    return `${this.formatOfferPrice(offer)} · 배송비 ${shipping}`;
  },

  normalizeDateTimeInput(raw, isEnd = false) {
    const trimmed = (raw || '').trim().replaceAll('-', '.');
    if (!trimmed) return '';
    if (/^\d{4}\.\d{2}\.\d{2}$/.test(trimmed)) {
      return `${trimmed} ${isEnd ? '23:59' : '00:00'}`;
    }
    return trimmed;
  },

  async submitAffiliateForm(mode) {
    const selection = document.getElementById('aff-form-offer')?.value || '';
    const matchedCatalog = this.state.offerCatalog.find((offer) => offer.offer_id === selection);
    const items = this.getAffiliateItems();
    const existing = mode === 'edit'
      ? items.find((item) => item.id === this.state.selectedAffiliateId)
      : null;

    const partner = (document.getElementById('aff-form-partner')?.value || '').trim();
    const typedName = (document.getElementById('aff-form-name')?.value || '').trim();
    const rawPriceField = (document.getElementById('aff-form-price')?.value || '').trim();
    const rawAmountInput = rawPriceField.replace(/\s*(?:원|[A-Z]{3})$/i, '').trim();
    const url = (document.getElementById('aff-form-url')?.value || '').trim();
    const start = this.normalizeDateTimeInput(document.getElementById('aff-form-start')?.value, false);
    const end = this.normalizeDateTimeInput(document.getElementById('aff-form-end')?.value, true);
    const enabled = true;
    const statusEl = document.getElementById('affiliate-save-status');

    if (!partner || !/^https?:\/\//i.test(url) || !URL.canParse(url)) {
      this.showToast('제휴사 이름과 올바른 URL(http/https)을 입력해 주세요.');
      return;
    }

    const amount = rawAmountInput || (matchedCatalog ? String(matchedCatalog.price) : (existing?.rawPrice || '0'));
    if (!/^(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?$/.test(amount)) {
      this.showToast('금액을 숫자로 입력해 주세요.');
      return;
    }

    const dateTime = /^\d{4}\.\d{2}\.\d{2} (?:[01]\d|2[0-3]):[0-5]\d$/;
    if (!dateTime.test(start) || (end && (!dateTime.test(end) || start >= end)) ||
        !this.parseDateRange(`${start.slice(0, 10)} ~ ${(end || start).slice(0, 10)}`)) {
      this.showToast('유효 일시를 YYYY.MM.DD HH:mm 형식으로 입력하고 시작·종료 순서를 확인해 주세요.');
      return;
    }

    const price = matchedCatalog && matchedCatalog.currency && matchedCatalog.currency !== 'KRW'
      ? `${Number(amount.replaceAll(',', '')).toLocaleString(undefined, { maximumFractionDigits: 2 })} ${matchedCatalog.currency}`
      : this.formatPriceKrw(amount);
    const productName = typedName || matchedCatalog?.name || existing?.name || `${partner} 제휴상품`;
    const targetOfferId = existing?.offerId || (this.isUuid(existing?.id) ? existing.id : '') || matchedCatalog?.offer_id || (this.isUuid(selection) ? selection : '');
    const periodStr = this.formatPeriodSummary(start, end);

    // 팀 API 모드에서는 반드시 카탈로그 판매정보 UUID를 선택해 NAS 서버 DB에 저장
    if (!this.isLocalAuthDemo()) {
      if (!this.isUuid(targetOfferId)) {
        this.showToast('판매정보 드롭다운에서 NAS 서버에 등록할 카탈로그 상품을 선택해 주세요.');
        return;
      }
      const button = document.getElementById('affiliate-save-submit');
      if (button) button.disabled = true;
      if (statusEl) statusEl.textContent = '팀 서버에 제휴 상품을 저장하는 중입니다...';

      const toIso = (entry) => entry.replaceAll('.', '-').replace(' ', 'T') + ':00+09:00';
      const startsAt = start === existing?.startDateTime && existing?.startsAt ? existing.startsAt : toIso(start);
      const endsAt = !end ? null : (end === existing?.endDateTime && existing?.endsAt ? existing.endsAt : toIso(end));
      const expectedVersion = existing?.isServer ? (existing.version ?? 0) : 0;
      const path = `/v2/admin/affiliate-offers/${encodeURIComponent(targetOfferId)}`;
      const payload = {
        partner_name: partner,
        affiliate_url: url,
        starts_at: startsAt,
        ends_at: endsAt,
        enabled,
        expected_version: expectedVersion,
      };

      try {
        try {
          await this.requestAdminAuth(path, {
            token: this.adminSession?.token,
            method: 'PUT',
            body: payload,
          });
        } catch (err) {
          // 이미 서버에 있는 제휴(비활성 포함)를 새로 등록하려 한 경우: 서버의 현재 버전으로 한 번만 다시 저장한다.
          // 서버가 거부한 주소(422, AFFILIATE_URL_HOSTS 밖)를 다른 주소로 감싸 우회 저장하지 않는다(devlog #69).
          if (err.status === 409 && mode === 'create') {
            const currentRows = await this.requestAdminList('/v2/admin/affiliate-offers', this.adminSession?.token, 'offer_id');
            const foundRow = currentRows.find((r) => r.offer_id === targetOfferId);
            if (!foundRow) throw err;
            await this.requestAdminAuth(path, {
              token: this.adminSession?.token,
              method: 'PUT',
              body: { ...payload, expected_version: foundRow.version },
            });
          } else {
            throw err;
          }
        }

        const metaStore = this.getAffiliateMetaStore();
        metaStore.byId = metaStore.byId || {};
        metaStore.byId[targetOfferId] = { name: productName, price, rawPrice: amount, url };
        this.saveAffiliateMetaStore(metaStore);

        this.state.affiliateSearch = '';
        this.state.affiliateStatusFilter = '전체';
        this.state.selectedAffiliateId = targetOfferId;
        await this.refreshLiveAffiliates();
        this.navigate('affiliate', 'list', undefined, { replace: true });
        this.showToast(mode === 'edit' ? '제휴 상품 변경사항을 서버에 저장했습니다.' : '새 제휴 상품을 서버에 등록했습니다.');
      } catch (error) {
        if (button) button.disabled = false;
        if (statusEl) {
          statusEl.textContent = error.status === 403
            ? '제휴 상품을 변경할 권한이 없습니다.'
            : error.status === 422
              ? '서버가 이 제휴 URL을 거부했습니다. HTTPS 주소인지, 그 쇼핑몰 주소가 서버 허용 목록(AFFILIATE_URL_HOSTS)에 등록되어 있는지 확인해 주세요.'
              : '팀 서버에 제휴 상품을 저장하지 못했습니다. 입력값과 서버 연결을 확인해 주세요.';
        }
      }
      return;
    }

    // 카탈로그 상품이 아직 DB에 없거나 직접 등록한 경우 콘솔 등록 목록에 반영
    const metaStore = this.getAffiliateMetaStore();
    const registeredItems = Array.isArray(metaStore.registeredItems) ? [...metaStore.registeredItems] : [];
    const nowText = this.formatKstDateTime(Date.now());

    if (mode === 'edit' && existing) {
      const updatedItem = {
        ...existing,
        partner,
        name: productName,
        price,
        rawPrice: amount,
        url,
        enabled,
        status: enabled ? '제휴 중' : '비활성',
        period: periodStr,
        offerTitle: `일반 상품 · ${productName}`,
        offerSub: `${price} · 직접 등록`,
        startDateTime: start,
        endDateTime: end,
        lastVerified: nowText,
        linkExpiry: end || '종료 없음',
      };
      if (this.isLocalAuthDemo()) {
        const idx = this.state.affiliateProducts.findIndex((p) => p.id === existing.id);
        if (idx !== -1) this.state.affiliateProducts[idx] = updatedItem;
      } else {
        const regIdx = registeredItems.findIndex((p) => p.id === existing.id);
        if (regIdx !== -1) registeredItems[regIdx] = updatedItem;
        else registeredItems.unshift(updatedItem);
        metaStore.registeredItems = registeredItems;
        this.saveAffiliateMetaStore(metaStore);
        if (this.liveAffiliates?.items) {
          const liveIdx = this.liveAffiliates.items.findIndex((p) => p.id === existing.id);
          if (liveIdx !== -1) this.liveAffiliates.items[liveIdx] = updatedItem;
        }
      }
      this.showToast('제휴 상품 변경사항을 반영했습니다.');
    } else {
      const existingNums = registeredItems
        .map((it) => Number(String(it.id).replace(/^AF-/, '')))
        .filter((n) => Number.isFinite(n));
      const nextNum = Math.max(this.state.nextAffiliateNumber, ...(existingNums.length ? [Math.max(...existingNums) + 1] : [1]));
      this.state.nextAffiliateNumber = nextNum + 1;
      const newId = `AF-${String(nextNum).padStart(3, '0')}`;
      const newItem = {
        id: newId,
        isServer: false,
        partner,
        name: productName,
        price,
        rawPrice: amount,
        url,
        enabled,
        status: enabled ? '제휴 중' : '비활성',
        period: periodStr,
        offerId: '',
        offerCode: `${newId} · ${productName}`,
        offerTitle: `일반 상품 · ${productName}`,
        offerSub: `${price} · 직접 등록`,
        startDateTime: start,
        endDateTime: end,
        lastVerified: nowText,
        linkExpiry: end || '종료 없음',
      };
      if (this.isLocalAuthDemo()) {
        this.state.affiliateProducts.unshift(newItem);
      } else {
        registeredItems.unshift(newItem);
        metaStore.registeredItems = registeredItems;
        this.saveAffiliateMetaStore(metaStore);
        if (this.liveAffiliates?.items) {
          this.liveAffiliates.items.unshift(newItem);
        }
      }
      this.state.selectedAffiliateId = newId;
      this.state.affiliateSearch = '';
      this.state.affiliateStatusFilter = '전체';
      this.showToast(`새 제휴 상품(${newId})을 등록했습니다.`);
    }

    this.navigate('affiliate', 'list', undefined, { replace: true });
  },

  // 삭제 확인 모달 렌더링
  renderModal() {
    const modalRoot = document.getElementById('modal-root');
    if (!modalRoot) return;

    if (!this.state.showDeleteModal) {
      modalRoot.innerHTML = '';
      return;
    }

    const item = this.getVisibleAffiliateSelection();

    if (!item) {
      modalRoot.innerHTML = '';
      return;
    }

    const isServerItem = !this.isLocalAuthDemo() && item.isServer;

    modalRoot.innerHTML = `
      <div class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 px-4">
        <div class="bg-white rounded-xl shadow-xl border border-slate-200 w-full max-w-[420px] p-6">
          <h3 class="text-xl font-bold text-slate-900">${isServerItem ? '제휴 상품을 비활성화할까요?' : '제휴 상품을 삭제할까요?'}</h3>
          <p class="font-bold text-slate-900 mt-4 text-sm">
            ${this.escapeHtml(item.id)} &nbsp;·&nbsp; ${this.escapeHtml(item.partner)} ${this.escapeHtml(item.name || '')}
          </p>
          <p class="text-sm text-slate-500 mt-1.5">
            ${isServerItem ? '해당 상품의 제휴 노출이 중단됩니다.' : '해당 상품의 제휴 연결이 삭제됩니다.'}
          </p>
          <p id="affiliate-delete-status" class="mt-2 text-sm text-slate-600 empty:hidden" role="status"></p>
          <div class="grid grid-cols-2 gap-3 mt-6">
            <button onclick="app.closeDeleteModal()" class="btn-secondary w-full">
              취소
            </button>
            <button id="affiliate-delete-submit" onclick="app.confirmDeleteAffiliate()" class="btn-danger w-full disabled:opacity-50">
              ${isServerItem ? '비활성화' : '삭제'}
            </button>
          </div>
        </div>
      </div>
    `;
  },
};
