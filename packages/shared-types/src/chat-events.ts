export type ChatEventType =
  | "token"
  | "tool_call"
  | "tool_result"
  | "reasoning"
  | "error"
  | "done";

export interface BaseChatEvent {
  type: ChatEventType;
  requestId: string;
  timestamp: string;
}

export interface TokenEvent extends BaseChatEvent {
  type: "token";
  token: string;
}

export interface ToolCallEvent extends BaseChatEvent {
  type: "tool_call";
  toolName: string;
  input: Record<string, unknown>;
}

export interface ToolResultEvent extends BaseChatEvent {
  type: "tool_result";
  toolName: string;
  output: unknown;
}

export interface ReasoningEvent extends BaseChatEvent {
  type: "reasoning";
  summary: string;
}

export interface ErrorEvent extends BaseChatEvent {
  type: "error";
  code: string;
  message: string;
  retryable?: boolean;
}

export interface DoneEvent extends BaseChatEvent {
  type: "done";
  stopReason?: string;
}

export type ChatStreamEvent =
  | TokenEvent
  | ToolCallEvent
  | ToolResultEvent
  | ReasoningEvent
  | ErrorEvent
  | DoneEvent;
