// SPDX-License-Identifier: Apache-2.0
import type { PageModule } from '../../shell/router';

const page: PageModule = {
  path: '/privacy',
  titleKey: 'title.privacy',
  navKey: 'nav.privacy',
  navGroup: 'legal',
  order: 91,
  load: () => import('./Privacy.svelte'),
};
export default page;
