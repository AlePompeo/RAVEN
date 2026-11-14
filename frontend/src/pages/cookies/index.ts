// SPDX-License-Identifier: Apache-2.0
import type { PageModule } from '../../shell/router';

const page: PageModule = {
  path: '/cookies',
  titleKey: 'title.cookies',
  navKey: 'nav.cookies',
  navGroup: 'legal',
  order: 92,
  load: () => import('./Cookies.svelte'),
};
export default page;
