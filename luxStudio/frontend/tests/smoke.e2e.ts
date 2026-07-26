import { test, expect } from '@playwright/test';

test.describe('Smoke tests', () => {
  test('login page renders correctly', async ({ page }) => {
    await page.goto('/');

    // The app should redirect to login when unauthenticated
    await page.waitForURL(/\/login/);

    // Check login form elements are present
    await expect(page.locator('input[type="email"]')).toBeVisible();
    await expect(page.locator('input[type="password"]')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toBeVisible();
  });

  test('page has the correct title', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle(/Lux/);
  });

  test('health endpoint responds', async ({ request }) => {
    const response = await request.get('/api/health');
    expect(response.ok()).toBeTruthy();
  });
});
