"""Controlled GitHub publishing for the dissertation's CODE only.

For interactive Colab use; no raw data and no token in Git URLs or commits.
Drive/this package is treated as the authoritative editing copy.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ALLOWED_ROOT_FILES = {'README.md', 'requirements.txt', '.gitignore'}
ALLOWED_FOLDERS = {'reputation_etl', 'tests', 'tools', 'notebooks', 'docs'}
ALLOWED_EXTENSIONS = {'.py', '.ipynb', '.md', '.txt'}
SECRET_PATTERNS = [
    re.compile(r'AIza[A-Za-z0-9_-]{30,}'),
    re.compile(r'gh[pousr]_[A-Za-z0-9_]{20,}'),
    re.compile(r'github_pat_[A-Za-z0-9_]{20,}'),
    re.compile(r'sk-[A-Za-z0-9_-]{30,}'),
    re.compile(r'(?i)-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(args: list[str], directory: Path, env=None):
    return subprocess.run(['git', *args], cwd=directory, env=env,
                          capture_output=True, text=True, check=True).stdout.strip()


def _files_to_publish(root: Path) -> list[Path]:
    chosen = [root / name for name in sorted(ALLOWED_ROOT_FILES) if (root / name).is_file()]
    for folder in sorted(ALLOWED_FOLDERS):
        d = root / folder
        if not d.is_dir():
            continue
        chosen.extend(p for p in d.rglob('*') if p.is_file() and p.suffix in ALLOWED_EXTENSIONS
                      and not any(x in {'__pycache__', '.ipynb_checkpoints', 'runs', 'data', 'outputs'}
                                  for x in p.relative_to(root).parts))
    return sorted(chosen)


def audit_code_files(root: Path):
    """Return code files only; refuse recognized API key material and oversized files."""
    root = root.resolve()
    files = _files_to_publish(root)
    violations = []
    for path in files:
        if path.stat().st_size > 5 * 1024 * 1024:
            violations.append(f'{path.relative_to(root)}: >5 MiB; inspect before publishing')
            continue
        text = path.read_text(encoding='utf-8', errors='replace')
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            violations.append(f'{path.relative_to(root)}: potential embedded credential')
    if violations:
        raise ValueError('GitHub upload blocked by preflight checks:\n- ' + '\n- '.join(violations))
    return files


def publish_code(root: Path, repo_slug: str, token: str, *,
                 message: str = 'Update dissertation research code',
                 dry_run: bool = True, allow_initial_overwrite: bool = False) -> dict:
    """Clone the *latest* default branch, compare code, then optionally commit.

    If a previously synchronized remote file changed independently, refuse to
    replace it. For an existing repo on the very first run, set
    allow_initial_overwrite=True AFTER inspecting the dry run.
    The .code_sync_state.json file is stored in the local project root only.
    """
    root = Path(root).resolve()
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo_slug):
        raise ValueError('repo_slug must be YOUR_USERNAME/YOUR_REPO')
    if not token:
        raise ValueError('Missing GitHub token; use a Colab Secret, not a notebook string')
    files = audit_code_files(root)
    state_path = root / '.code_sync_state.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    if state and state.get('repository') != repo_slug:
        raise ValueError('Sync state belongs to a different repository; review before repointing')
    old_hashes = state.get('remote_file_hashes', {})

    # Credentials passed through environment using a temp askpass script;
    # never placed in a command argument, remote URL, notebook, or commit.
    with tempfile.TemporaryDirectory(prefix='reputation_git_') as temp:
        workspace = Path(temp)
        askpass = workspace / 'askpass.sh'
        askpass.write_text('#!/bin/sh\ncase "$1" in *Username*) echo "x-access-token";; *) printf "%s\\n" "$GITHUB_TOKEN";; esac\n')
        askpass.chmod(0o700)
        env = os.environ.copy()
        env.update({'GIT_ASKPASS': str(askpass), 'GIT_TERMINAL_PROMPT': '0',
                    'GITHUB_TOKEN': token})
        repo = workspace / 'repo'
        subprocess.run(['git', 'clone', '--quiet', '--depth', '1',
                        f'https://github.com/{repo_slug}.git', str(repo)],
                       check=True, env=env, capture_output=True, text=True)
        comparison = []
        conflicted = []
        for file in files:
            rel = str(file.relative_to(root).as_posix())
            dest = repo / rel
            new_hash = _sha256(file)
            remote_hash = _sha256(dest) if dest.exists() else None
            if remote_hash == new_hash:
                status = 'unchanged'
            elif remote_hash is None:
                status = 'new'
            else:
                previous = old_hashes.get(rel)
                if remote_hash == previous or (previous is None and allow_initial_overwrite):
                    status = 'modified'
                else:
                    status = 'conflict'
                    conflicted.append(rel)
            comparison.append({'file': rel, 'status': status})
        result = {'repository': repo_slug, 'dry_run': dry_run,
                  'files': comparison, 'conflicts': conflicted,
                  'changed': sum(x['status'] in {'new', 'modified'} for x in comparison)}
        if conflicted:
            result['message'] = 'Conflict: remote files differ from last known copy. Review in GitHub; nothing pushed.'
            return result
        if dry_run:
            result['message'] = 'Preview only: no files uploaded.'
            return result
        changed = [item for item in comparison if item['status'] in {'new', 'modified'}]
        if not changed:
            result['message'] = 'No code changes to push.'
            return result
        for item in changed:
            dest = repo / item['file']
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / item['file'], dest)
        _git(['add', '--', *[x['file'] for x in changed]], repo)
        _git(['-c', 'user.name=Research Code Sync',
              '-c', 'user.email=research-code-sync@users.noreply.github.com',
              'commit', '-m', message], repo)
        # On the current repo's default branch; clone has latest remote snapshot.
        _git(['push', 'origin', 'HEAD'], repo, env=env)
        hashes = {x['file']: _sha256(repo / x['file'])
                  for x in comparison if (repo / x['file']).exists()}
        state_path.write_text(json.dumps({'repository': repo_slug,
                                          'remote_file_hashes': hashes}, indent=2))
        result['message'] = 'Code changes pushed to GitHub.'
        result['commit'] = _git(['rev-parse', 'HEAD'], repo)
        return result
