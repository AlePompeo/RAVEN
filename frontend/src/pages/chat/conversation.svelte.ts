// SPDX-License-Identifier: Apache-2.0
import { pageCtx } from '../../shell/pageContext.svelte';
import { sanitizeParams, type Level, type PageContext } from './assistant';
import { Session } from './session.svelte';

export const conversation = $state({
  pageId: 'chat', level: 'intermedio' as Level, language: 'auto' as 'auto' | 'it' | 'en',
  allowExternal: false, includeContext: false, cloudAvailable: false,
});
export function conversationContext(): PageContext {
  const visible = conversation.includeContext ? sanitizeParams(pageCtx.params) : {};
  const params = conversation.allowExternal ? Object.fromEntries(Object.entries(visible).filter(([, value]) => typeof value === 'number')) : visible;
  return {
    page_id: conversation.pageId,
    ...(conversation.includeContext && pageCtx.simulation_id ? { simulation_id: pageCtx.simulation_id } : {}),
    ...(Object.keys(params).length ? { params } : {}),
  };
}
export const conversationSession = new Session({
  getContext: conversationContext,
  getLevel: () => conversation.level,
  getLang: () => conversation.language === 'auto' ? undefined : conversation.language,
  getAllowExternal: () => conversation.allowExternal,
  getProvider: () => conversation.allowExternal && conversation.cloudAvailable ? 'groq' : undefined,
});

export function resetConversation() {
  conversationSession.reset();
  conversation.allowExternal = false;
  conversation.includeContext = false;
  conversation.level = 'intermedio';
  conversation.language = 'auto';
  conversation.cloudAvailable = false;
  conversation.pageId = 'chat';
}
