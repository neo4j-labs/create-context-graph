import { test, expect } from "@playwright/test";

const BASE_URL = process.env.FRONTEND_URL || "http://localhost:3000";
const API_URL = process.env.API_URL || "http://localhost:8000";

// Timeout for LLM responses — these can be slow
const CHAT_TIMEOUT = 120_000;

test.describe("Discovered Database Context Graph", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(BASE_URL);
  });

  // --------------------------------------------------------------------------
  // Basic page load
  // --------------------------------------------------------------------------

  test("page loads with header and chat panel", async ({ page }) => {
    // Header with domain name
    await expect(page.getByRole("heading", { name: /Discovered Database/i })).toBeVisible();

    // Chat heading
    await expect(page.getByRole("heading", { name: /chat/i })).toBeVisible();

    // Chat input
    await expect(page.getByPlaceholder(/ask about/i)).toBeVisible();
  });

  test("demo scenario badges are visible", async ({ page }) => {
    // Should show demo scenario section
    await expect(page.getByText(/try a demo scenario/i)).toBeVisible();

    // Should have clickable badges
    const badges = page.locator("[role='group'] span[data-scope='badge'], .chakra-badge").filter({ hasText: /.{10,}/ });
    const count = await badges.count();
    expect(count).toBeGreaterThan(0);
  });

  // --------------------------------------------------------------------------
  // Backend health
  // --------------------------------------------------------------------------

  test("backend health check returns ok or degraded", async ({ request }) => {
    const res = await request.get(`${API_URL}/health`);
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(["ok", "degraded"]).toContain(body.status);
    expect(body.domain).toBe("discovered-database");
  });

  test("connection status indicator visible", async ({ page }) => {
    // The header contains a colored status dot
    const dot = page.locator("[title*='Backend']");
    await expect(dot).toBeVisible({ timeout: 10_000 });
  });

  // --------------------------------------------------------------------------
  // Schema visualization
  // --------------------------------------------------------------------------

  test("graph loads schema view on startup", async ({ page }) => {
    // The graph panel shows "Schema view" text
    await expect(page.getByText(/schema view/i)).toBeVisible({ timeout: 15_000 });

    // Legend badges should be visible
    const legend = page.locator("[class*='badge']").filter({ hasText: /^[A-Z]/ });
    await expect(legend.first()).toBeVisible({ timeout: 10_000 });
  });

  // --------------------------------------------------------------------------
  // Chat interaction with demo prompts
  // --------------------------------------------------------------------------

  test("demo prompt: Explore discovered graph — sends and gets response", async ({ page }) => {
    test.setTimeout(CHAT_TIMEOUT);

    // Type the prompt
    const input = page.getByPlaceholder(/ask about/i);
    await input.fill("Show me a few Appearance records and summarize the key properties.");
    await page.getByRole("button", { name: /send/i }).click();

    // Should show user message
    await expect(page.getByText("Show me a few Appearance records and summarize the key properties.").first()).toBeVisible();

    // Should show loading state (thinking or tool calls)
    await expect(
      page.getByText(/thinking|running|generating/i).first()
    ).toBeVisible({ timeout: 10_000 });

    // Wait for assistant response (not an error)
    const assistantResponse = page.locator(".markdown-content").last();
    await expect(assistantResponse).toBeVisible({ timeout: CHAT_TIMEOUT });

    // Response should have meaningful content (not empty, not just an error)
    const text = await assistantResponse.textContent();
    expect(text).toBeTruthy();
    expect(text!.length).toBeGreaterThan(20);

    // Should NOT be an error message
    expect(text!.toLowerCase()).not.toContain("cannot reach the backend");
  });

  // --------------------------------------------------------------------------
  // Demo badge click flow
  // --------------------------------------------------------------------------

  test("clicking a demo badge sends the prompt", async ({ page }) => {
    test.setTimeout(CHAT_TIMEOUT);

    // Find and click the first demo badge
    const badge = page.locator(".chakra-badge[title]").first();
    const promptText = await badge.getAttribute("title");
    expect(promptText).toBeTruthy();

    await badge.click();

    // Should show user message with the badge prompt
    await expect(page.getByText(promptText!).first()).toBeVisible({ timeout: 5_000 });

    // Should eventually get an assistant response
    const assistantResponse = page.locator(".markdown-content").last();
    await expect(assistantResponse).toBeVisible({ timeout: CHAT_TIMEOUT });
  });

  // --------------------------------------------------------------------------
  // Tool call visualization
  // --------------------------------------------------------------------------

  test("tool calls show timeline with status indicators", async ({ page }) => {
    test.setTimeout(CHAT_TIMEOUT);

    // Send a prompt that should trigger tool calls
    const input = page.getByPlaceholder(/ask about/i);
    await input.fill("Show me a few Appearance records and summarize the key properties.");
    await page.getByRole("button", { name: /send/i }).click();

    // Wait for at least one tool call badge to appear
    const toolBadge = page.locator("[data-scope='badge']").filter({ hasText: /execute_cypher|get_schema|search/ });
    await expect(toolBadge.first()).toBeVisible({ timeout: 30_000 });
  });

  // --------------------------------------------------------------------------
  // Graph updates from chat
  // --------------------------------------------------------------------------

  test("graph visualization updates after agent query", async ({ page }) => {
    test.setTimeout(CHAT_TIMEOUT);

    // The graph starts in schema view
    await expect(page.getByText(/schema view/i)).toBeVisible({ timeout: 15_000 });

    // Send a query that should return graph data
    const input = page.getByPlaceholder(/ask about/i);
    await input.fill("Show me a few Appearance records and summarize the key properties.");
    await page.getByRole("button", { name: /send/i }).click();

    // Wait for the graph to switch from schema to data view
    // (the text changes from "Schema view" to entity relationships)
    await expect(page.getByText(/entity relationships/i)).toBeVisible({ timeout: CHAT_TIMEOUT });
  });

  // --------------------------------------------------------------------------
  // New conversation
  // --------------------------------------------------------------------------

  test("new conversation button resets chat", async ({ page }) => {
    test.setTimeout(CHAT_TIMEOUT);

    // Send a message first
    const input = page.getByPlaceholder(/ask about/i);
    await input.fill("Hello");
    await page.getByRole("button", { name: /send/i }).click();

    // Wait for response
    await expect(page.locator(".markdown-content").last()).toBeVisible({ timeout: CHAT_TIMEOUT });

    // Click "New" button
    await page.getByRole("button", { name: /new/i }).click();

    // Demo scenarios should be visible again
    await expect(page.getByText(/try a demo scenario/i)).toBeVisible();
  });

  // --------------------------------------------------------------------------
  // Mobile navigation (viewport 375px)
  // --------------------------------------------------------------------------

  test("mobile: bottom tab bar switches panels", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto(BASE_URL);

    // Chat should be visible by default
    await expect(page.getByPlaceholder(/ask about/i)).toBeVisible();

    // Bottom tab bar should be visible
    const graphTab = page.getByRole("button", { name: /graph panel/i });
    await expect(graphTab).toBeVisible();

    // Click graph tab
    await graphTab.click();

    // Graph content should now be visible
    await expect(page.getByText(/schema view|knowledge graph/i).first()).toBeVisible({ timeout: 10_000 });

    // Click details tab
    const detailsTab = page.getByRole("button", { name: /details panel/i });
    await detailsTab.click();

    // Traces/Documents tabs should be visible
    await expect(page.getByText(/traces/i).first()).toBeVisible();
  });

  // --------------------------------------------------------------------------
  // API-level prompt quality checks
  // --------------------------------------------------------------------------

  test("API: Explore discovered graph prompt 1 returns quality response", async ({ request }) => {
    test.setTimeout(CHAT_TIMEOUT);

    const res = await request.post(`${API_URL}/api/chat`, {
      data: { message: "Show me a few Appearance records and summarize the key properties." },
    });
    expect(res.ok()).toBeTruthy();

    const body = await res.json();

    // Should have a response string
    expect(body.response).toBeTruthy();
    expect(typeof body.response).toBe("string");
    expect(body.response.length).toBeGreaterThan(50);

    // Should have a session_id
    expect(body.session_id).toBeTruthy();

    // Response should not be a generic error
    expect(body.response.toLowerCase()).not.toContain("i apologize");
    expect(body.response.toLowerCase()).not.toContain("i don't have access");
  });

  test("API: Explore discovered graph prompt 2 returns quality response", async ({ request }) => {
    test.setTimeout(CHAT_TIMEOUT);

    const res = await request.post(`${API_URL}/api/chat`, {
      data: { message: "What relationships connect Appearance to other labels in this graph?" },
    });
    expect(res.ok()).toBeTruthy();

    const body = await res.json();

    // Should have a response string
    expect(body.response).toBeTruthy();
    expect(typeof body.response).toBe("string");
    expect(body.response.length).toBeGreaterThan(50);

    // Should have a session_id
    expect(body.session_id).toBeTruthy();

    // Response should not be a generic error
    expect(body.response.toLowerCase()).not.toContain("i apologize");
    expect(body.response.toLowerCase()).not.toContain("i don't have access");
  });

  test("API: Explore discovered graph prompt 3 returns quality response", async ({ request }) => {
    test.setTimeout(CHAT_TIMEOUT);

    const res = await request.post(`${API_URL}/api/chat`, {
      data: { message: "Compare Appearance with Attack using available relationships." },
    });
    expect(res.ok()).toBeTruthy();

    const body = await res.json();

    // Should have a response string
    expect(body.response).toBeTruthy();
    expect(typeof body.response).toBe("string");
    expect(body.response.length).toBeGreaterThan(50);

    // Should have a session_id
    expect(body.session_id).toBeTruthy();

    // Response should not be a generic error
    expect(body.response.toLowerCase()).not.toContain("i apologize");
    expect(body.response.toLowerCase()).not.toContain("i don't have access");
  });

  test("API: Explore discovered graph prompt 4 returns quality response", async ({ request }) => {
    test.setTimeout(CHAT_TIMEOUT);

    const res = await request.post(`${API_URL}/api/chat`, {
      data: { message: "Find examples that use the AWAY_ROTATION relationship." },
    });
    expect(res.ok()).toBeTruthy();

    const body = await res.json();

    // Should have a response string
    expect(body.response).toBeTruthy();
    expect(typeof body.response).toBe("string");
    expect(body.response.length).toBeGreaterThan(50);

    // Should have a session_id
    expect(body.session_id).toBeTruthy();

    // Response should not be a generic error
    expect(body.response.toLowerCase()).not.toContain("i apologize");
    expect(body.response.toLowerCase()).not.toContain("i don't have access");
  });
});
