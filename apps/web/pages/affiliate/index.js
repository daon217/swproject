const affiliatePage = {
  liveAffiliates: null,

  refreshLiveAffiliates() {
    return this.refreshAdminData('liveAffiliates', async (token) => {
      const rows = await this.requestAdminList('/v2/admin/affiliate-offers', token, 'offer_id');
      return {
        items: rows.map((row) => ({
          id: row.offer_id,
          partner: row.partner_name,
          url: row.affiliate_url,
          startsAt: row.starts_at,
          endsAt: row.ends_at,
          startDateTime: this.formatKstDateTime(row.starts_at),
          endDateTime: this.formatKstDateTime(row.ends_at),
          enabled: row.enabled,
          version: row.version,
          updatedAt: row.updated_at,
        })),
      };
    });
  },

  getAffiliateItems() {
    return this.isLocalAuthDemo() ? this.state.affiliateProducts : this.liveAffiliates?.items || [];
  },

  getAffiliateStatus(item, now) {
    if (this.isLocalAuthDemo()) return item.status;
    if (!item.enabled) return '비활성';
    if (item.endsAt && Date.parse(item.endsAt) <= now) return '종료';
    if (Date.parse(item.startsAt) > now) return '시작 예정';
    return '제휴 중';
  },

  getAffiliateHtml() {
    const sub = this.state.affiliateSubView;
    if (!this.isLocalAuthDemo()) {
      if (sub !== 'create' && this.liveAffiliates?.phase !== 'ready') {
        return this.renderPageHeader('제휴상품 관리', '팀 서버의 제휴 상품을 확인합니다.') +
          this.renderAdminDataStatus(this.liveAffiliates,
            '<button type="button" class="btn-secondary" onclick="app.refreshLiveAffiliates()">다시 시도</button>');
      }
      if (sub !== 'list') return this.getLiveAffiliateFormHtml(sub);
    }
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

    const toggleBtnHtml = `
      <button
        onclick="app.toggleAffiliateEmptyState()"
        class="text-xs px-2.5 py-1 rounded border ${
          this.state.affiliateForceEmpty
            ? 'bg-blue-50 border-blue-300 text-[#0066ff] font-semibold'
            : 'bg-white border-slate-200 text-slate-500 hover:text-slate-700'
        } transition-colors"
        title="PPT 60페이지 빈 상태 화면을 즉시 확인합니다"
      >
        [빈 상태 토글${this.state.affiliateForceEmpty ? ': ON' : ''}]
      </button>
    `;

    return `
      ${this.renderPageHeader(
        '제휴상품 관리',
        demo ? '제휴사별 상품명, 금액 및 URL을 관리하세요. · 예시 데이터' : '팀 서버의 제휴사, 연결 URL과 유효기간을 관리합니다.',
        demo ? toggleBtnHtml : '<button type="button" class="btn-secondary" onclick="app.refreshLiveAffiliates()">새로고침</button>'
      )}

      <!-- 상단 컨트롤 바 (한 줄 배치) -->
      <div class="flex flex-wrap items-end justify-between gap-4 mb-6">
        <div class="flex flex-wrap items-end gap-3">
          <div>
            <label class="block text-xs font-bold text-slate-600 mb-1.5">제휴상품 검색</label>
            <input
              id="affiliate-search-input"
              type="text"
              value="${this.escapeHtml(this.state.affiliateSearch)}"
              placeholder="${demo ? '상품명 또는 제휴사 검색' : '판매정보 ID 또는 제휴사 검색'}"
              class="form-input max-w-full w-[340px]"
              oninput="app.handleAffiliateFilterChange(this.value, null)"
            />
          </div>
          <div>
            <label class="block text-xs font-bold text-slate-600 mb-1.5">상태</label>
            <select
              class="form-input max-w-full w-[140px] cursor-pointer"
              onchange="app.handleAffiliateFilterChange(null, this.value)"
            >
              <option value="전체" ${statusFilter === '전체' ? 'selected' : ''}>전체</option>
              <option value="제휴 중" ${statusFilter === '제휴 중' ? 'selected' : ''}>제휴 중</option>
              <option value="종료 예정" ${statusFilter === '종료 예정' ? 'selected' : ''}>7일 이내 종료 예정</option>
              <option value="종료" ${statusFilter === '종료' ? 'selected' : ''}>종료</option>
              ${demo ? '' : `
                <option value="시작 예정" ${statusFilter === '시작 예정' ? 'selected' : ''}>시작 예정</option>
                <option value="비활성" ${statusFilter === '비활성' ? 'selected' : ''}>비활성</option>
              `}
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
            ${demo ? '선택 삭제' : '선택 비활성화'}
          </button>
        </div>
      </div>

      <!-- 테이블 영역 -->
      <div class="w-full overflow-x-auto">
        <!-- 테이블 컬럼 헤더 -->
        <div class="grid min-w-[880px] grid-cols-12 items-center px-5 py-3 text-xs font-bold text-slate-500 border-b border-slate-200">
          <div class="${demo ? 'col-span-1' : 'col-span-2'}">${demo ? '제휴상품 ID' : '판매정보 ID'}</div>
          <div class="${demo ? 'col-span-1' : 'col-span-2'}">제휴사</div>
          ${demo ? '<div class="col-span-2">상품명</div><div class="col-span-1">금액</div>' : ''}
          <div class="col-span-3">URL</div>
          <div class="col-span-1">제휴 상태</div>
          <div class="${demo ? 'col-span-2' : 'col-span-3'}">유효기간 · KST</div>
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
      // 빈 상태 (Empty State - PPT 60p, 63p 화면)
      return `
        <div class="bg-slate-100/80 text-slate-500 rounded-lg p-4 text-sm">
          등록된 제휴상품이 없습니다.
        </div>
      `;
    }

    const now = Date.now();
    const demo = this.isLocalAuthDemo();
    return `
      <div class="space-y-2">
        ${filtered
          .map((item) => {
            const isSelected = item.id === this.state.selectedAffiliateId;
            const rowBorder = isSelected
              ? 'border-[#0066ff] ring-1 ring-[#0066ff]/20 bg-[#ebf3ff]'
              : 'border-slate-200 bg-white hover:border-slate-300';
            const status = this.isAffiliateEndingSoon(item, now) ? '종료 예정' : this.getAffiliateStatus(item, now);
            return `
              <div
                data-id="${this.escapeHtml(item.id)}" onclick="app.selectAffiliateItem(this.dataset.id)"
                class="grid min-w-[880px] grid-cols-12 items-center px-5 py-4 rounded-lg border ${rowBorder} text-sm cursor-pointer transition-all"
              >
                <div class="${demo ? 'col-span-1' : 'col-span-2'} truncate pr-2 font-semibold text-slate-900" title="${this.escapeHtml(item.id)}">${this.escapeHtml(item.id)}</div>
                <div class="${demo ? 'col-span-1' : 'col-span-2'} truncate pr-2 text-slate-700">${this.escapeHtml(item.partner)}</div>
                ${demo ? `
                  <div class="col-span-2 font-medium text-slate-900 pr-2 truncate">${this.escapeHtml(item.name)}</div>
                  <div class="col-span-1 text-slate-800">${this.escapeHtml(item.price)}</div>
                ` : ''}
                <div class="col-span-3 text-slate-500 pr-3 truncate text-xs">${this.escapeHtml(item.url)}</div>
                <div class="col-span-1">
                  ${this.renderStatusBadge(status)}
                </div>
                <div class="${demo ? 'col-span-2' : 'col-span-3'} text-slate-600 text-xs">
                  ${demo ? this.escapeHtml(item.period) : `
                    <div>시작 ${this.escapeHtml(item.startDateTime || '—')}</div>
                    <div>${item.endDateTime ? `종료 ${this.escapeHtml(item.endDateTime)}` : '종료일 없음'}</div>
                  `}
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

  toggleAffiliateEmptyState() {
    this.state.affiliateForceEmpty = !this.state.affiliateForceEmpty;
    this.renderContent();
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
      this.state.selectedAffiliateId = null;
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

    return this.isLocalAuthDemo() && this.state.affiliateForceEmpty
      ? []
      : this.getAffiliateItems().filter((item) => {
          const matchesSearch =
            !search ||
            (item.name || '').toLowerCase().includes(search) ||
            item.partner.toLowerCase().includes(search) ||
            item.id.toLowerCase().includes(search);
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
    if (!this.isLocalAuthDemo() && !selected.enabled) {
      this.showToast('이미 비활성화된 제휴 상품입니다.');
      return;
    }
    this.state.showDeleteModal = true;
    this.renderModal();
  },

  closeDeleteModal() {
    this.state.showDeleteModal = false;
    this.renderModal();
  },

  confirmDeleteAffiliate() {
    const item = this.getVisibleAffiliateSelection();
    const targetId = item?.id;
    if (!this.state.showDeleteModal || !targetId) {
      this.closeDeleteModal();
      return;
    }
    if (!this.isLocalAuthDemo()) {
      if (item.enabled) {
        return this.saveLiveAffiliate(item.id, {
          method: 'DELETE', expectedVersion: item.version, buttonId: 'affiliate-delete-submit',
          successMessage: '제휴 상품을 비활성화했습니다.',
        });
      }
      return;
    }
    this.state.affiliateProducts = this.state.affiliateProducts.filter((p) => p.id !== targetId);
    this.state.showDeleteModal = false;
    if (this.state.affiliateProducts.length > 0) {
      this.state.selectedAffiliateId = this.state.affiliateProducts[0].id;
    } else {
      this.state.selectedAffiliateId = '';
    }
    this.renderModal();
    this.renderContent();
    this.showToast(`${targetId} 제휴 상품이 삭제되었습니다.`);
  },

  getLiveAffiliateFormHtml(mode) {
    const isEdit = mode === 'edit';
    const item = isEdit ? this.getAffiliateItems().find(({ id }) => id === this.state.selectedAffiliateId) : null;
    const title = isEdit ? '제휴 상품 편집' : '새 제휴 상품 등록';
    const header = this.renderPageHeader(title, '카탈로그 판매정보에 제휴사, URL, 유효기간을 연결합니다.');
    if (isEdit && !item) {
      return header + '<p class="mb-4 text-sm text-slate-600">이 판매정보의 제휴 연결을 찾을 수 없습니다.</p><a href="#/affiliate" class="btn-secondary inline-flex">목록으로</a>';
    }

    return `
      ${header}
      <form class="space-y-4 rounded-xl border border-slate-200 bg-white p-5 sm:p-6"
        onsubmit="event.preventDefault(); app.submitLiveAffiliateForm('${mode}')">
        ${item ? `
          <p class="break-all text-sm"><span class="font-semibold">판매정보 ID</span> ${this.escapeHtml(item.id)}</p>
        ` : `
          <div>
            <label for="aff-form-offer" class="block text-sm font-semibold">판매정보</label>
            <input id="aff-offer-search" type="search" aria-label="판매정보 검색" aria-controls="aff-form-offer"
              placeholder="상품명, 판매처 또는 ID 검색" class="form-input mb-2 mt-1 w-full"
              oninput="app.filterOfferCatalog(this.value)" disabled />
            <select id="aff-form-offer" class="form-input w-full" onchange="app.handleOfferSelectChange(this.value)" required disabled>
              <option value="">판매정보 선택</option>
            </select>
            <p id="aff-offer-status" class="mt-1 text-xs text-slate-600" role="status"></p>
            <button id="aff-offer-retry" type="button" hidden class="mt-1 text-xs text-[#0066ff]" onclick="app.loadOfferCatalog()">다시 시도</button>
            <p id="aff-offer-info-title" class="mt-2 text-sm font-semibold"></p>
            <p id="aff-offer-info-sub" class="text-xs text-slate-600"></p>
            <p id="aff-offer-info-id" class="break-all text-xs text-slate-600"></p>
          </div>
        `}
        <label class="block text-sm font-semibold">제휴사
          <input id="aff-form-partner" class="form-input mt-1 w-full" maxlength="100" required value="${this.escapeHtml(item?.partner)}" />
        </label>
        <label class="block text-sm font-semibold">제휴 URL
          <input id="aff-form-url" type="url" class="form-input mt-1 w-full" maxlength="2083" placeholder="https://" required value="${this.escapeHtml(item?.url)}" />
        </label>
        <div class="grid gap-4 md:grid-cols-2">
          <label class="block text-sm font-semibold">시작 일시 · KST
            <input id="aff-form-start" class="form-input mt-1 w-full" placeholder="YYYY.MM.DD HH:mm" required value="${this.escapeHtml(item?.startDateTime)}" />
          </label>
          <label class="block text-sm font-semibold">종료 일시 · KST (선택)
            <input id="aff-form-end" class="form-input mt-1 w-full" placeholder="YYYY.MM.DD HH:mm" value="${this.escapeHtml(item?.endDateTime)}" />
          </label>
        </div>
        <label class="flex items-center gap-2 text-sm">
          <input id="aff-form-enabled" type="checkbox" class="accent-[#0066ff]" ${item?.enabled === false ? '' : 'checked'} /> 제휴 활성화
        </label>
        ${item?.updatedAt ? `<p class="text-xs text-slate-500">최근 수정 ${this.escapeHtml(this.formatKstDateTime(item.updatedAt))} · KST</p>` : ''}
        <p id="affiliate-save-status" class="text-sm text-slate-600 empty:hidden" role="status"></p>
        <div class="flex flex-wrap justify-end gap-2">
          <a href="#/affiliate" class="btn-secondary inline-flex">취소</a>
          <button id="affiliate-save-submit" type="submit" class="btn-primary disabled:opacity-50">${isEdit ? '변경사항 저장' : '제휴 상품 등록'}</button>
        </div>
      </form>
    `;
  },

  submitLiveAffiliateForm(mode) {
    const value = (id) => (document.getElementById(`aff-form-${id}`)?.value || '').trim();
    const item = mode === 'edit' ? this.getAffiliateItems().find(({ id }) => id === this.state.selectedAffiliateId) : null;
    const offerId = item?.id || value('offer');
    const partner = value('partner');
    const url = value('url');
    const start = value('start');
    const end = value('end');
    const status = document.getElementById('affiliate-save-status');
    if (!this.isUuid(offerId) || (mode === 'edit' ? !item : !this.state.offerCatalog.some((offer) => offer.offer_id === offerId))) {
      status.textContent = '판매정보를 선택해 주세요.';
      return;
    }
    const affiliateUrl = URL.canParse(url) ? new URL(url) : null;
    if (!partner || !/^https:\/\//i.test(url) || !affiliateUrl || affiliateUrl.username || affiliateUrl.password) {
      status.textContent = '제휴사 이름과 올바른 HTTPS URL을 입력해 주세요.';
      return;
    }
    const dateTime = /^\d{4}\.\d{2}\.\d{2} (?:[01]\d|2[0-3]):[0-5]\d$/;
    if (!dateTime.test(start) || (end && !dateTime.test(end)) ||
        !this.parseDateRange(`${start.slice(0, 10)} ~ ${(end || start).slice(0, 10)}`)) {
      status.textContent = '시작과 종료 일시를 YYYY.MM.DD HH:mm 형식으로 입력해 주세요.';
      return;
    }
    const toIso = (entry) => entry.replaceAll('.', '-').replace(' ', 'T') + ':00+09:00';
    const startsAt = start === item?.startDateTime ? item.startsAt : toIso(start);
    const endsAt = !end ? null : (end === item?.endDateTime ? item.endsAt : toIso(end));
    if (endsAt && Date.parse(endsAt) <= Date.parse(startsAt)) {
      status.textContent = '종료 일시는 시작 일시보다 늦어야 합니다.';
      return;
    }
    return this.saveLiveAffiliate(offerId, {
      method: 'PUT', buttonId: 'affiliate-save-submit', successMessage: '제휴 상품을 저장했습니다.',
      body: {
        partner_name: partner, affiliate_url: url, starts_at: startsAt, ends_at: endsAt,
        enabled: document.getElementById('aff-form-enabled').checked, expected_version: item?.version ?? 0,
      },
    });
  },

  async saveLiveAffiliate(id, { method, body, expectedVersion, buttonId, successMessage }) {
    const button = document.getElementById(buttonId);
    if (!button || button.disabled || this.adminSession?.role !== 'admin' || this.isLocalAuthDemo()) return;
    const session = this.adminSession;
    const route = window.location.hash;
    const status = document.getElementById(method === 'PUT' ? 'affiliate-save-status' : 'affiliate-delete-status');
    button.disabled = true;
    status.textContent = '팀 서버에 저장하는 중입니다.';
    const path = `/v2/admin/affiliate-offers/${encodeURIComponent(id)}`;
    try {
      const query = method === 'DELETE' ? `?${new URLSearchParams({ expected_version: expectedVersion })}` : '';
      await this.requestAdminAuth(path + query, { token: session.token, method, body });
      if (this.adminSession !== session || window.location.hash !== route || !button.isConnected) return;
      this.navigate('affiliate', 'list', undefined, { replace: true });
      this.showToast(successMessage);
    } catch (error) {
      if (this.adminSession !== session || !button.isConnected) return;
      const messages = {
        401: '로그인 세션이 만료되었습니다. 다시 로그인해 주세요.',
        403: '제휴 상품을 변경할 권한이 없습니다.',
        404: '판매정보를 찾을 수 없습니다.',
        409: '이미 등록됐거나 다른 변경이 반영됐습니다. 목록을 다시 열어 확인해 주세요.',
        422: '입력값을 확인해 주세요. 제휴 URL은 서버가 허용한 HTTPS 주소여야 합니다.',
      };
      status.textContent = messages[error.status] || '팀 서버에서 저장 결과를 확인하지 못했습니다.';
    } finally {
      button.disabled = false;
    }
  },

  // 새 제휴 상품 등록 / 제휴 상품 편집 공통 폼 화면
  getAffiliateFormHtml(mode) {
    const isEdit = mode === 'edit';
    const item = isEdit
      ? this.state.affiliateProducts.find((p) => p.id === this.state.selectedAffiliateId) ||
        this.state.affiliateProducts[0]
      : null;

    const title = isEdit ? '제휴 상품 편집' : '새 제휴 상품 등록';
    const subtitle = '제휴사, 금액, 판매정보 및 URL을 입력하세요.';

    const partnerVal = isEdit ? item.partner : '';
    const priceVal = isEdit ? item.price : '';
    const offerVal = isEdit ? item.offerId || item.offerCode : '';
    const urlVal = isEdit ? item.url : '';
    const startVal = isEdit ? item.startDateTime : '';
    const endVal = isEdit ? item.endDateTime : '';

    const infoBoxTitle = isEdit ? item.offerTitle : '상품명 · 브랜드 · 구분';
    const infoBoxSub = isEdit ? item.offerSub : '판매정보를 선택하면 가격과 판매 URL이 표시됩니다.';

    const autoManageText = isEdit
      ? `제휴상품 ID &nbsp;<strong class="text-slate-800">${item.id}</strong> &nbsp;&nbsp;·&nbsp;&nbsp; 최근 검증 &nbsp;<strong class="text-slate-800">${item.lastVerified}</strong> &nbsp;&nbsp;·&nbsp;&nbsp; 링크 유효기한 &nbsp;<strong class="text-slate-800">${item.linkExpiry}</strong>`
      : '제휴상품 ID, 최근 검증일시, 링크 유효기한은 등록·검증 결과에 따라 자동 표시됩니다.';

    return `
      ${this.renderPageHeader(title, subtitle)}

      <div class="space-y-5">
        <!-- 카드 1 (제휴 연결 정보) -->
        <div class="bg-white border border-slate-200 rounded-xl p-6">
          <h2 class="text-sm font-bold text-slate-900 mb-4">제휴 연결 정보</h2>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-5">
            <!-- 좌상단: 제휴사 * -->
            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1.5">제휴사 <span class="text-[#0066ff]">*</span></label>
              <input
                id="aff-form-partner"
                type="text"
                value="${this.escapeHtml(partnerVal)}"
                placeholder="제휴사명 입력"
                class="form-input w-full"
              />
            </div>

            <!-- 우상단: 금액 * -->
            <div>
              <label class="block text-xs font-bold text-slate-700 mb-1.5">금액 <span class="text-[#0066ff]">*</span></label>
              <input
                id="aff-form-price"
                type="text"
                value="${this.escapeHtml(priceVal)}"
                placeholder="금액 입력 (원)"
                class="form-input w-full"
              />
            </div>

            <!-- 좌하단: 판매정보 * 셀렉트 -->
            <div>
              <label for="aff-form-offer" class="block text-xs font-bold text-slate-700 mb-1.5">판매정보 <span class="text-[#0066ff]">*</span></label>
              <input
                id="aff-offer-search"
                type="search"
                aria-label="판매정보 검색"
                aria-controls="aff-form-offer"
                placeholder="상품명, 판매처 또는 ID 검색"
                class="form-input w-full mb-2"
                oninput="app.filterOfferCatalog(this.value)"
                disabled
              />
              <select
                id="aff-form-offer"
                class="form-input w-full cursor-pointer"
                onchange="app.handleOfferSelectChange(this.value)"
              >
                <option value="">판매정보 선택</option>
                ${isEdit ? `<option value="${this.escapeHtml(offerVal)}" selected>${this.escapeHtml(item.offerCode)}</option>` : ''}
              </select>
              <p id="aff-offer-status" class="text-xs text-slate-500 mt-1" role="status"></p>
              <button id="aff-offer-retry" type="button" hidden class="text-xs text-[#0066ff] mt-1" onclick="app.loadOfferCatalog()">다시 시도</button>
            </div>

            <!-- 우하단: 회색 안내 박스 -->
            <div class="flex flex-col justify-end">
              <div id="aff-offer-info-box" class="bg-slate-50 border border-slate-200 rounded-lg px-4 py-3 min-h-[64px] flex flex-col justify-center">
                <div id="aff-offer-info-title" class="text-xs font-bold ${isEdit ? 'text-slate-800' : 'text-slate-600'}">
                  ${this.escapeHtml(infoBoxTitle)}
                </div>
                <div id="aff-offer-info-sub" class="text-xs text-slate-500 mt-0.5">
                  ${this.escapeHtml(infoBoxSub)}
                </div>
                <div id="aff-offer-info-id" class="text-xs text-slate-500 mt-0.5 break-all">${isEdit && item.offerId ? `판매정보 ID ${this.escapeHtml(item.offerId)}` : ''}</div>
              </div>
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
              placeholder="URL을 입력해 주세요"
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
                placeholder="종료일 없음"
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

        <!-- 우측 하단 버튼 -->
        <div class="flex items-center justify-end gap-3 pt-2">
          <button onclick="app.navigate('affiliate', 'list')" class="btn-secondary">
            취소
          </button>
          <button onclick="app.submitAffiliateForm('${mode}')" class="btn-primary">
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
    select.disabled = true;
    search.disabled = true;
    retry.hidden = true;
    status.textContent = '판매정보를 불러오는 중입니다.';
    try {
      const url = new URL('/v2/offers', this.getApiBase());
      url.search = new URLSearchParams({ selected_domain: 'product', currency: 'KRW', limit: '100' });
      const offers = new Map();
      const cursors = new Set();
      do {
        const response = await fetch(url, { signal: AbortSignal.timeout(5000) });
        if (!select.isConnected) return;
        if (!response.ok) throw new Error('Catalog request failed');
        const { items, next_cursor: cursor } = await response.json();
        if (!select.isConnected) return;
        for (const offer of items) offers.set(offer.offer_id, offer);
        if (!cursor) break;
        if (cursors.has(cursor)) throw new Error('Repeated catalog cursor');
        cursors.add(cursor);
        url.searchParams.set('after', cursor);
      } while (true);

      this.state.offerCatalog = [...offers.values()];
      this.filterOfferCatalog(search.value);
      search.disabled = !offers.size;
    } catch {
      if (!select.isConnected) return;
      status.textContent = window.location.protocol === 'file:'
        ? '판매정보를 불러오려면 로컬 웹 서버에서 이 화면을 열고 카탈로그 API를 실행해 주세요.'
        : '판매정보를 불러오지 못했습니다. API 연결을 확인해 주세요.';
      retry.hidden = false;
    } finally {
      select.disabled = false;
    }
  },

  filterOfferCatalog(query) {
    const select = document.getElementById('aff-form-offer');
    const status = document.getElementById('aff-offer-status');
    const selectedId = select.value;
    const selectedLabel = select.selectedOptions[0]?.text;
    const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
    const matches = this.state.offerCatalog.filter((offer) => {
      const searchable = `${offer.name} ${offer.source} ${offer.offer_id}`.toLowerCase();
      return terms.every((term) => searchable.includes(term));
    });

    select.options.length = 1;
    for (const offer of matches) {
      const label = `${offer.name} · ${offer.source} · ${offer.price}원`;
      select.add(new Option(label, offer.offer_id));
    }
    if (selectedId && !matches.some((offer) => offer.offer_id === selectedId)) {
      select.add(new Option(selectedLabel, selectedId));
    }
    select.value = selectedId;

    if (matches.length) {
      status.textContent = `판매정보 ${matches.length}건`;
    } else {
      status.textContent = terms.length ? '검색 결과가 없습니다.' : '선택할 수 있는 판매정보가 없습니다.';
    }
  },

  handleOfferSelectChange(id) {
    const found = this.state.offerCatalog.find((offer) => offer.offer_id === id);
    const titleEl = document.getElementById('aff-offer-info-title');
    const subEl = document.getElementById('aff-offer-info-sub');
    const idEl = document.getElementById('aff-offer-info-id');
    const priceEl = document.getElementById('aff-form-price');
    const urlEl = document.getElementById('aff-form-url');

    if (idEl) idEl.textContent = found ? `판매정보 ID ${found.offer_id}` : '';
    if (found) {
      if (titleEl) {
        titleEl.textContent = `${found.name} · ${found.source}`;
        titleEl.className = 'text-xs font-bold text-slate-800';
      }
      if (subEl) subEl.textContent = this.formatCatalogOfferPrice(found);
      if (priceEl) {
        priceEl.value = `${found.price}원`;
        priceEl.dataset.catalogValue = priceEl.value;
      }
      if (urlEl) {
        urlEl.value = found.current_url;
        urlEl.dataset.catalogValue = urlEl.value;
      }
    } else {
      for (const input of [priceEl, urlEl]) {
        if (input && input.value === input.dataset.catalogValue) input.value = '';
      }
      if (titleEl) {
        titleEl.textContent = '상품명 · 브랜드 · 구분';
        titleEl.className = 'text-xs font-bold text-slate-600';
      }
      if (subEl) subEl.textContent = '판매정보를 선택하면 가격과 판매 URL이 표시됩니다.';
    }
  },

  formatCatalogOfferPrice(offer) {
    const shipping = offer.shipping_fee == null ? '미확인' : `${offer.shipping_fee}원`;
    return `${offer.price}원 · 배송비 ${shipping}`;
  },

  submitAffiliateForm(mode) {
    const selection = document.getElementById('aff-form-offer')?.value;
    const matchedCatalog = this.state.offerCatalog.find((offer) => offer.offer_id === selection);
    const existing = mode === 'edit'
      ? this.state.affiliateProducts.find((item) => item.id === this.state.selectedAffiliateId)
      : null;
    if (!matchedCatalog && (!existing || selection !== (existing.offerId || existing.offerCode))) {
      this.showToast('판매정보를 선택해 주세요.');
      return;
    }

    const partner = (document.getElementById('aff-form-partner')?.value || '').trim();
    const amount = (document.getElementById('aff-form-price')?.value || '').trim().replace(/\s*원$/, '');
    const url = (document.getElementById('aff-form-url')?.value || '').trim();
    const start = (document.getElementById('aff-form-start')?.value || '').trim();
    const end = (document.getElementById('aff-form-end')?.value || '').trim();
    if (!partner || !/^(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?$/.test(amount) ||
        !/^https?:\/\//i.test(url) || !URL.canParse(url)) {
      this.showToast('제휴사, 금액, 판매 URL을 확인해 주세요.');
      return;
    }
    const dateTime = /^\d{4}\.\d{2}\.\d{2} (?:[01]\d|2[0-3]):[0-5]\d$/;
    if (!dateTime.test(start) || (end && (!dateTime.test(end) || start > end)) ||
        !this.parseDateRange(`${start.slice(0, 10)} ~ ${(end || start).slice(0, 10)}`)) {
      this.showToast('유효 일시를 YYYY.MM.DD HH:mm 형식으로 입력하고 시작·종료 순서를 확인해 주세요.');
      return;
    }
    const price = `${amount}원`;

    const productName = matchedCatalog ? matchedCatalog.name : existing.name;
    const offerId = matchedCatalog ? matchedCatalog.offer_id : existing.offerId;
    const offerCode = matchedCatalog ? `${offerId} · ${productName}` : existing.offerCode;
    const offerTitle = matchedCatalog ? `${productName} · ${matchedCatalog.source}` : existing.offerTitle;
    const offerSub = matchedCatalog ? this.formatCatalogOfferPrice(matchedCatalog) : existing.offerSub;

    // 기간 포맷 (예: 10.01 ~ 12.31 또는 10.01 ~ 종료 없음)
    const periodStr = `${start.slice(5, 10)} ~ ${end ? end.slice(5, 10) : '종료 없음'}`;

    if (mode === 'edit') {
      const idx = this.state.affiliateProducts.findIndex((p) => p.id === this.state.selectedAffiliateId);
      if (idx !== -1) {
        this.state.affiliateProducts[idx] = {
          ...this.state.affiliateProducts[idx],
          partner,
          name: productName,
          price,
          url,
          period: periodStr,
          offerId,
          offerCode,
          offerTitle,
          offerSub,
          startDateTime: start,
          endDateTime: end,
        };
      }
      this.showToast('현재 세션에 제휴 상품 변경사항을 반영했습니다.');
    } else {
      const newId = `AF-${String(this.state.nextAffiliateNumber++).padStart(3, '0')}`;
      const newItem = {
        id: newId,
        partner,
        name: productName,
        price,
        url,
        status: '제휴 중',
        period: periodStr,
        offerId,
        offerCode,
        offerTitle,
        offerSub,
        startDateTime: start,
        endDateTime: end,
        lastVerified: '2026.10.12 09:00',
        linkExpiry: '2026.10.13 09:00',
      };
      this.state.affiliateProducts.unshift(newItem);
      this.state.selectedAffiliateId = newId;
      this.state.affiliateForceEmpty = false;
      this.showToast(`현재 세션에 새 제휴 상품(${newId})을 등록했습니다.`);
    }

    this.navigate('affiliate', 'list', undefined, { replace: true });
  },

  // 삭제 확인 모달 렌더링 (PPT 62p)
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

    modalRoot.innerHTML = `
      <div class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 px-4">
        <div class="bg-white rounded-xl shadow-xl border border-slate-200 w-full max-w-[420px] p-6">
          <h3 class="text-xl font-bold text-slate-900">${this.isLocalAuthDemo() ? '제휴 상품을 삭제할까요?' : '제휴 상품을 비활성화할까요?'}</h3>
          <p class="font-bold text-slate-900 mt-4 text-sm">
            ${this.escapeHtml(item.id)} &nbsp;·&nbsp; ${this.escapeHtml(item.partner)} ${this.escapeHtml(item.name)}
          </p>
          <p class="text-sm text-slate-500 mt-1.5">
            ${this.isLocalAuthDemo() ? '해당 상품의 제휴 연결이 삭제됩니다.' : '해당 상품의 제휴 노출이 중단됩니다.'}
          </p>
          <p id="affiliate-delete-status" class="mt-2 text-sm text-slate-600 empty:hidden" role="status"></p>
          <div class="grid grid-cols-2 gap-3 mt-6">
            <button onclick="app.closeDeleteModal()" class="btn-secondary w-full">
              취소
            </button>
            <button id="affiliate-delete-submit" onclick="app.confirmDeleteAffiliate()" class="btn-danger w-full disabled:opacity-50">
              ${this.isLocalAuthDemo() ? '삭제' : '비활성화'}
            </button>
          </div>
        </div>
      </div>
    `;
  },
};
