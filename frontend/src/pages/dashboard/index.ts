// SPDX-License-Identifier: Apache-2.0
import type { PageModule } from '../../shell/router';
const page: PageModule = {
  path: '/dashboard',
  title: 'Dashboard',
  navLabel: 'Dashboard',
  order: 6,
  load: () => import('./Dashboard.svelte'),
};
export default page;
