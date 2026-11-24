// Where the app keeps small secrets: the phone's secure store (Keychain / Keystore). The web build
// (a development preview only) keeps them in memory, so nothing sensitive lands in localStorage.

import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

const memory = new Map<string, string>();

export const storage =
  Platform.OS === 'web'
    ? {
        getItemAsync: async (key: string) => memory.get(key) ?? null,
        setItemAsync: async (key: string, value: string) => void memory.set(key, value),
        deleteItemAsync: async (key: string) => void memory.delete(key),
      }
    : {
        getItemAsync: (key: string) => SecureStore.getItemAsync(key),
        setItemAsync: (key: string, value: string) => SecureStore.setItemAsync(key, value),
        deleteItemAsync: (key: string) => SecureStore.deleteItemAsync(key),
      };
