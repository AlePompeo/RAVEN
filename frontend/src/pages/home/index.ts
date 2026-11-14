// SPDX-License-Identifier: Apache-2.0
import type { PageModule } from '../../shell/router';

const page: PageModule = {
  path: '/',
  titleKey: 'title.home',
  navLabel: 'Home',
  order: 0,
  load: () => import('./Home.svelte'),
};
export default page;
