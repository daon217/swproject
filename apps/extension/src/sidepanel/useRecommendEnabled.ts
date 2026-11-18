import { useEffect, useState } from 'react';
import { isRecommendEnabled, setRecommendEnabled } from '../shared/recommendSetting';
import { KEYS, onItemChange } from '../shared/storage';

/** 상품 추천 켜기/끄기 상태. null이면 아직 불러오는 중 */
export function useRecommendEnabled(): [boolean | null, (on: boolean) => void] {
  const [on, setOn] = useState<boolean | null>(null);
  useEffect(() => {
    const load = () => void isRecommendEnabled().then(setOn);
    load();
    return onItemChange(KEYS.recommendEnabled, load);
  }, []);
  const set = (v: boolean) => {
    setOn(v);
    void setRecommendEnabled(v);
  };
  return [on, set];
}
