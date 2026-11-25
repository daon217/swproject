import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { SessionProvider, useSession } from '../session';

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <SessionProvider>
        <StatusBar style="dark" />
        <AccountScreens />
      </SessionProvider>
    </SafeAreaProvider>
  );
}

function AccountScreens() {
  const { me, loading } = useSession();
  if (loading) return null;
  return (<Stack key={me?.user_id ?? 'guest'} screenOptions={{ headerShown: false, contentStyle: { backgroundColor: '#fff' } }}>
          <Stack.Screen name="(tabs)" />
          <Stack.Screen name="terms" options={{ presentation: 'modal' }} />
        </Stack>);
}
