import * as Crypto from 'expo-crypto';

export const uuid = (): string => Crypto.randomUUID();

export async function sha256(text: string): Promise<string> {
  return Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, text);
}
