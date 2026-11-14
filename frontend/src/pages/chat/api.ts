// SPDX-License-Identifier: Apache-2.0
import { createSseParser, toChatEvent, SseLimitError, type SseEvent } from './sse';

export interface ChatMessage {
  role: 'user' | 'assistant'; // 'system' non e ammesso dal client
  content: string;
}

export type ChatResult = { status: 'done' } | { status: 'aborted' } | { status: 'error'; detail: string };

/** Provider eseguiti in locale, senza invio del testo a terzi. Ogni altro provider e considerato esterno. */
export const LOCAL_PROVIDERS: readonly string[] = ['echo-llm'];

export function isLocalProvider(id: string): boolean {
  return LOCAL_PROVIDERS.includes(id);
}

/**
 * Fail closed: il provider e "locale" solo se l'elenco dei provider e stato caricato, lo contiene
 * ed e uno stub locale noto. Altrimenti (elenco non disponibile, provider ignoto) vale come esterno.
 */
export function isVerifiedLocal(provider: string, knownIds: readonly string[] | null): boolean {
  return knownIds !== null && knownIds.includes(provider) && isLocalProvider(provider);
}

export async function streamChat(
  fetchFn: typeof fetch,
  messages: ChatMessage[],
  provider: string,
  signal: AbortSignal,
  onToken: (t: string) => void,
): Promise<ChatResult> {
  try {
    const res = await fetchFn('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify({ messages, provider }),
      signal,
    });
    if (!res.ok || !res.body) return { status: 'error', detail: `richiesta fallita (${res.status})` };
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    const parser = createSseParser();
    for (;;) {
      const { done, value } = await reader.read();
      let events: SseEvent[];
      try {
        events = parser.feed(done ? dec.decode() : dec.decode(value, { stream: true }));
      } catch (err) {
        await reader.cancel().catch(() => {});
        throw err;
      }
      for (const ev of events) {
        const ce = toChatEvent(ev);
        if (ce.type === 'token') onToken(ce.token);
        else if (ce.type === 'error') {
          await reader.cancel().catch(() => {});
          return { status: 'error', detail: ce.detail };
        } else if (ce.type === 'done') {
          await reader.cancel().catch(() => {});
          return { status: 'done' };
        }
      }
      if (done) return { status: 'error', detail: 'connessione chiusa prima della fine della risposta' };
    }
  } catch (e) {
    if (e instanceof SseLimitError) return { status: 'error', detail: 'risposta troppo grande, interrotta' };
    if (signal.aborted || (e instanceof DOMException && e.name === 'AbortError')) return { status: 'aborted' };
    return { status: 'error', detail: 'impossibile contattare il server' };
  }
}
