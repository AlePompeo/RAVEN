// SPDX-License-Identifier: Apache-2.0
import type { PageModule } from '../../shell/router';

const page: PageModule = {
  path: '/contacts',
  titleKey: 'title.team',
  navKey: 'title.team',
  order: 30,
  load: () => import('./Contacts.svelte'),
};
export default page;
