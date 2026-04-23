/**
 * lib/apiClient.ts
 * Instance du client API pour mobile — SecureStore pour refresh token
 */
import * as SecureStore from "expo-secure-store";
import { APIClient } from "@shared/api/client";
import { TOKEN_CONFIG } from "@shared/constants";
import type { TokenPair } from "@shared/types";

let _accessToken: string | null = null;

export const setAccessToken = (token: string | null) => {
  _accessToken = token;
};

export const apiClient = new APIClient({
  baseURL: process.env.EXPO_PUBLIC_API_URL ?? "https://nanovia.ca/api",

  getAccessToken: () => _accessToken,

  getRefreshToken: async () => {
    return SecureStore.getItemAsync(TOKEN_CONFIG.SECURE_STORE_KEY);
  },

  onTokenRefresh: async (tokens: TokenPair) => {
    _accessToken = tokens.access_token;
    await SecureStore.setItemAsync(TOKEN_CONFIG.SECURE_STORE_KEY, tokens.refresh_token);
  },

  onAuthFailure: async () => {
    _accessToken = null;
    await SecureStore.deleteItemAsync(TOKEN_CONFIG.SECURE_STORE_KEY);
    // Navigation handled by auth hook
  },
});
