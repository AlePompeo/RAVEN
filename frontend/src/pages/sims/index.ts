// SPDX-License-Identifier: Apache-2.0
import type { PageModule } from '../../shell/router';

const page: PageModule = {
  path: '/sims',
  titleKey: 'title.sims',
  section: '/explore',
  order: 37,
  load: () => import('./Sims.svelte'),
};
export default page;
