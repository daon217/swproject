import { useEffect, useRef, useState } from 'react';
import { Animated, Easing, Modal, PanResponder, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { allergenLabel } from '../shared/allergens';
import { formatPrice } from '../shared/format';
import type { PageAnalysis } from '../usePageAnalysis';
import { IconClose, IconWarning } from './icons';
import { ResultView } from './ResultView';
import { C } from './theme';

// 플로팅 결과(Figma U16~U25): 축소 카드 → 누르면 하단 시트가 아래에서 올라온다(명세 REQ-UI-009~011).
// 시트는 배경 터치·닫기 버튼·뒤로가기, 또는 상단을 아래로 끌어서 내린다.
// 끌기: 손가락을 따라 움직이고, 빠르게 내리거나 절반 넘게 내리면 닫힘, 그 외에는 제자리로 돌아온다. 축소 카드는 상품 페이지에 있는 동안 계속 보인다.

const native = Platform.OS !== 'web';
/** 이 속도(px/ms)보다 빠르게 내리면 닫는다 */
const FLING_VELOCITY = 0.8;
/** 시트 높이의 이 비율보다 많이 내리면 천천히 놓아도 닫는다 */
const CLOSE_RATIO = 0.5;

export function Floating({
  page,
  onOpenUrl,
  onPremium,
  onFilter,
  onRetry,
}: {
  page: PageAnalysis;
  onOpenUrl: (url: string) => void;
  onPremium: () => void;
  onFilter: () => void;
  onRetry: () => void;
}) {
  const insets = useSafeAreaInsets();
  const [open, setOpen] = useState(false);
  /** 시트가 원래 위치에서 아래로 내려간 거리(px). 0이면 완전히 열림 */
  const offset = useRef(new Animated.Value(SHEET_FALLBACK)).current;
  const sheetH = useRef(SHEET_FALLBACK);
  useEffect(() => setOpen(false), [page.pageSessionId]);

  useEffect(() => {
    if (!open) return;
    offset.setValue(sheetH.current);
    Animated.timing(offset, { toValue: 0, duration: 260, easing: Easing.out(Easing.cubic), useNativeDriver: native }).start();
  }, [open, offset]);

  const close = (velocity = 0) => {
    // 빠르게 던졌으면 그 속도에 맞춰 더 빨리 내려간다.
    const duration = velocity > 0 ? Math.max(120, Math.min(220, sheetH.current / velocity / 2)) : 200;
    Animated.timing(offset, { toValue: sheetH.current, duration, easing: Easing.out(Easing.quad), useNativeDriver: native }).start(() => setOpen(false));
  };
  const closeRef = useRef(close);
  closeRef.current = close;

  const drag = useRef(
    PanResponder.create({
      // 손잡이 영역은 누르는 순간 바로 잡는다. 늦게 잡으려 하면 바깥 시트(Pressable)가 먼저 터치를 가져가
      // 끌기 이벤트가 이쪽으로 오지 않는다.
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: () => true,
      onPanResponderTerminationRequest: () => false,
      onPanResponderGrant: () => offset.stopAnimation(),
      onPanResponderMove: (_, g) => offset.setValue(Math.max(0, g.dy)),
      onPanResponderRelease: (_, g) => {
        if (g.vy > FLING_VELOCITY || g.dy > sheetH.current * CLOSE_RATIO) closeRef.current(g.vy);
        else Animated.spring(offset, { toValue: 0, bounciness: 4, speed: 14, useNativeDriver: native }).start();
      },
      onPanResponderTerminate: () => Animated.spring(offset, { toValue: 0, bounciness: 4, speed: 14, useNativeDriver: native }).start(),
    }),
  ).current;

  const a = page.status === 'done' ? page.analysis : null;
  if (!a || a.result_kind !== 'recommendation') return null;

  const warning = a.warnings[0];
  // [임시] 페이지에서 읽은 실제 상품명·가격이 있으면 그것을 보여준다(서버 OCR 연동 전).
  const first = a.page_product ?? a.sections.find((x) => x.kind !== 'used')?.items[0];
  if (!warning && !first) return null;

  // 바깥으로 링크를 열 때는 시트를 먼저 내린다.
  const openUrl = (url: string) => {
    setOpen(false);
    onOpenUrl(url);
  };
  const go = (fn: () => void) => () => {
    setOpen(false);
    fn();
  };

  return (
    <>
      <View style={st.compactWrap}>
        <Pressable
          style={[st.compact, warning && st.compactAlert]}
          onPress={() => setOpen(true)}
          accessibilityRole="button"
          accessibilityLabel={warning ? `${allergenLabel(warning.allergen)} 알레르기 주의. 눌러서 대체 상품 보기` : '꿀픽 추천. 눌러서 추천 더 보기'}
        >
          {warning ? (
            <>
              <IconWarning size={22} color={C.danger} />
              <Text style={st.alertTitle}>{allergenLabel(warning.allergen)} 알레르기 주의</Text>
              <Text style={st.alertBody}>{warning.message}{'\n'}구매 전 성분표를 확인해 주세요.</Text>
              <Text style={[st.hint, { color: C.primary }]}>눌러서 대체 상품 보기</Text>
            </>
          ) : (
            first && (
              <>
                <Text style={st.label}>꿀픽 추천</Text>
                <Text style={st.name} numberOfLines={1}>
                  {first.name}
                </Text>
                {!!first.price && <Text style={st.price}>{formatPrice(first.price, first.currency)}</Text>}
                <Text style={st.hint}>눌러서 추천 더 보기</Text>
              </>
            )
          )}
        </Pressable>
      </View>

      <Modal visible={open} transparent animationType="fade" onRequestClose={() => close()} statusBarTranslucent navigationBarTranslucent>
        {/* 배경과 시트를 형제로 둔다. 시트를 터치 영역(Pressable) 안에 넣으면 그 영역이 터치를 먼저 가져가
            시트 안 목록 스크롤과 손잡이 끌기가 막힌다. */}
        <View style={st.dim}>
          <Pressable style={StyleSheet.absoluteFill} onPress={() => close()} accessibilityLabel="추천 닫기" />
          <Animated.View
            style={[st.sheetWrap, { transform: [{ translateY: offset }] }]}
            onLayout={(e) => (sheetH.current = e.nativeEvent.layout.height || SHEET_FALLBACK)}
          >
            <View style={[st.sheet, { paddingBottom: insets.bottom }]} accessibilityViewIsModal>
              {/* 끌기 영역: 손잡이가 있는 시트 상단 */}
              <View style={st.dragZone} {...drag.panHandlers} accessibilityHint="아래로 끌어서 닫기">
                <View style={st.handle} />
              </View>
              <Pressable style={st.sheetClose} onPress={() => close()} accessibilityLabel="닫기" hitSlop={10}>
                <IconClose size={22} color={C.sub} />
              </Pressable>
              <ResultView status={page.status} analysis={a} error={page.error} onOpenUrl={openUrl} onPremium={go(onPremium)} onFilter={go(onFilter)} onRetry={onRetry} />
            </View>
          </Animated.View>
        </View>
      </Modal>
    </>
  );
}

const SHEET_FALLBACK = 700;

const shadow = { shadowColor: '#1A2233', shadowOpacity: 0.16, shadowRadius: 16, shadowOffset: { width: 0, height: 6 }, elevation: 8 };

const st = StyleSheet.create({
  compactWrap: { position: 'absolute', top: 96, right: 12 },
  compact: { width: 206, padding: 14, borderRadius: 14, backgroundColor: C.surface, borderWidth: 1, borderColor: C.border, ...shadow },
  compactAlert: { width: 238, backgroundColor: C.primarySoft, borderColor: '#D7DEEF' },
  label: { color: C.primary, fontWeight: '800', fontSize: 13, marginBottom: 8 },
  name: { fontWeight: '800', fontSize: 15, color: C.text },
  price: { color: C.price, fontWeight: '800', fontSize: 18, marginTop: 4 },
  hint: { fontSize: 12, color: C.sub, marginTop: 8 },
  alertTitle: { color: C.danger, fontWeight: '800', fontSize: 14, marginTop: 6 },
  alertBody: { fontSize: 12, color: C.text, marginTop: 4, lineHeight: 17 },
  dim: { flex: 1, backgroundColor: C.dim, justifyContent: 'flex-end' },
  sheetWrap: { height: '82%' },
  sheet: { flex: 1, backgroundColor: C.surface, borderTopLeftRadius: 20, borderTopRightRadius: 20, overflow: 'hidden' },
  dragZone: { height: 40, paddingTop: 10 },
  handle: { width: 40, height: 4, borderRadius: 2, backgroundColor: '#D5DAE3', alignSelf: 'center' },
  sheetClose: { position: 'absolute', top: 18, right: 16, zIndex: 2 },
});
