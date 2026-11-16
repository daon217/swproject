import type {
  Analysis,
  AnalysisHistoryItem,
  CreateAnalysisRequest,
  CreateAnalysisResponse,
  CreateSubscriptionResponse,
  Me,
  OfferCard,
  PaymentMethod,
  ProfilePatch,
  SignupRequest,
  SubscriptionPlan,
  SubscriptionStatus,
  SupportConversation,
  SupportMessage,
} from '../types';
import { createHttpApi } from './http';
import { createMockApi } from './mock';

/** 화면이 사용하는 업무 API. 경로는 기술 명세서 17.3 기준(보완안 포함). */
export interface KkulpickApi {
  // 인증·회원
  signup(req: SignupRequest): Promise<{ user_id: string }>;
  /** 아이디 중복확인(GET /v2/auth/login-id-availability). 가입 저장 시 서버가 다시 검사한다. */
  checkLoginId(login_id: string): Promise<{ available: boolean }>;
  login(login_id: string, password: string): Promise<{ token: string }>;
  logout(): Promise<void>;
  getMe(): Promise<Me>;
  updateProfile(patch: ProfilePatch): Promise<Me>;
  changePassword(current: string, next: string, confirmation: string): Promise<void>;

  // 분석
  createAnalysis(req: CreateAnalysisRequest): Promise<CreateAnalysisResponse>;
  getAnalysis(analysis_id: string): Promise<Analysis>;
  cancelAnalysis(analysis_id: string): Promise<void>;
  listHistory(): Promise<AnalysisHistoryItem[]>;
  /** 기록이 없는 비회원 시작 화면용 추천 상품(제휴 상품 포함, 보완안 경로) */
  listFeatured(): Promise<OfferCard[]>;
  deleteAllHistory(): Promise<{ request_id: string }>;

  // 구독·결제 (실제 VAN/PG 연동 없음: 흐름만 구현)
  listPlans(): Promise<SubscriptionPlan[]>;
  createSubscription(plan_id: string, method: PaymentMethod, idempotency_key: string): Promise<CreateSubscriptionResponse>;
  getSubscription(): Promise<SubscriptionStatus>;

  // 고객센터
  getSupportConversation(): Promise<SupportConversation>;
  listSupportMessages(conversation_id: string): Promise<SupportMessage[]>;
  sendSupportMessage(conversation_id: string, body: string, client_message_id: string): Promise<SupportMessage>;
}

const baseUrl = process.env.EXPO_PUBLIC_API_BASE_URL?.trim();

export const api: KkulpickApi = baseUrl ? createHttpApi(baseUrl) : createMockApi();
export const isMockApi = !baseUrl;
