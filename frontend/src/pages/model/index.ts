// SPDX-License-Identifier: Apache-2.0
import type { PageModule } from '../../shell/router';

const page: PageModule = {
  path: '/model',
  titleKey: 'title.model',
  aliases: { '/validation': '' },
  load: () => import('./Model.svelte'),
};
export default page;
