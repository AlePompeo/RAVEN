// SPDX-License-Identifier: Apache-2.0
import type { PageModule } from '../../shell/router';

const page: PageModule = {
  path: '/model',
  titleKey: 'title.model',
  navKey: 'nav.model',
  navGroup: 'legal',
  order: 89,
  aliases: { '/validation': '' },
  load: () => import('./Model.svelte'),
};
export default page;
