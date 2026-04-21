/**
 * Determines if we should use the API proxy (Next.js /api route) instead of direct connection.
 * This is needed when:
 * - The page is loaded over HTTPS, but the backend API is HTTP (mixed content issue)
 * - Or when explicitly configured via environment variable
 */
export function getApiUrl(backendUrl: string | undefined): string {
  if (!backendUrl) {
    return "";
  }

  // Always store backend URL in cookie for proxy access (even if not using proxy now)
  // This ensures the proxy knows the backend URL if it's needed later
  if (typeof window !== "undefined") {
    try {
      // Set cookie with backend URL (expires in 1 hour)
      const expires = new Date();
      expires.setHours(expires.getHours() + 1);
      document.cookie = `backend_url=${encodeURIComponent(backendUrl)}; expires=${expires.toUTCString()}; path=/; SameSite=Lax`;
      console.log("[getApiUrl] Set backend_url cookie:", backendUrl);
    } catch (e) {
      console.warn("[getApiUrl] Failed to set cookie:", e);
    }
  }

  // If explicitly configured to use proxy, use it
  const useProxy = process.env.NEXT_PUBLIC_USE_API_PROXY === "true";

  // Check if we're in browser and on HTTPS
  const isHttps =
    typeof window !== "undefined" && window.location.protocol === "https:";

  // Check if backend URL is HTTP
  const isHttpBackend = backendUrl.startsWith("http://");

  // Use proxy if:
  // 1. Explicitly configured to use proxy, OR
  // 2. We're on HTTPS and backend is HTTP (to avoid mixed content)
  if (useProxy || (isHttps && isHttpBackend)) {
    // Use absolute URL for /api path which will proxy to the backend
    // The SDK requires an absolute URL, so we need to prepend the origin
    if (typeof window !== "undefined") {
      console.log("[getApiUrl] Using proxy:", `${window.location.origin}/api`);
      return `${window.location.origin}/api`;
    }
    // Fallback for server-side (shouldn't normally happen, but just in case)
    return "/api";
  }

  // Otherwise, use the backend URL directly
  console.log("[getApiUrl] Using direct connection:", backendUrl);
  return backendUrl;
}

/**
 * Gets the actual backend URL for server-side use (for API passthrough configuration)
 */
export function getBackendUrl(): string {
  return (
    process.env.LANGGRAPH_API_URL ||
    process.env.BACKEND_API_URL ||
    "http://localhost:2024"
  );
}
