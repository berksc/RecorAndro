"""Controlled interruption helper, used only for disposable recovery tests."""

from contextlib import ExitStack
from pathlib import Path
import sys
import time
import os
from unittest.mock import patch

from recorandro.config import Config
from recorandro import normalization, segmentation, exports
from recorandro.recovery import recover_session
from recorandro.storage import OwnedDirectory


def main():
    root, sid, checkpoint, marker = sys.argv[1:]
    config = Config(Path(root))

    def pause():
        Path(marker).write_text('checkpoint reached')
        while True:
            time.sleep(0.05)

    execute, publish, atomic = normalization._execute, OwnedDirectory.publish, OwnedDirectory.atomic_json
    boundaries = segmentation.plan_boundaries
    copy_audio = exports._copy

    def generating(args, timeout, phase, **kwargs):
        if ((checkpoint == 'normalization_generate' and phase == 'encode') or
                (checkpoint == 'export_generate' and phase == 'part_encode')):
            Path(args[-1]).write_bytes(b'controlled partial encoder bytes')
            pause()
        return execute(args, timeout, phase, **kwargs)

    def moving(folder, temporary, final, destination=None):
        publish(folder, temporary, final, destination)
        if ((checkpoint == 'normalization_publish' and final == 'normalized.m4a') or
                (checkpoint == 'export_publish' and final.startswith('part_'))):
            pause()

    def saving(folder, record):
        atomic(folder, record)
        if 'audio' not in record:
            if ((checkpoint == 'plan_report' and record.get('status') == 'planned') or
                    (checkpoint == 'export_report' and record.get('status') == 'export_succeeded')):
                pause()

    def planning(*args, **kwargs):
        if checkpoint == 'plan_generate':
            pause()
        return boundaries(*args, **kwargs)

    def copying(stream, folder, leaf, timeout):
        if checkpoint == 'export_generate':
            with os.fdopen(folder.open(leaf, os.O_WRONLY | os.O_CREAT | os.O_EXCL), 'wb') as partial:
                partial.write(b'controlled partial copy bytes')
            pause()
        return copy_audio(stream, folder, leaf, timeout)

    with ExitStack() as stack:
        stack.enter_context(patch.object(normalization, '_execute', generating))
        stack.enter_context(patch.object(exports, '_execute', generating))
        stack.enter_context(patch.object(exports, '_copy', copying))
        stack.enter_context(patch.object(segmentation, 'plan_boundaries', planning))
        stack.enter_context(patch.object(OwnedDirectory, 'publish', moving))
        stack.enter_context(patch.object(OwnedDirectory, 'atomic_json', saving))
        result = recover_session(config, sid)
    raise RuntimeError('Checkpoint not reached: ' + str(result))


if __name__ == '__main__':
    main()
