import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Animated, Easing, Modal, PanResponder, Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { allergyNotice, warningsForDomain } from '../shared/allergens';
import { formatPrice } from '../shared/format';
import type { PageAnalysis } from '../usePageAnalysis';
import { IconClose, IconWarning } from './icons';
import { ResultView } from './ResultView';
import { C } from './theme';
import { useSession } from '../session';
import { BasicRecommendations } from './BasicRecommendations';

// 플로팅 결과(Figma U16~U25): 축소 카드 → 누르면 하단 시트가 아래에서 올라온다(명세 REQ-UI-009~011).
// 시트는 배경 터치·닫기 버튼·뒤로가기, 또는 상단을 아래로 끌어서 내린다.
// 분석 중·실패·추천 없음도 작은 카드로 알려 준다(아무 표시 없이 사라지면 원인을 알 수 없어서).
// 끌기: 손가락을 따라 움직이고, 빠르게 내리거나 절반 넘게 내리면 닫힘, 그 외에는 제자리로 돌아온다. 축소 카드는 상품 페이지에 있는 동안 계속 보인다.

const native = Platform.OS !== 'web';
/** 이 속도(px/ms)보다 빠르게 내리면 닫는다 */
const FLING_VELOCITY = 0.8;
/** 시트 높이의 이 비율보다 많이 내리면 천천히 놓아도 닫는다 */
const CLOSE_RATIO = 0.5;
/** 이만큼(px) 넘게 움직여야 카드 끌기로 본다. 그보다 짧으면 누르기 */
const DRAG_SLOP = 6;
/** 축소 카드 기본 위치(부모 기준). st.compactWrap과 같은 값 */
const CARD_TOP = 96;
const CARD_RIGHT = 12;
const EDGE = 8;

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
  const { me } = useSession();
  const [open, setOpen] = useState(false);
  /** 시트가 원래 위치에서 아래로 내려간 거리(px). 0이면 완전히 열림 */
  const [offset] = useState(() => new Animated.Value(SHEET_FALLBACK));
  const sheetH = useRef(SHEET_FALLBACK);
  const [openedSession, setOpenedSession] = useState(page.pageSessionId);
  if (openedSession !== page.pageSessionId) {
    setOpenedSession(page.pageSessionId);
    setOpen(false);
  }

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
  useEffect(() => { closeRef.current = close; });

  // PanResponder registers handlers here; refs are read only later, during gestures.
  // eslint-disable-next-line react-hooks/refs
  const [drag] = useState(() =>
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
  );

  // 축소 카드 끌기(짧게 누르면 시트가 열리고, 일정 거리 넘게 움직이면 카드를 옮긴다).
  // 위치는 기본 자리(오른쪽 위)에서 옮긴 거리로 두고, 부모 영역 안으로만 움직인다. 페이지가 바뀌어도 유지된다.
  const [cardPos] = useState(() => new Animated.ValueXY({ x: 0, y: 0 }));
  const moved = useRef({ x: 0, y: 0 });
  // 웹(react-native-web)에서는 끌기가 끝난 뒤에도 안쪽 버튼의 누르기가 실행된다. 끌기 직후의 누르기는 무시한다.
  const draggedAt = useRef(0);
  const area = useRef({ w: 0, h: 0 });
  const card = useRef({ w: 206, h: 120 });
  const fitCard = (p: { x: number; y: number }) => {
    const { w, h } = area.current;
    if (!w || !h) return p;
    const baseLeft = w - CARD_RIGHT - card.current.w;
    const minX = EDGE - baseLeft;
    const maxX = Math.max(minX, w - card.current.w - EDGE - baseLeft);
    const minY = EDGE - CARD_TOP;
    const maxY = Math.max(minY, h - card.current.h - EDGE - CARD_TOP);
    return { x: Math.min(Math.max(minX, p.x), maxX), y: Math.min(Math.max(minY, p.y), maxY) };
  };
  const fitRef = useRef(fitCard);
  useEffect(() => {
    fitRef.current = fitCard;
  });
  const refit = () => {
    moved.current = fitRef.current(moved.current);
    cardPos.setValue(moved.current);
  };
  // PanResponder registers handlers here; refs are read only later, during gestures.
  // eslint-disable-next-line react-hooks/refs
  const [cardDrag] = useState(() =>
    PanResponder.create({
      // 누르기는 안쪽 버튼(Pressable)이 받는다. 일정 거리 넘게 움직이면 끌기로 가져온다.
      onStartShouldSetPanResponder: () => false,
      onMoveShouldSetPanResponderCapture: (_, g) => Math.abs(g.dx) > DRAG_SLOP || Math.abs(g.dy) > DRAG_SLOP,
      onMoveShouldSetPanResponder: (_, g) => Math.abs(g.dx) > DRAG_SLOP || Math.abs(g.dy) > DRAG_SLOP,
      onPanResponderTerminationRequest: () => false,
      onPanResponderGrant: () => {
        draggedAt.current = Date.now();
      },
      onPanResponderMove: (_, g) => {
        // 웹은 버튼 누르기(pointerup)가 끌기 끝(mouseup)보다 먼저 오므로 움직이는 동안 시각을 남긴다.
        draggedAt.current = Date.now();
        cardPos.setValue(fitRef.current({ x: moved.current.x + g.dx, y: moved.current.y + g.dy }));
      },
      onPanResponderRelease: (_, g) => {
        moved.current = fitRef.current({ x: moved.current.x + g.dx, y: moved.current.y + g.dy });
        cardPos.setValue(moved.current);
        draggedAt.current = Date.now();
      },
      onPanResponderTerminate: () => {
        cardPos.setValue(moved.current);
        draggedAt.current = Date.now();
      },
    }),
  );
  const openSheet = () => {
    if (Date.now() - draggedAt.current < 400) return;
    setOpen(true);
  };

  const a = page.status === 'done' ? page.analysis : null;
  // 추천이 비어도(empty) 알레르기 경고는 카드로 보여준다.
  const rec = a?.result_kind === 'recommendation' || a?.result_kind === 'empty' ? a : null;
  // 식품 페이지에서만 알레르기 경고를 보여준다(상품 페이지는 띄우지 않음). 여러 항목이면 카드 하나에 모은다.
  const shown = rec ? warningsForDomain(rec.warnings, rec.selected_domain) : [];
  const allergy = allergyNotice(shown);
  const hasItems = !!rec?.sections.some((x) => x.kind !== 'used' && x.items.length > 0);
  // 큰 경고 카드는 알레르기를 확인했을 때나 추천이 없을 때만 먼저 보여준다. '성분표 인식 못 함'뿐이면 추천 카드 + 작은 안내.
  const notice = allergy && (shown.some((w) => w.evidence !== 'unknown') || !hasItems) ? allergy : null;
  const warning = !!notice;
  // [임시] 페이지에서 읽은 실제 상품명·가격이 있으면 그것을 보여준다(서버 OCR 연동 전).
  const first = rec && hasItems ? (rec.page_product ?? rec.sections.find((x) => x.kind !== 'used' && x.items.length > 0)?.items[0]) : undefined;
  const kind: 'launcher' | 'analyzing' | 'error' | 'empty' | 'result' =
    page.status === 'none' ? 'launcher' : page.status === 'analyzing' ? 'analyzing' : page.status === 'error' ? 'error' : warning || first ? 'result' : 'empty';

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
      {!open && (
      <View
        style={StyleSheet.absoluteFill}
        pointerEvents="box-none"
        onLayout={(e) => {
          area.current = { w: e.nativeEvent.layout.width, h: e.nativeEvent.layout.height };
          refit();
        }}
      >
      <Animated.View
        style={[st.compactWrap, { transform: cardPos.getTranslateTransform() }]}
        onLayout={(e) => {
          card.current = { w: e.nativeEvent.layout.width, h: e.nativeEvent.layout.height };
          refit();
        }}
        accessibilityHint="끌어서 옮길 수 있어요"
        {...cardDrag.panHandlers}
      >
        {kind === 'launcher' && <Pressable style={st.compact} onPress={openSheet} accessibilityRole="button" accessibilityLabel="꿀픽 추천 열기"><Text style={st.label}>꿀픽</Text><Text style={st.hint}>추천 상품 보기</Text></Pressable>}
        {kind === 'analyzing' && (
          <Pressable style={st.compact} onPress={openSheet} accessibilityRole="button" accessibilityLabel="꿀픽이 이 상품을 분석하고 있어요">
            <View style={st.stateRow}>
              <ActivityIndicator size="small" color={C.primary} />
              <Text style={[st.label, { marginBottom: 0 }]}>꿀픽 분석 중</Text>
            </View>
            <Text style={st.hint}>비슷한 상품과 가격을 찾고 있어요</Text>
          </Pressable>
        )}
        {kind === 'error' && (
          <Pressable style={st.compact} onPress={openSheet} accessibilityRole="button" accessibilityLabel="분석하지 못했어요. 추천 창에서 다시 시도">
            <Text style={[st.label, { color: C.danger }]}>분석하지 못했어요</Text>
            <Text style={st.stateBody} numberOfLines={2}>
              {page.error ?? '잠시 후 다시 시도해 주세요.'}
            </Text>
            <Text style={[st.hint, { color: C.primary }]}>추천 창에서 다시 시도</Text>
          </Pressable>
        )}
        {kind === 'empty' && (
          <Pressable style={st.compact} onPress={openSheet} accessibilityRole="button" accessibilityLabel="추천할 상품을 찾지 못했어요">
            <Text style={st.label}>꿀픽 추천</Text>
            <Text style={st.stateBody}>{a?.result_kind === 'ingredient_unknown' ? '성분 정보를 확인하지 못했어요' : a?.selected_domain ? '비슷한 상품을 찾지 못했어요' : '추천할 상품을 찾지 못했어요'}</Text>
          </Pressable>
        )}
        {kind === 'result' && (
        <Pressable
          style={[st.compact, warning && st.compactAlert]}
          onPress={openSheet}
          accessibilityRole="button"
          accessibilityLabel={notice ? `${notice.title}. 눌러서 ${hasItems ? '대체 상품' : '자세히'} 보기` : '꿀픽 추천. 눌러서 추천 더 보기'}
        >
          {notice ? (
            <>
              <IconWarning size={22} color={C.danger} />
              <Text style={st.alertTitle}>{notice.title}</Text>
              <Text style={st.alertBody}>
                {notice.names.length > 1 ? `${notice.names.join(', ')}\n` : ''}
                {notice.lines[0]}
                {'\n'}구매 전 성분표를 확인해 주세요.
              </Text>
              <Text style={[st.hint, { color: C.primary }]}>{hasItems ? '눌러서 대체 상품 보기' : '눌러서 자세히 보기'}</Text>
            </>
          ) : (
            first && (
              <>
                <Text style={st.label}>꿀픽 추천</Text>
                <Text style={st.name} numberOfLines={1}>
                  {first.name}
                </Text>
                {!!first.price && <Text style={st.price}>{formatPrice(first.price, first.currency)}</Text>}
                <Text style={st.hint}>{allergy ? '알레르기 성분 확인 필요 · 눌러서 보기' : '눌러서 추천 더 보기'}</Text>
              </>
            )
          )}
        </Pressable>
        )}
      </Animated.View>
      </View>
      )}

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
              {!me && page.status === 'none' ? <BasicRecommendations onOpenUrl={openUrl} onLogin={go(onPremium)} /> : <ResultView status={page.status} analysis={page.analysis} error={page.error} onOpenUrl={openUrl} onPremium={go(onPremium)} onFilter={go(onFilter)} onRetry={onRetry} />}
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
  stateRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  stateBody: { fontSize: 13, color: C.text, lineHeight: 18 },
  alertTitle: { color: C.danger, fontWeight: '800', fontSize: 14, marginTop: 6 },
  alertBody: { fontSize: 12, color: C.text, marginTop: 4, lineHeight: 17 },
  dim: { flex: 1, backgroundColor: C.dim, justifyContent: 'flex-end' },
  sheetWrap: { height: '82%' },
  sheet: { flex: 1, backgroundColor: C.surface, borderTopLeftRadius: 20, borderTopRightRadius: 20, overflow: 'hidden' },
  dragZone: { height: 40, paddingTop: 10 },
  handle: { width: 40, height: 4, borderRadius: 2, backgroundColor: '#D5DAE3', alignSelf: 'center' },
  sheetClose: { position: 'absolute', top: 18, right: 16, zIndex: 2 },
});
