// Real backend bindings override the design preview's in-memory actions.
const consoleBackend = {
  async api(path, options = {}) {
    return this.requestAdminAuth(path, { ...options, token: this.adminSession?.token });
  },
  dateText(value) {
    return value ? new Intl.DateTimeFormat('sv-SE', { timeZone: 'Asia/Seoul', year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false }).format(new Date(value)).replaceAll('-', '.') : '';
  },
  clearConsoleData() {
    Object.assign(this.state, { affiliateProducts:[], customers:[], counselingList:[], crawlingData:[], offerCatalog:[], overview:null, consoleError:'' });
  },
  async loadPages(path, key) {
    const result=[]; let after='';
    // Bounded per screen. A caption makes this display limit explicit.
    for(let n=0;n<10;n++) {
      const page=await this.api(path+'?limit=100'+(after?'&after='+encodeURIComponent(after):''));
      result.push(...page); if(page.length<100) break;
      after=page[page.length-1][key];
    }
    return result;
  },
  async loadConsoleData() {
    this.clearConsoleData();
    try {
      if(this.adminSession.role==='admin') {
        const [members, affiliates, overview] = await Promise.all([
          this.api('/v2/admin/members?limit=100'),this.loadPages('/v2/admin/affiliate-offers','offer_id'),this.api('/v2/admin/overview')]);
        this.state.overview=overview;
        this.state.crawlingData=overview.crawl_days;
        this.state.customers=members.map(m=>({id:m.login_id,userId:m.user_id,subscribed:m.subscribed?'O':'',
          gender:({male:'남성',female:'여성',prefer_not_to_say:'응답 안 함'})[m.gender]||'미등록',
          ageGroup:m.age_decade==null?'미등록':m.age_decade+'대',status:'정상',subStartDate:this.dateText(m.subscription_started_at)||'-'}));
        this.state.affiliateProducts=affiliates.map(a=>({id:a.offer_id,offerId:a.offer_id,version:a.version,partner:a.partner_name,
          name:a.name||a.offer_id,price:a.price==null?'미확인':Number(a.price).toLocaleString()+'원',rawPrice:a.price||'',url:a.affiliate_url,
          status:!a.enabled||(a.ends_at&&Date.parse(a.ends_at)<=Date.now())?'종료':Date.parse(a.starts_at)>Date.now()?'시작 예정':'제휴 중',
          period:this.dateText(a.starts_at)+' ~ '+(this.dateText(a.ends_at)||'종료 없음'),offerCode:a.offer_id,
          offerTitle:a.name||a.offer_id,offerSub:'수집된 가격은 상품 수집 API에서 관리합니다.',startDateTime:this.dateText(a.starts_at),
          endDateTime:this.dateText(a.ends_at),lastVerified:this.dateText(a.updated_at),linkExpiry:this.dateText(a.ends_at)||'종료 없음'}));
      }
      const conversations=await this.loadPages('/v2/admin/support/conversations','conversation_id');
      this.state.counselingList=conversations.map(c=>({id:c.conversation_id,version:c.version,customerId:this.state.customers.find(m=>m.userId===c.owner_id)?.id||c.owner_id,
        title:'고객 문의',category:'이용 문의',status:['resolved','closed'].includes(c.status)?'완료':c.status==='pending_customer'?'진행 중':'대기',
        agent:c.agent_name||'미배정',lastMessageAt:c.updated_at,messages:[]}));
      this.state.counselingSettings=await this.api('/v2/admin/support/settings');
    } catch(error) { this.state.consoleError='데이터를 불러오지 못했습니다. 새로고침으로 다시 시도해 주세요.'; this.showToast(this.state.consoleError); }
  },
  async refreshConsole() { await this.loadConsoleData(); this.renderRoute(); },
  renderContent() {
    consoleLayout.renderContent.call(this);
    const root=document.getElementById('app-content');
    if(this.state.consoleError) {const notice=document.createElement('p');notice.textContent=this.state.consoleError;root.prepend(notice);}
    if(this.state.currentPage==='counseling'&&this.state.counselingSubView==='detail')this.loadMessages(this.state.selectedCounselingId);
  },
  async loadMessages(id) {
    const target=document.getElementById('chat-message-list'); if(!target)return;
    target.textContent='최근 메시지를 불러오는 중입니다.';
    try {
      const messages=await this.api('/v2/admin/support/conversations/'+id+'/messages?limit=100');
      if(!target.isConnected)return;
      target.innerHTML=messages.map(m=>`<div class="bg-slate-100 rounded-lg p-4 mb-3"><strong>${this.escapeHtml(m.sender==='agent'?(m.sender_name||'상담원'):'고객')}</strong><p class="whitespace-pre-wrap">${this.escapeHtml(m.body)}</p><small>${this.escapeHtml(this.dateText(m.created_at))}</small></div>`).join('')||'메시지가 없습니다.';
    } catch {if(target.isConnected)target.textContent='메시지를 불러오지 못했습니다. 목록에서 다시 열어 주세요.';}
  },
  async sendCounselingReply(id=this.state.selectedCounselingId) {
    const input=document.getElementById('chat-reply-input'); const body=input?.value.trim();
    if(!body||this.sendingReply)return;
    this.sendingReply=true;
    const pending=this.pendingReply?.id===id&&this.pendingReply.body===body?this.pendingReply:{id,body,key:crypto.randomUUID()};
    this.pendingReply=pending;
    try {await this.api('/v2/admin/support/conversations/'+id+'/messages',{method:'POST',body:{body,client_message_id:pending.key}});
      this.pendingReply=null;input.value='';await this.refreshConsole();this.showToast('답변을 저장했습니다.');
    } catch {this.showToast('답변 저장을 확인하지 못했습니다. 같은 내용으로 재시도해 주세요.');}
    finally{this.sendingReply=false;}
  },
  async completeCounseling(id=this.state.selectedCounselingId) {
    const c=this.state.counselingList.find(c=>c.id===id);if(!c)return;
    try {await this.api('/v2/admin/support/conversations/'+id,{method:'PATCH',body:{status:'closed',expected_version:c.version}});
      await this.refreshConsole();this.showToast('상담을 완료했습니다.');
    } catch {this.showToast('변경에 실패했습니다. 다른 상담원이 수정했을 수 있습니다. 새로고침해 주세요.');}
  },
  async submitAffiliateForm(mode) {
    if(this.savingAffiliate)return;
    const value=id=>document.getElementById('aff-form-'+id)?.value.trim()||'';
    const previous=this.state.affiliateProducts.find(a=>a.id===this.state.selectedAffiliateId);
    const id=mode==='edit'?previous?.id:value('offer');
    const parseDate=v=>new Date(v.replaceAll('.','-').replace(' ','T')+':00+09:00').toISOString();
    this.savingAffiliate=true;
    try {
      if(!id)throw Error('offer');
      await this.api('/v2/admin/affiliate-offers/'+id,{method:'PUT',body:{partner_name:value('partner'),affiliate_url:value('url'),
        starts_at:parseDate(value('start')),ends_at:value('end')?parseDate(value('end')):null,enabled:true,
        expected_version:mode==='edit'?previous.version:0}});
      await this.loadConsoleData();this.navigate('affiliate');this.showToast('제휴상품을 저장했습니다.');
    } catch {this.showToast('저장 실패: 판매정보, 허용된 HTTPS 주소, KST 날짜와 변경 충돌을 확인해 주세요.');}
    finally{this.savingAffiliate=false;}
  },
  async confirmDeleteAffiliate() {
    const item=this.getVisibleAffiliateSelection();if(!item||!this.state.showDeleteModal)return;
    try {await this.api('/v2/admin/affiliate-offers/'+item.id+'?expected_version='+item.version,{method:'DELETE'});
      this.closeDeleteModal();await this.refreshConsole();this.showToast('제휴 노출을 종료했습니다. 상품 원본은 유지됩니다.');
    }catch{this.showToast('삭제에 실패했습니다. 새로고침 후 다시 시도해 주세요.');}
  },
  async saveCounselingSettings() {
    const value=id=>document.getElementById('cs-setting-'+id)?.value||'';
    try {this.state.counselingSettings=await this.api('/v2/admin/support/settings',{method:'PUT',body:{days:value('days'),startTime:value('start'),endTime:value('end'),awayMessage:value('away'),expected_version:this.state.counselingSettings.version}});
      this.showToast('상담 설정을 DB에 저장했습니다.');
    }catch{this.showToast('설정 저장 실패: 시간 형식 또는 다른 담당자의 변경을 확인해 주세요.');}
  },
  getMainDashboardHtml() {
    const o=this.state.overview;
    if(!o)return '<p>현황 데이터를 불러오지 못했습니다.</p><button onclick="app.refreshConsole()">다시 시도</button>';
    const values=[['전체 회원',o.members],['현재 구독자',o.subscribers],['판매 중 상품',o.available],['보관 상품',o.offers],['최근 30일 모의 결제 합계 (실매출 아님)',Number(o.mock_revenue_krw).toLocaleString()+'원']];
    return this.renderPageHeader('서비스 현황','DB 기준 · 조회 시점의 집계')+'<button class="btn-secondary mb-5" onclick="app.refreshConsole()">새로고침</button><div class="grid grid-cols-2 gap-5">'+values.map(([label,value])=>`<div class="bg-white p-6 rounded-xl border"><p>${label}</p><strong class="text-2xl">${this.escapeHtml(String(value))}</strong></div>`).join('')+'</div>';
  },
  getStatsHtml(){return this.getMainDashboardHtml();},
  getCrawlingHtml(){
    return this.renderPageHeader('상품 크롤링 검토','최근 30일 · KST · API가 접수한 관측 데이터')+'<button class="btn-secondary mb-5" onclick="app.refreshConsole()">새로고침</button><table class="w-full text-left"><thead><tr><th>날짜</th><th>수신 건수</th><th>반영 건수</th></tr></thead><tbody>'+this.state.crawlingData.map(d=>`<tr><td>${this.escapeHtml(d.date)}</td><td>${d.count}</td><td>${d.applied}</td></tr>`).join('')+'</tbody></table>';
  },
  initMainChart(){},initStatsCharts(){},
};
