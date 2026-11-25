// 알레르기 선택 항목. 코드는 공개 성분 코드(ingredients.code)를 가정하며 서버가 유효성을 다시 검사한다.
// 식품은 식품 알레르기 표시 대상(19종) 기준. 그 외 카테고리는 일반 상품(화장품·생활용품·의약외품 등)
// 추천 시 주의 표시용 초안이며, 실제 성분 매칭 범위는 백엔드·추천 담당과 확정한다.
// 이 파일은 apps/extension/src/shared/allergens.ts 와 같은 내용을 유지한다.

export interface AllergenGroup {
  group: string;
  items: { code: string; label: string }[];
}

export const ALLERGEN_GROUPS: AllergenGroup[] = [
  {
    group: '식품',
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
    ],
  },
  {
    group: '호흡기',
    items: [
      { code: 'pollen', label: '꽃가루' },
      { code: 'house_dust_mite', label: '집먼지진드기' },
      { code: 'animal_dander', label: '동물 털·비듬' },
      { code: 'mold', label: '곰팡이' },
      { code: 'cockroach', label: '바퀴벌레' },
    ],
  },
  {
    group: '피부 접촉',
    items: [
      { code: 'nickel', label: '니켈·금속' },
      { code: 'latex', label: '라텍스' },
      { code: 'fragrance', label: '향료' },
      { code: 'preservative', label: '방부제(파라벤 등)' },
      { code: 'hair_dye_ppd', label: '염색약 성분(PPD)' },
      { code: 'lanolin', label: '라놀린' },
    ],
  },
  {
    group: '약물',
    items: [
      { code: 'penicillin', label: '페니실린계 항생제' },
      { code: 'aspirin', label: '아스피린' },
      { code: 'nsaid', label: '소염진통제(NSAIDs)' },
      { code: 'sulfonamide', label: '설파제' },
    ],
  },
  {
    group: '곤충',
    items: [
      { code: 'bee_venom', label: '벌독' },
      { code: 'mosquito', label: '모기' },
    ],
  },
];

const LABELS = new Map(ALLERGEN_GROUPS.flatMap((g) => g.items.map((i) => [i.code, i.label] as const)));

export function allergenLabel(code: string): string {
  return LABELS.get(code) ?? code;
}
