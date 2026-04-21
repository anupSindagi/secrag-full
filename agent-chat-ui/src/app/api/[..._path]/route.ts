import { initApiPassthrough } from "langgraph-nextjs-api-passthrough";
import { NextRequest } from "next/server";

// This file acts as a proxy for requests to your LangGraph server.
// Read the [Going to Production](https://github.com/langchain-ai/agent-chat-ui?tab=readme-ov-file#going-to-production) section for more information.

// Get the backend API URL from environment variable, defaulting to localhost for development
const DEFAULT_BACKEND_API_URL = process.env.LANGGRAPH_API_URL || process.env.BACKEND_API_URL || "http://localhost:2024";
const BACKEND_API_KEY = process.env.LANGSMITH_API_KEY || process.env.BACKEND_API_KEY || undefined;

// Helper to get backend URL from request (cookie, header, or query param)
function getBackendUrlFromRequest(request: NextRequest): string {
  // Try to get from cookie first (set by frontend when using proxy)
  const cookies = request.cookies;
  const cookieUrl = cookies.get("backend_url")?.value;
  if (cookieUrl) {
    try {
      const decoded = decodeURIComponent(cookieUrl);
      console.log("[Proxy] Using backend URL from cookie:", decoded);
      return decoded;
    } catch (e) {
      console.warn("[Proxy] Failed to decode cookie URL:", e);
    }
  }
  
  // Try to get from custom header
  const headerUrl = request.headers.get("x-backend-url");
  if (headerUrl) {
    console.log("[Proxy] Using backend URL from header:", headerUrl);
    return headerUrl;
  }
  
  // Try to get from query parameter
  const url = new URL(request.url);
  const queryUrl = url.searchParams.get("backend_url");
  if (queryUrl) {
    console.log("[Proxy] Using backend URL from query:", queryUrl);
    return queryUrl;
  }
  
  // Fallback to env var
  console.log("[Proxy] Using default backend URL from env:", DEFAULT_BACKEND_API_URL);
  return DEFAULT_BACKEND_API_URL;
}

// Create passthrough handlers that read backend URL dynamically
function createHandler(
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE"
): (request: NextRequest) => Promise<Response> {
  return async (request: NextRequest): Promise<Response> => {
    const backendUrl = getBackendUrlFromRequest(request);
    const passthrough = initApiPassthrough({
      apiUrl: backendUrl,
      apiKey: BACKEND_API_KEY,
      runtime: "nodejs",
    });
    const handler = passthrough[method];
    if (handler && typeof handler === "function") {
      return handler(request);
    }
    return new Response("Method not implemented", { status: 501 });
  };
}

export const GET = createHandler("GET");
export const POST = createHandler("POST");
export const PUT = createHandler("PUT");
export const PATCH = createHandler("PATCH");
export const DELETE = createHandler("DELETE");

// OPTIONS handler - handle CORS preflight requests
export async function OPTIONS(request: NextRequest) {
  // Return a simple CORS response for preflight requests
  return new Response(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Api-Key, X-Backend-Url",
    },
  });
}

export const runtime = "nodejs";
