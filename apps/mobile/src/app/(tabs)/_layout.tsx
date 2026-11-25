import { Tabs } from 'expo-router';
import { IconClock, IconGear, IconGlobe } from '../../ui/icons';
import { C } from '../../ui/theme';

// 하단 탭: 최근 · 브라우저 · 설정 (Figma 01). 시작 화면(/)은 Figma U01·U02 '홈 · 최근 추천'(index), 브라우저는 /browser.

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
      <Tabs.Screen name="index" options={{ title: '최근', tabBarIcon: ({ color }) => <IconClock color={color as string} size={24} /> }} />
      <Tabs.Screen name="browser" options={{ title: '브라우저', tabBarIcon: ({ color }) => <IconGlobe color={color as string} size={24} /> }} />
      <Tabs.Screen name="settings" options={{ title: '설정', tabBarIcon: ({ color }) => <IconGear color={color as string} size={24} /> }} />
    </Tabs>
  );
}
