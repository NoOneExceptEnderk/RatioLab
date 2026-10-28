"""Publish a whole export directory in one rename, without replacing results."""
from contextlib import contextmanager
from pathlib import Path
import os
import shutil
import tempfile


def write_text(path, content, encoding='utf-8'):
    """Replace one file only after a complete successful write."""
    path = Path(path)
    descriptor, name = tempfile.mkstemp(prefix='.'+path.name+'-',suffix='.tmp',dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor,'w',encoding=encoding) as output:
            output.write(content)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path


@contextmanager
def directory(target):
    """Yield a sibling staging directory and publish only on success.

    A reservation file serializes RatioLab writers to the same target. Existing
    directories (including empty ones) are never replaced. All generated paths
    must be relative to the staging directory; external assets are prohibited.
    """
    target = Path(target).absolute()
    target.parent.mkdir(parents=True, exist_ok=True)
    lock = target.with_name('.'+target.name+'.export-lock')
    fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    staging = None
    try:
        if target.exists() or target.is_symlink():
            raise FileExistsError(f'Export already exists: {target}')
        staging = Path(tempfile.mkdtemp(prefix='.'+target.name+'-', dir=target.parent))
        yield staging
        if target.exists() or target.is_symlink():
            raise FileExistsError(f'Export already exists: {target}')
        staging.rename(target)
        staging = None
    finally:
        if staging is not None:
            shutil.rmtree(staging)
        lock.unlink(missing_ok=True)
