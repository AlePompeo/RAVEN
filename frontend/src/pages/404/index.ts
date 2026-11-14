// SPDX-License-Identifier: Apache-2.0
import type { PageModule } from '../../shell/router';

const page: PageModule = {
  path: '/404',
  titleKey: 'title.notFound',
  load: () => import('./NotFound.svelte'),
};
export default page;
