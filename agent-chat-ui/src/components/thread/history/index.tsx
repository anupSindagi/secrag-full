import { Button } from "@/components/ui/button";
import { useThreads } from "@/providers/Thread";
import { Thread } from "@langchain/langgraph-sdk";
import { useEffect } from "react";

import { getContentString } from "../utils";
import { useQueryState, parseAsBoolean } from "nuqs";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { PanelRightOpen, PanelRightClose } from "lucide-react";
import { useMediaQuery } from "@/hooks/useMediaQuery";

function getThreadPreviewText(thread: Thread): string {
  // Debug: log thread structure to understand what data we have
  if (process.env.NODE_ENV === "development") {
    console.log("[getThreadPreviewText] Thread data:", {
      thread_id: thread.thread_id,
      hasValues: !!thread.values,
      valuesType: typeof thread.values,
      hasMessages: thread.values && typeof thread.values === "object" && "messages" in thread.values,
      messagesLength: thread.values && typeof thread.values === "object" && "messages" in thread.values 
        ? (thread.values.messages as any[])?.length 
        : 0,
      metadata: thread.metadata,
    });
  }

  // Try to get the first human message from thread values
  if (
    typeof thread.values === "object" &&
    thread.values &&
    "messages" in thread.values &&
    Array.isArray(thread.values.messages) &&
    thread.values.messages.length > 0
  ) {
    // Find the first human message (user's first message)
    const firstHumanMessage = thread.values.messages.find(
      (m) => m.type === "human"
    );
    
    if (firstHumanMessage) {
      const text = getContentString(firstHumanMessage.content);
      // Truncate to 50 characters for display
      if (text && text.trim().length > 0) {
        const trimmed = text.trim();
        if (trimmed.length > 50) {
          return trimmed.substring(0, 50) + "...";
        }
        return trimmed;
      }
    }
    
    // If no human message, try the first message of any type
    const firstMessage = thread.values.messages[0];
    if (firstMessage) {
      const text = getContentString(firstMessage.content);
      if (text && text.trim().length > 0) {
        const trimmed = text.trim();
        if (trimmed.length > 50) {
          return trimmed.substring(0, 50) + "...";
        }
        return trimmed;
      }
    }
  }
  
  // Check if thread has metadata with a preview
  if (thread.metadata && typeof thread.metadata === "object") {
    const metadata = thread.metadata as Record<string, any>;
    if (metadata.thread_name && typeof metadata.thread_name === "string" && metadata.thread_name.trim().length > 0) {
      const name = metadata.thread_name.trim();
      return name.length > 50 ? name.substring(0, 50) + "..." : name;
    }
  }
  
  // Fallback: use a shortened thread ID with better formatting
  const shortId = thread.thread_id.split("-")[0]; // Just the first part of UUID
  return `Thread ${shortId}...`;
}

function ThreadList({
  threads,
  onThreadClick,
}: {
  threads: Thread[];
  onThreadClick?: (threadId: string) => void;
}) {
  const [threadId, setThreadId] = useQueryState("threadId");

  return (
    <div className="flex h-full w-full flex-col items-start justify-start gap-2 overflow-y-scroll [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-gray-300 [&::-webkit-scrollbar-track]:bg-transparent">
      {threads.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-full text-center px-4">
          <p className="text-sm text-gray-500 mb-2">No threads yet</p>
          <p className="text-xs text-gray-400">Start a conversation to create your first thread</p>
        </div>
      ) : (
        threads.map((t) => {
          const previewText = getThreadPreviewText(t);
          const isActive = t.thread_id === threadId;
          
          return (
            <div
              key={t.thread_id}
              className="w-full px-1"
            >
              <Button
                variant={isActive ? "secondary" : "ghost"}
                className={`w-[280px] items-start justify-start text-left font-normal ${
                  isActive ? "bg-gray-100" : ""
                }`}
                onClick={(e) => {
                  e.preventDefault();
                  onThreadClick?.(t.thread_id);
                  if (t.thread_id === threadId) return;
                  setThreadId(t.thread_id);
                }}
              >
                <p className="truncate text-ellipsis">{previewText}</p>
              </Button>
            </div>
          );
        })
      )}
    </div>
  );
}

function ThreadHistoryLoading() {
  return (
    <div className="flex h-full w-full flex-col items-start justify-start gap-2 overflow-y-scroll [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-gray-300 [&::-webkit-scrollbar-track]:bg-transparent">
      {Array.from({ length: 30 }).map((_, i) => (
        <Skeleton
          key={`skeleton-${i}`}
          className="h-10 w-[280px]"
        />
      ))}
    </div>
  );
}

export default function ThreadHistory() {
  const isLargeScreen = useMediaQuery("(min-width: 1024px)");
  const [chatHistoryOpen, setChatHistoryOpen] = useQueryState(
    "chatHistoryOpen",
    parseAsBoolean.withDefault(false),
  );

  const { getThreads, threads, setThreads, threadsLoading, setThreadsLoading } =
    useThreads();

  useEffect(() => {
    if (typeof window === "undefined") return;
    console.log("[ThreadHistory] Loading threads...");
    setThreadsLoading(true);
    getThreads()
      .then((threads) => {
        console.log("[ThreadHistory] Loaded threads:", threads.length);
        setThreads(threads);
      })
      .catch((error) => {
        console.error("[ThreadHistory] Error loading threads:", error);
      })
      .finally(() => {
        setThreadsLoading(false);
      });
  }, [getThreads]);

  return (
    <>
      <div className="shadow-inner-right hidden h-screen w-[300px] shrink-0 flex-col items-start justify-start gap-6 border-r-[1px] border-slate-300 lg:flex">
        <div className="flex w-full items-center justify-between px-4 pt-1.5">
          <Button
            className="hover:bg-gray-100"
            variant="ghost"
            onClick={() => setChatHistoryOpen((p) => !p)}
          >
            {chatHistoryOpen ? (
              <PanelRightOpen className="size-5" />
            ) : (
              <PanelRightClose className="size-5" />
            )}
          </Button>
          <h1 className="text-xl font-semibold tracking-tight">
            Thread History
          </h1>
        </div>
        {threadsLoading ? (
          <ThreadHistoryLoading />
        ) : (
          <ThreadList threads={threads} />
        )}
      </div>
      <div className="lg:hidden">
        <Sheet
          open={!!chatHistoryOpen && !isLargeScreen}
          onOpenChange={(open) => {
            if (isLargeScreen) return;
            setChatHistoryOpen(open);
          }}
        >
          <SheetContent
            side="left"
            className="flex lg:hidden"
          >
            <SheetHeader>
              <SheetTitle>Thread History</SheetTitle>
            </SheetHeader>
            <ThreadList
              threads={threads}
              onThreadClick={() => setChatHistoryOpen((o) => !o)}
            />
          </SheetContent>
        </Sheet>
      </div>
    </>
  );
}
