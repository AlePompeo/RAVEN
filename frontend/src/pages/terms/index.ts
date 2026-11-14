// SPDX-License-Identifier: Apache-2.0
import type { PageModule } from '../../shell/router';

const page: PageModule = {
  path: '/terms',
  titleKey: 'title.terms',
  navKey: 'nav.terms',
  navGroup: 'legal',
  order: 94,
  load: () => import('./Terms.svelte'),
};
export default page;
