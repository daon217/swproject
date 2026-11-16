import { router } from 'expo-router';
import { Text, View } from 'react-native';
import { Button, Desc, H1, Note, Page, SubHeader } from '../ui/components';
import { C } from '../ui/theme';

// 결제 완료 (Figma U31)
export default function PaymentDoneScreen() {
  const back = () => router.dismissTo('/');
  return (
    <View style={{ flex: 1 }}>
      <SubHeader title="결제 완료" onBack={back} />
      <Page footer={<Button label="돌아가기" onPress={back} />}>
        <Text style={{ color: C.success, fontSize: 48, fontWeight: '900', marginTop: 16 }} accessibilityElementsHidden>
          ✓
        </Text>
        <H1 style={{ fontSize: 30, lineHeight: 40 }}>{'프리미엄 구독이\n완료되었어요!'}</H1>
        <Desc>이제 추천 상품 3개와 식품 재료 필터를 이용할 수 있어요.</Desc>
        <Note>프리미엄 혜택이 지금부터 적용돼요.</Note>
      </Page>
    </View>
  );
}
