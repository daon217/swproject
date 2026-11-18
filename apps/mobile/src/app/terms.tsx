import { router } from 'expo-router';
import { Text, View } from 'react-native';
import { agreeConsent } from '../consent';
import { CONSENT_VERSION, PRIVACY_CONSENT_SECTIONS, PRIVACY_CONSENT_TITLE } from '../shared/terms';
import { Button, Desc, Page, SubHeader } from '../ui/components';
import { C } from '../ui/theme';

// 개인정보 수집 및 이용 동의 원문 (가입 화면의 '원문보기 >')
export default function TermsScreen() {
  return (
    <View style={{ flex: 1 }}>
      <SubHeader title={PRIVACY_CONSENT_TITLE} />
      <Page
        footer={
          <Button
            label="동의하기"
            onPress={() => {
              agreeConsent();
              router.back();
            }}
          />
        }
      >
        {PRIVACY_CONSENT_SECTIONS.map((sec) => (
          <View key={sec.heading} style={{ marginBottom: 16 }}>
            <Text style={{ fontWeight: '800', fontSize: 14, color: C.text, marginBottom: 6 }}>{sec.heading}</Text>
            <Text style={{ fontSize: 13, color: '#3B4558', lineHeight: 20 }}>{sec.body}</Text>
          </View>
        ))}
        <Desc>문서 버전 {CONSENT_VERSION}</Desc>
      </Page>
    </View>
  );
}
