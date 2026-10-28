"""Installed command and diagnostics; GTK is imported only when needed."""
import argparse
import ctypes as C
import json
from pathlib import Path
import sys

from app_paths import (APP_ID, bundle_dir, config_dir, data_dir, default_output_dir,
                       prepare_native_runtime, require_gtk_version, resource_path)


def diagnose(gui=False):
    """Report the actual runtime; --gui also requires a working desktop GL context."""
    prepare_native_runtime()
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import Gtk
    require_gtk_version(Gtk)
    import cairo
    from gl_loader import load_epoxy
    loader = load_epoxy()
    typelib = Path(gi.Repository.get_default().get_typelib_path('Gtk'))
    bundled = bundle_dir()
    if bundled is not None:
        allowed = bundled.parent if sys.platform == 'darwin' else bundled
        if not typelib.resolve().is_relative_to(allowed.resolve()):
            raise RuntimeError(f'GTK loaded outside the application bundle: {typelib}')
    result = dict(application_id=APP_ID, python=sys.executable,
                  gtk='.'.join(str(v) for v in (Gtk.get_major_version(), Gtk.get_minor_version(), Gtk.get_micro_version())),
                  cairo=cairo.cairo_version_string(), epoxy=loader._name,
                  gtk_typelib=str(typelib), bundled=bundled is not None,
                  icon=str(resource_path('branding/ratiolab-icon.png')),
                  config_dir=str(config_dir()), data_dir=str(data_dir()),
                  default_exports=str(default_output_dir()))
    for name in ('catalogo-cuscinetti.json', 'catalogo-hardware.json'):
        json.loads(resource_path(name).read_text(encoding='utf-8'))
    if gui:
        from gi.repository import Gdk, GLib
        if not Gtk.init_check() or Gdk.Display.get_default() is None:
            raise RuntimeError('A graphical desktop session is required for --diagnose-gui')
        from geometry import generate
        from preview3d import Preview3D
        loop = GLib.MainLoop()
        completed = False
        failure = None
        timeout_fired = False
        class DiagnosticPreview(Preview3D):
            def on_render(self, widget, context):
                nonlocal completed, failure
                # Gtk.GLArea's render signal stops at a handler returning True.
                # Wrap the real renderer rather than connecting an after-handler
                # that is never reached. Read its framebuffer while current.
                try:
                    super().on_render(widget, context)
                    if self.failure or self.get_error() or not self.gl:
                        raise RuntimeError(str(self.failure or self.get_error() or 'OpenGL did not initialize'))
                    width = self.get_width()*self.get_scale_factor()
                    height = self.get_height()*self.get_scale_factor()
                    pixels = C.create_string_buffer(width*height*4)
                    self.gl.ReadPixels(0, 0, width, height, 0x1908, 0x1401, pixels)
                    if self.gl.GetError():
                        raise RuntimeError('The OpenGL preview reported an error')
                    raw = pixels.raw
                    if not raw or not any(raw[i:i+4] != raw[:4] for i in range(4, len(raw), 4)):
                        raise RuntimeError('The OpenGL preview produced a blank framebuffer')
                    version = loader.epoxy_gl_version
                    version.restype = C.c_int
                    version.argtypes = []
                    result['opengl_version'] = version()
                    result['graphics_api'] = 'OpenGL ES' if self.use_es else 'OpenGL'
                    from gl_loader import bind_function
                    get_string = bind_function(loader, 'GetString', C.c_char_p, [C.c_uint])
                    result['graphics_renderer'] = (get_string(0x1F01) or b'').decode('utf-8', errors='replace')
                    if result['opengl_version'] < (30 if self.use_es else 33):
                        raise RuntimeError('OpenGL ES 3.0 or desktop OpenGL 3.3 or newer is required')
                    result['framebuffer_has_geometry'] = True
                    completed = True
                except Exception as error:
                    failure = str(error)
                finally:
                    GLib.idle_add(loop.quit)
                return True
        area = DiagnosticPreview()
        area.set_design(generate('spur'))
        window = Gtk.Window(title='RatioLab OpenGL check', default_width=640, default_height=480)
        window.set_child(area)
        def timed_out():
            nonlocal failure, timeout_fired
            timeout_fired = True
            failure = str(area.failure or area.get_error() or 'Timed out waiting for the OpenGL preview')
            loop.quit()
            return False
        timeout = GLib.timeout_add_seconds(20, timed_out)
        try:
            window.present()
            loop.run()
            if failure:
                raise RuntimeError(failure)
            if area.failure or area.get_error() or not completed or not area.gl:
                raise RuntimeError(str(area.failure or area.get_error() or 'OpenGL did not initialize'))
            result['preview'] = 'rendered'
        finally:
            if not timeout_fired:
                GLib.source_remove(timeout)
            window.destroy()
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description='RatioLab · parametric gears and reducers')
    parser.add_argument('--version', action='version', version='RatioLab 0.1.0')
    parser.add_argument('--diagnose', action='store_true', help='Check installed GTK, Cairo, resources and GL loader')
    parser.add_argument('--diagnose-gui', action='store_true', help='Also open and render a test OpenGL preview')
    parser.add_argument('--self-test', action='store_true', help='Check runtime, preferences and model exports in a temporary profile')
    parser.add_argument('--self-test-gui', action='store_true', help='Also check the complete graphical workspace and exports')
    parser.add_argument('--install-desktop', action='store_true', help='Register this installation in the Linux application menu')
    parser.add_argument('--mcp', action='store_true', help='Serve local agent tools over MCP stdio without opening GTK')
    parser.add_argument('--workspace', type=Path, help='Explicit working directory for MCP projects and exports')
    args = parser.parse_args(argv)
    if args.mcp:
        if args.workspace is None:
            parser.error('--mcp requires --workspace')
        if any((args.install_desktop, args.self_test, args.self_test_gui, args.diagnose, args.diagnose_gui)):
            parser.error('--mcp cannot be combined with GUI or diagnostic commands')
        from ratiolab_mcp import main as serve
        return serve(['--workspace', str(args.workspace)])
    if args.workspace is not None:
        parser.error('--workspace is only used with --mcp')
    if args.install_desktop:
        from install_desktop import main as install
        return install([])
    if args.self_test or args.self_test_gui:
        try:
            from ratiolab_checks import self_test
            print(json.dumps(self_test(gui=args.self_test_gui), ensure_ascii=False, indent=2))
            return 0
        except Exception as error:
            print(f'RatioLab installation check failed: {error}', file=sys.stderr)
            return 1
    if args.diagnose or args.diagnose_gui:
        try:
            print(json.dumps(diagnose(gui=args.diagnose_gui), ensure_ascii=False, indent=2))
            return 0
        except Exception as error:
            print(f'RatioLab runtime check failed: {error}', file=sys.stderr)
            return 1
    prepare_native_runtime()
    try:
        from app import main as run
    except (ImportError, ValueError, RuntimeError) as error:
        print(f'RatioLab could not load GTK 4 for {sys.executable}: {error}\n'
              f'Install native dependencies for this Python as described in {resource_path("INSTALL.md")}.', file=sys.stderr)
        return 1
    return run([sys.argv[0]])


if __name__ == '__main__':
    raise SystemExit(main())
