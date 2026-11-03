"""Simple converter for inspecting notebook code; NOT automatic ETL refactoring.

Usage: python tools/notebook_to_py.py input.ipynb output.py
Cells with !, %, %% or IPython/Colab-specific behavior are commented out.
Review/edit the result before importing as a normal Python module.
"""
import argparse
import json
from pathlib import Path


def convert_notebook(source: Path, destination: Path):
    notebook = json.loads(Path(source).read_text(encoding='utf-8'))
    lines = ['# Converted notebook - REVIEW before using as a module.',
             '# Move UI inputs, drive.mount(), and saving logic to the orchestrating notebook.\n']
    for index, cell in enumerate(notebook.get('cells', [])):
        if cell.get('cell_type') != 'code':
            continue
        lines.append(f'\n# ===== Original code cell {index} =====')
        content = ''.join(cell.get('source', []))
        if ('get_ipython(' in content or 'drive.mount(' in content or
            any(line.lstrip().startswith(('!', '%')) for line in content.splitlines())):
            lines.append('# NOTE: Cell contains notebook-specific commands; manually refactor:')
            lines.extend('# ' + line for line in content.splitlines())
        else:
            lines.append(content)
    Path(destination).parent.mkdir(parents=True, exist_ok=True)
    Path(destination).write_text('\n'.join(lines) + '\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    convert_notebook(args.source, args.destination)
