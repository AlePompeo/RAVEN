// SPDX-License-Identifier: Apache-2.0
/// <reference types="svelte" />
/// <reference types="vite/client" />

declare module '*.svelte' {
  import type { Component } from 'svelte';
  const component: Component<any>;
  export default component;
}
