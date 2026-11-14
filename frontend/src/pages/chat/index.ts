// SPDX-License-Identifier: Apache-2.0
import type { PageModule } from '../../shell/router';

const page: PageModule = {
  path: '/chat',
  titleKey: 'title.assistant',
  section: '/learn',
  order: 50,
  load: () => import('./Chat.svelte'),
};
export default page;
