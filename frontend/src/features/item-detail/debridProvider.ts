import { humanizeServiceKey } from '../dashboard/serviceSetupMessages';

export type FilesystemEntryLike = {
  provider?: string | null;
};

export function getDebridProviderLabel(
  filesystemEntry?: FilesystemEntryLike | null,
): string | null {
  const provider = filesystemEntry?.provider?.trim();
  if (!provider) return null;
  return humanizeServiceKey(provider);
}
