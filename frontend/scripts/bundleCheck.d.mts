// SPDX-License-Identifier: Apache-2.0
export interface ManifestChunk {
  file: string;
  imports?: string[];
  dynamicImports?: string[];
  isEntry?: boolean;
}
export function htmlScripts(html: string): Set<string>;
export function analyzeBundle(a: {
  html: string;
  manifest: Record<string, ManifestChunk>;
  readFile: (file: string) => Uint8Array;
  maxBytes: number;
}): { raw: number; gz: number; chunks: string[]; problems: string[] };
