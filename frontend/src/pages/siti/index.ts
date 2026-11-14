// SPDX-License-Identifier: Apache-2.0
import type { PageModule } from '../../shell/router';

const page: PageModule = {
  path: '/siti',
  titleKey: 'title.sites',
  section: '/explore',
  order: 30,
  aliases: { '/viewer': 'tab=globo', '/compare': 'tab=classifica' },
  load: () => import('./Siti.svelte'),
};
export default page;
