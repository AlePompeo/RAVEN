// SPDX-License-Identifier: Apache-2.0
import type { PageModule } from '../../shell/router';

const page: PageModule = {
  path: '/demo',
  titleKey: 'title.demo',
  section: '/explore',
  order: 19,
  load: () => import('./Demo.svelte'),
};

export default page;
