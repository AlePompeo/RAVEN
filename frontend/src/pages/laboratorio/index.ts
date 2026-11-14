// SPDX-License-Identifier: Apache-2.0
import type { PageModule } from '../../shell/router';

const page: PageModule = {
  path: '/laboratorio',
  titleKey: 'title.lab',
  section: '/explore',
  order: 40,
  load: () => import('./Laboratorio.svelte'),
};
export default page;
