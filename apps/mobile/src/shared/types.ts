// 기술 명세서 17장의 요청·응답 형태를 프론트에서 쓰는 타입으로 옮긴 것.
// 경로·필드는 '보완안' 기준이며 백엔드 OpenAPI 확정 시 맞춰 수정한다.

// 명세의 other는 2026-11-16 결정으로 제외(여성·남성·응답하지 않음 + 미입력 NULL)
export type Gender = 'male' | 'female' | 'prefer_not_to_say';

export interface Me {
  user_id: string;
  login_id: string;
  /** 서버 현재 유효 권한 기준. 표시용 회원 유형보다 entitlement가 우선이다. */
  premium: boolean;
  profile: Profile;
}

export interface Profile {
  version: number;
  gender: Gender | null;
  birth_date: string | null; // YYYY-MM-DD
  include_used: boolean;
  allergies: string[]; // 공개 성분 코드
  /** 재료 필터(프리미엄 식품 전용). 명세 D07 결정 대상이며 Figma 기준으로 구현. */
  ingredient_filter: IngredientFilter;
}

export interface IngredientFilter {
  avoid: string[];
  prefer: string[];
}

export interface SignupRequest {
  login_id: string;
  password: string;
  password_confirmation: string;
  consent_version: string;
  consent_accepted: boolean;
  allergies: string[];
  gender: Gender | null;
  birth_date: string | null;
}

export interface ProfilePatch {
  expected_version: number;
  gender?: Gender | null;
  birth_date?: string | null;
  include_used?: boolean;
  allergies?: string[];
  ingredient_filter?: IngredientFilter;
}

// ---- 분석 ----

export type AnalysisState = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
export type ResultKind = 'recommendation' | 'empty' | 'ingredient_unknown';
export type IngredientStatus = 'complete' | 'partial' | 'not_found' | 'error' | 'not_applicable';
export type Domain = 'product' | 'food';

export interface CreateAnalysisRequest {
  /** 앱 내 브라우저 캡처 파일(react-native-view-shot tmpfile) */
  image: { uri: string } | null;
  page_url: string;
  page_session_id: string;
  page_revision: number;
  request_key: string;
}

export interface CreateAnalysisResponse {
  analysis_id: string;
  state: AnalysisState;
  status_url: string;
}

export interface OfferCard {
  offer_id: string;
  name: string;
  subtitle: string;
  price: string; // 정밀도 손실 없는 문자열
  currency: string;
  observed_at: string;
  availability: 'available' | 'out_of_stock';
  url: string; // 서버가 검증한 안전한 링크
  reason: string;
  affiliate: boolean;
  image_kind: Domain;
}

export type SectionKind = 'ai' | 'used' | 'alternative';

export interface ResultSection {
  kind: SectionKind;
  /** 'loading'이면 해당 구역만 아직 분석 중 */
  state: 'loading' | 'ready' | 'failed';
  items: OfferCard[];
  /** 서버가 허용한 공개 개수. 잠긴 후보의 URL·근거는 응답에 포함되지 않는다. */
  locked_count: number;
  lock_reason: 'premium_required' | null;
  footnote: string | null;
}

export interface AllergyWarning {
  type: 'allergy';
  allergen: string;
  /** contains | may_contain | unknown */
  evidence: 'contains' | 'may_contain' | 'unknown';
  message: string;
}

export interface Analysis {
  analysis_id: string;
  state: AnalysisState;
  result_kind: ResultKind | null;
  ingredient_status: IngredientStatus;
  page_session_id: string;
  page_revision: number;
  selected_domain: Domain | null;
  source_summary: Record<string, 'success' | 'empty' | 'failed' | 'blocked' | 'unsupported'>;
  warnings: AllergyWarning[];
  sections: ResultSection[];
  applied_filter: IngredientFilter | null;
  premium: boolean;
  error: { code: string; message: string; retryable: boolean } | null;
}

export interface AnalysisHistoryItem {
  analysis_id: string;
  created_at: string;
  card: OfferCard;
}

// ---- 구독·결제 ----

export interface SubscriptionPlan {
  plan_id: string;
  name: string;
  /** 요금 미확정(D01)이면 null */
  price: string | null;
  currency: string;
  interval: 'month' | 'year';
  benefits: string[];
}

export type PaymentMethod = 'card' | 'bank_transfer' | 'naverpay' | 'kakaopay' | 'tosspay';

export interface CreateSubscriptionResponse {
  subscription_id: string;
  invoice_id: string;
  payment_id: string;
}

export interface SubscriptionStatus {
  active: boolean;
  entitlement_end: string | null;
  cancel_at_period_end: boolean;
}

// ---- 고객센터 ----

export interface SupportMessage {
  message_id: string;
  sequence_no: number;
  sender: 'member' | 'agent';
  sender_name: string | null;
  body: string;
  created_at: string;
}

export interface SupportConversation {
  conversation_id: string;
  agent_name: string | null;
  status: 'open' | 'pending_customer' | 'pending_agent' | 'resolved' | 'closed';
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public retryable = false,
  ) {
    super(message);
  }
}
