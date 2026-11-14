// SPDX-License-Identifier: Apache-2.0
import type { PageModule } from '../../shell/router';

const page: PageModule = {
  path: '/learn',
  title: 'Learn',
  navLabel: 'Learn',
  order: 20,
  load: () => import('./Learn.svelte'),
};
export default page;
