// SPDX-License-Identifier: Apache-2.0
import type { PageModule } from '../../shell/router';

const page: PageModule = {
  path: '/pricing',
  titleKey: 'title.pricing',
  navKey: 'title.pricing',
  order: 25,
  load: () => import('./Pricing.svelte'),
};
export default page;
