import { validate } from "uuid";
import { getApiKey } from "@/lib/api-key";
import { getApiUrl } from "@/lib/api-url";
import { Thread } from "@langchain/langgraph-sdk";
import { useQueryState } from "nuqs";
import {
  createContext,
  useContext,
  ReactNode,
  useCallback,
  useState,
  Dispatch,
  SetStateAction,
} from "react";
import { createClient } from "./client";

interface ThreadContextType {
  getThreads: () => Promise<Thread[]>;
  threads: Thread[];
  setThreads: Dispatch<SetStateAction<Thread[]>>;
  threadsLoading: boolean;
  setThreadsLoading: Dispatch<SetStateAction<boolean>>;
}

const ThreadContext = createContext<ThreadContextType | undefined>(undefined);

function getThreadSearchMetadata(
  assistantId: string,
): { graph_id: string } | { assistant_id: string } {
  if (validate(assistantId)) {
    return { assistant_id: assistantId };
  } else {
    return { graph_id: assistantId };
  }
}

export function ThreadProvider({ children }: { children: ReactNode }) {
  // Get environment variables (same as StreamProvider)
  const envApiUrl: string | undefined = process.env.NEXT_PUBLIC_API_URL;
  const envAssistantId: string | undefined = process.env.NEXT_PUBLIC_ASSISTANT_ID;

  // Use URL params with env var fallbacks (same as StreamProvider)
  const [apiUrl] = useQueryState("apiUrl", {
    defaultValue: envApiUrl || "",
  });
  const [assistantId] = useQueryState("assistantId", {
    defaultValue: envAssistantId || "",
  });

  // Determine final values to use, prioritizing URL params then env vars (same as StreamProvider)
  const finalApiUrl = apiUrl || envApiUrl;
  const finalAssistantId = assistantId || envAssistantId;

  const [threads, setThreads] = useState<Thread[]>([]);
  const [threadsLoading, setThreadsLoading] = useState(false);

  const getThreads = useCallback(async (): Promise<Thread[]> => {
    console.log("[ThreadProvider] getThreads called with:", { 
      apiUrl, 
      assistantId, 
      finalApiUrl, 
      finalAssistantId,
      envApiUrl,
      envAssistantId 
    });
    if (!finalApiUrl || !finalAssistantId) {
      console.log("[ThreadProvider] Missing apiUrl or assistantId");
      return [];
    }
    const apiUrlToUse = getApiUrl(finalApiUrl);
    const apiKey = getApiKey() ?? undefined;
    console.log("[ThreadProvider] Using API URL:", apiUrlToUse, "with key:", !!apiKey);
    
    const client = createClient(apiUrlToUse, apiKey);
    const metadataFilter = getThreadSearchMetadata(finalAssistantId);
    console.log("[ThreadProvider] Searching with metadata:", metadataFilter);

    try {
      const threads = await client.threads.search({
        metadata: metadataFilter,
        limit: 100,
      });
      console.log("[ThreadProvider] Search returned threads:", threads.length, threads);
      return threads;
    } catch (error) {
      console.error("[ThreadProvider] Error searching threads:", error);
      // Try fallback search without metadata
      try {
        console.log("[ThreadProvider] Attempting fallback search without metadata");
        const allThreads = await client.threads.search({
          limit: 100,
        });
        console.log("[ThreadProvider] Fallback search returned:", allThreads.length, "threads");
        return allThreads;
      } catch (fallbackError) {
        console.error("[ThreadProvider] Fallback search also failed:", fallbackError);
        // Return empty array instead of throwing - don't break the app if threads fail
        console.warn("[ThreadProvider] Thread loading failed, returning empty array to prevent app breakage");
        return [];
      }
    }
  }, [apiUrl, assistantId, finalApiUrl, finalAssistantId, envApiUrl, envAssistantId]);

  const value = {
    getThreads,
    threads,
    setThreads,
    threadsLoading,
    setThreadsLoading,
  };

  return (
    <ThreadContext.Provider value={value}>{children}</ThreadContext.Provider>
  );
}

export function useThreads() {
  const context = useContext(ThreadContext);
  if (context === undefined) {
    throw new Error("useThreads must be used within a ThreadProvider");
  }
  return context;
}
