import { useCallback, useEffect, useMemo, useState } from 'react';
import { ViewLayout, ViewHeader, Panel } from '../../shared/ui/PagePrimitives';
import { apiGet } from '../../shared/api/api';
import type { AppRoute } from '../../app/routeTypes';

interface MountEntry {
  name: string;
  vfsPath: string;
  absPath: string;
}

type DirNode = {
  kind: 'dir';
  name: string;
  vfsPath: string;
  dirs: Map<string, DirNode>;
  files: MountEntry[];
};

function createDirNode(name: string, vfsPath: string): DirNode {
  return { kind: 'dir', name, vfsPath, dirs: new Map(), files: [] };
}

function buildTree(entries: MountEntry[]): DirNode {
  const root = createDirNode('', '/');

  for (const e of entries) {
    const parts = e.vfsPath.split('/').filter(Boolean);
    if (parts.length === 0) continue;

    let current = root;
    let currentPath = '';

    for (let i = 0; i < parts.length - 1; i++) {
      const part = parts[i]!;
      currentPath += `/${part}`;

      let next = current.dirs.get(part);
      if (!next) {
        next = createDirNode(part, currentPath);
        current.dirs.set(part, next);
      }
      current = next;
    }

    current.files.push(e);
  }

  return root;
}

function getDir(root: DirNode, cwd: string[]): DirNode | null {
  let current: DirNode = root;
  for (const seg of cwd) {
    const next = current.dirs.get(seg);
    if (!next) return null;
    current = next;
  }
  return current;
}

function countFiles(root: DirNode): number {
  let total = 0;
  const stack: DirNode[] = [root];
  while (stack.length) {
    const node = stack.pop()!;
    total += node.files.length;
    for (const child of node.dirs.values()) stack.push(child);
  }
  return total;
}

function filterTree(root: DirNode, needle: string): DirNode {
  const match = (s: string) => s.toLowerCase().includes(needle);

  const walk = (node: DirNode): DirNode | null => {
    const next = createDirNode(node.name, node.vfsPath);

    // files
    for (const f of node.files) {
      if (
        match(f.name) ||
        match(f.vfsPath) ||
        match(f.absPath)
      ) {
        next.files.push(f);
      }
    }

    // dirs
    for (const [name, child] of node.dirs.entries()) {
      const keepChild = walk(child);
      if (keepChild) next.dirs.set(name, keepChild);
    }

    const dirMatches = node.name ? match(node.name) || match(node.vfsPath) : false;
    const hasChildren = next.files.length > 0 || next.dirs.size > 0;

    if (dirMatches || hasChildren) return next;
    return null;
  };

  return walk(root) ?? createDirNode('', '/');
}

export default function MountView({ route }: { route: AppRoute }) {
  const [entries, setEntries] = useState<MountEntry[]>([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [cwd, setCwd] = useState<string[]>([]);

  const fetchMount = useCallback(async () => {
    const response = await apiGet('/mount');
    if (!response.ok) {
      setError(response.error || 'Failed to load mount data.');
      setEntries([]);
      setLoading(false);
      return;
    }
    const files = response.data?.files ?? {};
    setEntries(
      Object.entries(files).map(([vfsPath, absPath]) => {
        const name =
          String(vfsPath).split('/').filter(Boolean).at(-1) ?? String(vfsPath);
        return {
          name,
          vfsPath: String(vfsPath),
          absPath: String(absPath),
        };
      }),
    );
    setError(null);
    setLoading(false);
  }, []);

  useEffect(() => {
    fetchMount();
  }, [fetchMount]);

  const needle = search.trim().toLowerCase();
  const tree = useMemo(() => buildTree(entries), [entries]);
  const totalFiles = useMemo(() => countFiles(tree), [tree]);
  const filteredTree = useMemo(
    () => (needle ? filterTree(tree, needle) : tree),
    [tree, needle],
  );
  const visibleFiles = useMemo(() => countFiles(filteredTree), [filteredTree]);

  const currentDir = useMemo(() => getDir(filteredTree, cwd), [filteredTree, cwd]);
  const currentDirs = useMemo(() => {
    const dir = currentDir;
    if (!dir) return [];
    return Array.from(dir.dirs.values()).sort((a, b) => a.name.localeCompare(b.name));
  }, [currentDir]);
  const currentFiles = useMemo(() => {
    const dir = currentDir;
    if (!dir) return [];
    return [...dir.files].sort((a, b) => a.name.localeCompare(b.name));
  }, [currentDir]);

  return (
    <ViewLayout className="view-mount" view="mount">
      <ViewHeader
        title="Mounted Files"
        subtitle="Current VFS mount inventory exposed by the backend filesystem service."
      />
      <Panel className="mount-panel">
        <div className="toolbar toolbar--mount">
          <input
            type="search"
            placeholder="Filter by file/path"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="explore-breadcrumbs" style={{ marginTop: '0.55rem' }}>
          <button type="button" className="pill pill--origin" onClick={() => setCwd([])}>
            /
          </button>
          {cwd.map((seg, idx) => (
            <button
              key={`${seg}-${idx}`}
              type="button"
              className="pill pill--text"
              onClick={() => setCwd(cwd.slice(0, idx + 1))}
            >
              {seg}
            </button>
          ))}
        </div>
        <div className="mount-stats">
          {loading
            ? 'Loading…'
            : `${visibleFiles.toLocaleString()} / ${totalFiles.toLocaleString()} files`}
        </div>
        {error ? (
          <p className="muted">{error}</p>
        ) : !currentDir ? (
          <p className="muted">Folder not found.</p>
        ) : currentDirs.length === 0 && currentFiles.length === 0 ? (
          <p className="muted">
            {needle ? 'No matching mounted files or folders.' : 'Folder is empty.'}
          </p>
        ) : (
          <div className="mount-list">
            {cwd.length > 0 ? (
              <button
                type="button"
                className="mount-row mount-row--dir"
                onClick={() => setCwd(cwd.slice(0, -1))}
              >
                <strong title="..">..</strong>
                <span className="muted">Up</span>
              </button>
            ) : null}

            {currentDirs.map((dir) => (
              <button
                key={dir.vfsPath}
                type="button"
                className="mount-row mount-row--dir"
                onClick={() => setCwd([...cwd, dir.name])}
              >
                <strong title={dir.name}>{dir.name}</strong>
                <span className="muted" title={dir.vfsPath}>
                  {dir.vfsPath}
                </span>
              </button>
            ))}

            {currentFiles.map((entry) => (
              <div key={entry.vfsPath} className="mount-row">
                <strong title={entry.name}>{entry.name}</strong>
                <span className="muted" title={entry.vfsPath}>
                  {entry.vfsPath}
                </span>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </ViewLayout>
  );
}
