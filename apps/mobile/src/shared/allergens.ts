// 알레르기 선택 항목. 코드는 공개 성분 코드(ingredients.code)를 가정하며 서버가 유효성을 다시 검사한다.
// - 식품: 식품 알레르기 표시 대상 19종 + 자주 보고되는 식품(견과류·과일·생선 등). 식품 페이지에서만 경고한다.
// - 피부: 화장품·생활용품 등에서 피부 질환을 일으키기 쉬운 접촉 성분. 프로필에 저장만 하고 상품 페이지에서는 경고하지 않는다.
// 이 파일은 apps/extension/src/shared/allergens.ts 와 같은 내용을 유지한다.

import type { AllergyWarning, Domain } from './types';

export type AllergenKind = 'food' | 'skin';

export interface AllergenGroup {
  group: string;
  kind: AllergenKind;
  items: { code: string; label: string }[];
}

export const ALLERGEN_GROUPS: AllergenGroup[] = [
  {
    group: '식품',
    kind: 'food',
    items: [
      { code: 'egg', label: '달걀(알류)' },
      { code: 'milk', label: '우유' },
      { code: 'buckwheat', label: '메밀' },
      { code: 'peanut', label: '땅콩' },
      { code: 'soybean', label: '대두' },
      { code: 'wheat', label: '밀' },
      { code: 'mackerel', label: '고등어' },
      { code: 'crab', label: '게' },
      { code: 'shrimp', label: '새우' },
      { code: 'pork', label: '돼지고기' },
      { code: 'peach', label: '복숭아' },
      { code: 'tomato', label: '토마토' },
      { code: 'sulfite', label: '아황산류' },
      { code: 'walnut', label: '호두' },
      { code: 'chicken', label: '닭고기' },
      { code: 'beef', label: '쇠고기' },
      { code: 'squid', label: '오징어' },
      { code: 'shellfish', label: '조개류(굴·전복·홍합)' },
      { code: 'pine_nut', label: '잣' },
      { code: 'almond', label: '아몬드' },
      { code: 'cashew', label: '캐슈넛' },
      { code: 'pistachio', label: '피스타치오' },
      { code: 'hazelnut', label: '헤이즐넛' },
      { code: 'macadamia', label: '마카다미아' },
      { code: 'sesame', label: '참깨' },
      { code: 'kiwi', label: '키위' },
      { code: 'banana', label: '바나나' },
      { code: 'apple', label: '사과' },
      { code: 'mango', label: '망고' },
      { code: 'salmon', label: '연어' },
      { code: 'tuna', label: '참치' },
      { code: 'octopus', label: '문어·낙지' },
      { code: 'lamb', label: '양고기' },
      { code: 'celery', label: '셀러리' },
      { code: 'mustard', label: '겨자' },
      { code: 'corn', label: '옥수수' },
    ],
  },
  {
    group: '피부 질환',
    kind: 'skin',
    items: [
      { code: 'nickel', label: '니켈·금속' },
      { code: 'latex', label: '라텍스' },
      { code: 'fragrance', label: '향료' },
      { code: 'preservative', label: '방부제(파라벤 등)' },
      { code: 'hair_dye_ppd', label: '염색약 성분(PPD)' },
      { code: 'lanolin', label: '라놀린' },
      { code: 'alcohol', label: '알코올(에탄올)' },
      { code: 'isothiazolinone', label: '메칠이소치아졸리논(MIT·CMIT)' },
      { code: 'formaldehyde', label: '포름알데하이드' },
      { code: 'sls', label: '계면활성제(SLS·SLES)' },
      { code: 'cocamidopropyl_betaine', label: '코카미도프로필베타인' },
      { code: 'propylene_glycol', label: '프로필렌글라이콜' },
      { code: 'oxybenzone', label: '자외선 차단 성분(옥시벤존)' },
      { code: 'essential_oil', label: '에센셜 오일(티트리 등)' },
      { code: 'cobalt_chrome', label: '코발트·크롬' },
    ],
  },
];

// 예전에 고를 수 있던 항목(호흡기·약물·곤충). 저장된 프로필에 남아 있을 수 있어 이름만 남긴다.
// 선택 화면에는 나오지 않고, 프로필을 다시 저장하면 빠진다(knownAllergens).
const RETIRED_LABELS: Record<string, string> = {
  pollen: '꽃가루',
  house_dust_mite: '집먼지진드기',
  animal_dander: '동물 털·비듬',
  mold: '곰팡이',
  cockroach: '바퀴벌레',
  penicillin: '페니실린계 항생제',
  aspirin: '아스피린',
  nsaid: '소염진통제(NSAIDs)',
  sulfonamide: '설파제',
  bee_venom: '벌독',
  mosquito: '모기',
};

const LABELS = new Map(ALLERGEN_GROUPS.flatMap((g) => g.items.map((i) => [i.code, i.label] as const)));
const KINDS = new Map(ALLERGEN_GROUPS.flatMap((g) => g.items.map((i) => [i.code, g.kind] as const)));

export function allergenLabel(code: string): string {
  return LABELS.get(code) ?? RETIRED_LABELS[code] ?? code;
}

/** 지금 선택 화면에 있는 항목만 남긴다(예전 항목·모르는 코드 제외). */
export function knownAllergens(codes: string[]): string[] {
  return codes.filter((c) => KINDS.has(c));
}

/**
 * 이 페이지에 보여줄 알레르기 경고만 고른다(프론트 조건).
 * - 식품 페이지(domain='food'): 백엔드가 보낸 알레르기 경고를 보여준다(식품 알레르기 항목만)
 * - 일반 상품 페이지(domain='product'): 알레르기 경고를 띄우지 않는다
 * - 종류를 모르면(null): 띄우지 않는다
 * 같은 항목이 여러 번 오면 하나만 남긴다.
 */
export function warningsForDomain(warnings: AllergyWarning[], domain: Domain | null): AllergyWarning[] {
  if (domain !== 'food') return [];
  const seen = new Set<string>();
  return warnings.filter((w) => {
    if (KINDS.get(w.allergen) !== 'food' || seen.has(w.allergen)) return false;
    seen.add(w.allergen);
    return true;
  });
}

export interface AllergyNotice {
  /** 경고 제목. 한 항목이면 '우유 알레르기 주의', 여러 항목이면 '알레르기 주의 · 3개 항목' */
  title: string;
  /** 해당하는 내 알레르기 이름 */
  names: string[];
  /** 본문 문장들 */
  lines: string[];
}

/** 여러 알레르기 경고를 경고창 하나에 담을 문구로 합친다. 경고가 없으면 null. */
export function allergyNotice(warnings: AllergyWarning[]): AllergyNotice | null {
  if (!warnings.length) return null;
  const label = (ws: AllergyWarning[]) => ws.map((w) => allergenLabel(w.allergen));
  const names = label(warnings);
  const found = label(warnings.filter((w) => w.evidence === 'contains'));
  const maybe = label(warnings.filter((w) => w.evidence === 'may_contain'));
  const unread = label(warnings.filter((w) => w.evidence === 'unknown'));
  const lines: string[] = [];
  if (found.length) lines.push(`상품 표시에서 ${found.join(', ')} 성분을 확인했어요.`);
  if (maybe.length) lines.push(`${maybe.join(', ')} 성분이 들어 있을 수 있어요.`);
  if (unread.length) {
    lines.push(
      found.length || maybe.length
        ? `${unread.join(', ')} 성분은 성분표에서 인식하지 못했어요.`
        : '알레르기 성분표를 인식하지 못했어요. 안전하다는 뜻은 아니에요.',
    );
  }
  return {
    title: names.length === 1 ? `${names[0]} 알레르기 주의` : `알레르기 주의 · ${names.length}개 항목`,
    names,
    lines,
  };
}
