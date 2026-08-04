import { apiClient, tokenStorage } from "./client";

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export async function login(email: string, password: string): Promise<void> {
  const form = new URLSearchParams();
  form.set("username", email);
  form.set("password", password);

  const response = await apiClient.post<TokenResponse>("/auth/token", form, {
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
  });

  tokenStorage.set(response.data.access_token, response.data.refresh_token);
}

export function logout(): void {
  tokenStorage.clear();
}

export function isAuthenticated(): boolean {
  return Boolean(tokenStorage.getAccess());
}
