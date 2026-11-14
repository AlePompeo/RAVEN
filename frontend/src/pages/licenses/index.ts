// SPDX-License-Identifier: Apache-2.0
import type { PageModule } from '../../shell/router';

const page: PageModule = {
  path: '/licenses',
  titleKey: 'title.licenses',
  navKey: 'nav.licenses',
  navGroup: 'legal',
  order: 90,
  load: () => import('./Licenses.svelte'),
};
export default page;
