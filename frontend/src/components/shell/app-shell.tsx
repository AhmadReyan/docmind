"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { ConversationOut, Paginated, UserOut } from "@/lib/api-types";
import { api, isApiClientError } from "@/lib/api-client";
import { cn } from "@/lib/cn";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { Spinner } from "@/components/ui/spinner";
import { useToast } from "@/components/ui/toast";

interface AppContextValue {
  user: UserOut;
  conversations: ConversationOut[];
  refreshConversations: () => Promise<void>;
  addConversation: (conversation: ConversationOut) => void;
  updateConversationTitle: (id: string, title: string) => void;
}

const AppContext = createContext<AppContextValue | null>(null);

export function useApp(): AppContextValue {
  const ctx = useContext(AppContext);
  if (!ctx) {
    throw new Error("useApp must be used within AppShell");
  }
  return ctx;
}

export function AppShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { toast } = useToast();

  const [user, setUser] = useState<UserOut | null>(null);
  const [conversations, setConversations] = useState<ConversationOut[]>([]);
  const [pendingDelete, setPendingDelete] = useState<ConversationOut | null>(
    null,
  );
  const [deleting, setDeleting] = useState(false);

  const refreshConversations = useCallback(async () => {
    try {
      const page = await api.get<Paginated<ConversationOut>>(
        "/api/conversations?limit=100&offset=0",
      );
      setConversations(page.items);
    } catch {
      // Non-fatal: the sidebar list just stays as-is.
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const me = await api.get<UserOut>("/api/auth/me");
        if (cancelled) return;
        setUser(me);
        void refreshConversations();
      } catch (e) {
        if (cancelled) return;
        if (isApiClientError(e) && e.status === 401) {
          router.replace("/login");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [router, refreshConversations]);

  const addConversation = useCallback((conversation: ConversationOut) => {
    setConversations((items) => [
      conversation,
      ...items.filter((c) => c.id !== conversation.id),
    ]);
  }, []);

  const updateConversationTitle = useCallback((id: string, title: string) => {
    setConversations((items) => {
      const target = items.find((c) => c.id === id);
      if (!target) return items;
      const updated = { ...target, title };
      // Sending a message bumps updated_at, so float it to the top.
      return [updated, ...items.filter((c) => c.id !== id)];
    });
  }, []);

  const confirmDelete = useCallback(async () => {
    if (!pendingDelete) return;
    setDeleting(true);
    try {
      await api.del(`/api/conversations/${pendingDelete.id}`);
      setConversations((items) =>
        items.filter((c) => c.id !== pendingDelete.id),
      );
      if (pathname === `/chat/${pendingDelete.id}`) {
        router.push("/chat");
      }
      setPendingDelete(null);
    } catch {
      toast("Could not delete the conversation. Please try again.", "error");
    } finally {
      setDeleting(false);
    }
  }, [pendingDelete, pathname, router, toast]);

  const logout = useCallback(async () => {
    try {
      await api.post("/api/auth/logout");
    } catch {
      // Even if the call fails, send the user to the login screen.
    }
    router.replace("/login");
  }, [router]);

  const value = useMemo<AppContextValue | null>(
    () =>
      user
        ? {
            user,
            conversations,
            refreshConversations,
            addConversation,
            updateConversationTitle,
          }
        : null,
    [
      user,
      conversations,
      refreshConversations,
      addConversation,
      updateConversationTitle,
    ],
  );

  if (!value) {
    return (
      <div className="flex min-h-screen items-center justify-center text-zinc-500">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <AppContext.Provider value={value}>
      <div className="flex h-screen overflow-hidden">
        <aside className="flex w-64 shrink-0 flex-col border-r border-zinc-800 bg-zinc-900/40">
          <div className="flex items-center gap-2 px-5 py-5">
            <span
              className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-sm font-bold text-white"
              aria-hidden="true"
            >
              D
            </span>
            <span className="text-lg font-semibold tracking-tight text-zinc-100">
              DocMind
            </span>
          </div>

          <nav className="px-3">
            <NavLink
              href="/documents"
              label="Documents"
              active={pathname.startsWith("/documents")}
            />
            <NavLink
              href="/chat"
              label="Chat"
              active={pathname.startsWith("/chat")}
            />
          </nav>

          <div className="mt-6 flex min-h-0 flex-1 flex-col">
            <div className="flex items-center justify-between px-5 pb-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-zinc-500">
                Conversations
              </span>
            </div>
            <ul className="min-h-0 flex-1 space-y-0.5 overflow-y-auto px-3 pb-3">
              {conversations.length === 0 && (
                <li className="px-2 py-1.5 text-xs text-zinc-600">
                  No conversations yet
                </li>
              )}
              {conversations.map((c) => {
                const active = pathname === `/chat/${c.id}`;
                return (
                  <li key={c.id} className="group relative">
                    <Link
                      href={`/chat/${c.id}`}
                      className={cn(
                        "block truncate rounded-lg px-2 py-1.5 pr-8 text-sm transition-colors",
                        active
                          ? "bg-zinc-800 text-zinc-100"
                          : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200",
                      )}
                      title={c.title}
                    >
                      {c.title}
                    </Link>
                    <button
                      type="button"
                      onClick={() => setPendingDelete(c)}
                      aria-label={`Delete conversation ${c.title}`}
                      className={cn(
                        "absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-1 text-zinc-500",
                        "opacity-0 transition-opacity hover:text-red-400 focus-visible:opacity-100 group-hover:opacity-100",
                      )}
                    >
                      <TrashIcon />
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>

          <div className="border-t border-zinc-800 px-4 py-3">
            <div className="flex items-center justify-between gap-2">
              <span
                className="min-w-0 truncate text-xs text-zinc-400"
                title={value.user.email}
              >
                {value.user.email}
              </span>
              <Button variant="ghost" size="sm" onClick={logout}>
                Log out
              </Button>
            </div>
          </div>
        </aside>

        <main className="min-w-0 flex-1 overflow-y-auto">{children}</main>
      </div>

      <Modal
        open={pendingDelete !== null}
        onClose={() => setPendingDelete(null)}
        title="Delete conversation"
        footer={
          <>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setPendingDelete(null)}
            >
              Cancel
            </Button>
            <Button
              variant="danger"
              size="sm"
              loading={deleting}
              onClick={confirmDelete}
            >
              Delete
            </Button>
          </>
        }
      >
        Delete{" "}
        <span className="font-medium text-zinc-100">
          &ldquo;{pendingDelete?.title}&rdquo;
        </span>
        ? This removes all of its messages and cannot be undone.
      </Modal>
    </AppContext.Provider>
  );
}

function NavLink({
  href,
  label,
  active,
}: {
  href: string;
  label: string;
  active: boolean;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "mb-0.5 block rounded-lg px-2 py-1.5 text-sm font-medium transition-colors",
        active
          ? "bg-indigo-500/15 text-indigo-300"
          : "text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200",
      )}
    >
      {label}
    </Link>
  );
}

function TrashIcon() {
  return (
    <svg
      className="h-3.5 w-3.5"
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M2.5 4.5h11M6.5 2.5h3M4 4.5l.6 8.6a1 1 0 001 .9h4.8a1 1 0 001-.9l.6-8.6M6.5 7v4M9.5 7v4" />
    </svg>
  );
}
