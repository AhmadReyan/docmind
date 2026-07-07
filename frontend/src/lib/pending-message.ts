/**
 * Hand-off for the "/chat → /chat/[id]" flow: the new-chat page stores the
 * user's first message here, and the conversation page sends it on mount.
 */
const PREFIX = "docmind:pending:";

export function stashPendingMessage(conversationId: string, content: string) {
  try {
    sessionStorage.setItem(`${PREFIX}${conversationId}`, content);
  } catch {
    // Storage unavailable (private mode, quota) — the user can resend.
  }
}

export function takePendingMessage(conversationId: string): string | null {
  try {
    const key = `${PREFIX}${conversationId}`;
    const content = sessionStorage.getItem(key);
    if (content !== null) sessionStorage.removeItem(key);
    return content;
  } catch {
    return null;
  }
}
