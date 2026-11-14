// SPDX-License-Identifier: Apache-2.0
import type { PageModule } from '../../shell/router';

const page: PageModule = {
  path: '/about',
  titleKey: 'title.about',
  navKey: 'nav.about',
  navGroup: 'legal',
  order: 87,
  load: () => import('./About.svelte'),
};

export default page;
