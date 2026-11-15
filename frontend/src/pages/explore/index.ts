// SPDX-License-Identifier: Apache-2.0
import type { PageModule } from '../../shell/router';

const page: PageModule = {
  path: '/explore',
  title: 'Explore',
  navLabel: 'Explore',
  navGroup: 'legal',
  order: 89,
  load: () => import('./Explore.svelte'),
};
export default page;
