import { Tabs } from 'expo-router';
import { IconClock, IconGear, IconGlobe } from '../../ui/icons';
import { C } from '../../ui/theme';

// 첫 화면은 브라우저(index). 하단 탭: 최근 · 브라우저 · 설정 (Figma 01). 앱 안 브라우저에서 쇼핑하고 분석까지 처리한다.
// 앱을 열면 브라우저 탭(index)부터 보이게 한다(SDK 58은 initialRouteName 대신 anchor).
export const unstable_settings = { anchor: 'index' };

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: C.primary,
        tabBarInactiveTintColor: C.sub,
        tabBarLabelStyle: { fontSize: 12, fontWeight: '600' },
        tabBarStyle: { borderTopColor: C.border },
      }}
    >
      <Tabs.Screen name="recent" options={{ title: '최근', tabBarIcon: ({ color }) => <IconClock color={color as string} size={24} /> }} />
      <Tabs.Screen name="index" options={{ title: '브라우저', tabBarIcon: ({ color }) => <IconGlobe color={color as string} size={24} /> }} />
      <Tabs.Screen name="settings" options={{ title: '설정', tabBarIcon: ({ color }) => <IconGear color={color as string} size={24} /> }} />
    </Tabs>
  );
}
