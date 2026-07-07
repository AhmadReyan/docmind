/**
 * TypeScript transcription of docs/api-contract.md.
 * Do not change shapes here without updating the contract document first.
 */

export interface ApiError {
  detail: string;
  code:
    | "unauthorized"
    | "invalid_credentials"
    | "email_taken"
    | "not_found"
    | "validation_error"
    | "file_too_large"
    | "unsupported_file_type"
    | "rate_limited"
    | "internal_error";
}

export interface Paginated<T> {
  items: T[];
  total: number;
}

export interface UserOut {
  id: string;
  email: string;
  created_at: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export type DocumentStatus = "pending" | "processing" | "ready" | "failed";

export interface DocumentOut {
  id: string;
  title: string;
  filename: string;
  mime_type: "application/pdf" | "text/plain" | "text/markdown";
  size_bytes: number;
  status: DocumentStatus;
  error_message: string | null;
  page_count: number | null;
  chunk_count: number | null;
  created_at: string;
}

export interface ChunkOut {
  id: string;
  chunk_index: number;
  content: string;
  page_number: number | null;
  token_count: number;
}

export interface ConversationOut {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationDetail extends ConversationOut {
  messages: MessageOut[];
}

export interface MessageOut {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources: Source[] | null;
  created_at: string;
}

export interface Source {
  index: number;
  chunk_id: string;
  document_id: string;
  document_title: string;
  page_number: number | null;
  snippet: string;
  score: number;
}

export interface SendMessageRequest {
  content: string;
}

/** SSE events emitted by POST /api/conversations/{id}/messages */
export type ChatStreamEvent =
  | { event: "sources"; data: { sources: Source[] } }
  | { event: "token"; data: { delta: string } }
  | { event: "done"; data: { message_id: string; conversation_title: string } }
  | { event: "error"; data: { detail: string; code: string } };

export interface HealthOut {
  status: "ok";
  db: boolean;
  redis: boolean;
  providers: {
    llm: string;
    embedding: string;
  };
}
