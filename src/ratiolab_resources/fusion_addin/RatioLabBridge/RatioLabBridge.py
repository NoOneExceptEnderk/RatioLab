# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Fusion add-in entry point; SDK operations execute in a CustomEvent handler."""
import importlib.util
from pathlib import Path
import sys
import uuid
import adsk.core
import adsk.fusion

_server = None
_event = None
_handler = None
_event_id = None


def _local_module(name):
    # Fusion can load several add-ins with similarly named helper modules.
    # Load our siblings by absolute path under private module names.
    qualified = '_ratiolab_fusion_' + name
    spec = importlib.util.spec_from_file_location(qualified, Path(__file__).parent/(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[qualified] = module
    spec.loader.exec_module(module)
    return module


def run(context):
    global _server, _event, _handler, _event_id
    if _server is not None:
        return
    app = adsk.core.Application.get()
    transport = _local_module('bridge_server')
    importer = _local_module('fusion_import')
    _event_id = 'RatioLabBridge.' + str(uuid.uuid4())
    backend = importer.FusionImporter(app)
    event_id = _event_id
    # Fusion's Python overload requires the additionalInfo argument on some
    # native SDK versions, even though generated stubs advertise *args.
    server = transport.BridgeServer(lambda: app.fireCustomEvent(event_id, ''), backend.handle)
    backend.session_id = server.session_id

    class Handler(adsk.core.CustomEventHandler):
        def notify(self, args):
            server.drain()

    try:
        _event = app.registerCustomEvent(_event_id)
        _handler = Handler()
        if not _event.add(_handler):
            raise RuntimeError('Could not register the Fusion event handler')
        server.start()
        _server = server
    except Exception:
        server.stop()
        if _event_id:
            app.unregisterCustomEvent(_event_id)
        _event = _handler = _event_id = None
        raise


def stop(context):
    global _server, _event, _handler, _event_id
    if _server is not None:
        _server.stop()
    if _event is not None and _handler is not None:
        _event.remove(_handler)
    if _event_id is not None:
        adsk.core.Application.get().unregisterCustomEvent(_event_id)
    _server = _event = _handler = _event_id = None
