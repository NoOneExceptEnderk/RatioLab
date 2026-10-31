# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""GTK project lifecycle. All asynchronous answers belong to one document revision."""
from copy import deepcopy
import json
from math import isfinite
from pathlib import Path
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio, GLib
import app_paths
from geometry import FAMILIES, VARIANTS, defaults, generate
from project_document import Document, Store, atomic_json, equivalent
from gui_workflow import (numeric_value, numeric_snapshot_text, numeric_is_automatic,
                          set_numeric_value)


class ProjectActions:
    def init_projects(self):
        self.raw_edits = getattr(self, 'raw_edits', {})
        self.automatic_edits = getattr(self, 'automatic_edits', {})
        self.project_restoring = False
        self.project_dialog = None
        self.project_store = Store(app_paths.data_dir()/'projects')
        self.document = Document(self.project_snapshot())
        self.project_alive = True
        self.win.connect('close-request', self.close_project)
        self.update_document()
        self.recovery_idle = GLib.idle_add(self.offer_recovery)
        def removed(*args):
            self.project_alive = False
            if self.pending:
                GLib.source_remove(self.pending)
                self.pending = 0
            if self.recovery_idle:
                GLib.source_remove(self.recovery_idle)
                self.recovery_idle = 0
        self.win.connect('unrealize', removed)

    def collect_fields(self):
        """Read each entry independently: one incomplete value cannot erase others."""
        values = dict(self.values.get(self.family, defaults(self.family)))
        values.update(getattr(self, 'option_values', {}))
        raw = dict(getattr(self, 'raw_edits', {}).get(self.family, {}))
        automatic = set(getattr(self, 'automatic_edits', {}).get(self.family, []))
        for key, widget in self.inputs.items():
            if not widget.get_sensitive():
                # Derived displays are recomputed, rather than user edits. Keep
                # any earlier manual text separately for a return to manual mode.
                values.pop(key, None)
                continue
            raw[key] = numeric_snapshot_text(widget)
            if numeric_is_automatic(widget):
                automatic.add(key)
            else:
                automatic.discard(key)
            try:
                value = numeric_value(widget)
                if isfinite(value):
                    values[key] = value
            except ValueError:
                pass
        if hasattr(self, 'motion_rpm'):
            values['input_rpm'] = self.motion_rpm
            raw['input_rpm'] = numeric_snapshot_text(self.motion_speed_text)
            if numeric_is_automatic(self.motion_speed_text):
                automatic.add('input_rpm')
            else:
                automatic.discard('input_rpm')
            try:
                number = numeric_value(self.motion_speed_text)
                if isfinite(number):
                    values['input_rpm'] = number
            except ValueError:
                pass
        if self.family in VARIANTS:
            variants = list(VARIANTS[self.family])
            index = self.variant_selector.get_selected()
            if index < len(variants):
                values['variant'] = variants[index]
        self.values[self.family] = values
        if not hasattr(self, 'raw_edits'):
            self.raw_edits = {}
        self.raw_edits[self.family] = raw
        if not hasattr(self, 'automatic_edits'):
            self.automatic_edits = {}
        self.automatic_edits[self.family] = sorted(automatic.intersection(raw))
        return values

    def project_snapshot(self):
        self.collect_fields()
        return deepcopy(dict(family=self.family, values=self.values, raw=self.raw_edits,
                             automatic=self.automatic_edits))

    def project_changed(self, group=None):
        if not hasattr(self, 'document') or not self.project_alive or self.project_restoring or self.building:
            return
        snapshot = self.project_snapshot()
        if hasattr(self, 'interference'):self.interference.changed(snapshot)
        if hasattr(self, 'combination_search'):self.combination_search.changed(snapshot)
        if hasattr(self, 'components'):self.components.changed(snapshot)
        if hasattr(self, 'gear_measurement'):self.gear_measurement.changed(snapshot)
        if hasattr(self, 'backlash'):self.backlash.changed(snapshot)
        if self.document.record(snapshot, group):
            self.undo_reset.set_visible(False)
            self.update_document()

    def project_reconcile_token(self):
        if not hasattr(self, 'document') or not self.project_alive or self.project_restoring:
            return None
        return self.document.token if equivalent(self.project_snapshot(), self.document.current) else None

    def reconcile_project(self, token):
        if token is not None and self.document.token == token:
            if self.document.reconcile(self.project_snapshot()):
                self.update_document()

    def settle_project(self):
        # Commit adjustments before a dialog captures its revision token. Later
        # focus loss must not apply the same numeric edit after that snapshot.
        # The numeric binder preserves invalid and incomplete entry text.
        for widget in tuple(self.inputs.values()):
            if widget.get_sensitive():
                widget.update()
        self.project_changed()
        self.refresh()

    def update_document(self):
        if not self.project_alive:
            return
        d = self.document
        name = d.path.name if d.path else 'Untitled'
        self.project_title.set_text('RatioLab · '+name)
        self.win.set_title(f'{"• " if d.dirty else ""}{name} — RatioLab')
        self.undo_button.set_sensitive(d.index > 0 and not self.busy)
        self.redo_button.set_sensitive(d.index+1 < len(d.states) and not self.busy)
        self.recovery_error = None
        try:
            self.project_store.checkpoint(d)
        except (OSError, ValueError) as error:
            self.recovery_error = str(error)
            self.status_text(f'Session recovery could not be updated: {error}')
        label = f'{"Unsaved changes · " if d.dirty else "Saved · " if d.path else ""}{d.path or "Untitled · not saved"}'
        if self.recovery_error:
            label += ' · Recovery unavailable'
        self.document_label.set_text(label)
        self.document_label.set_tooltip_text(self.recovery_error or (str(d.path) if d.path else 'New parameter configuration'))

    def restore_project_snapshot(self, snapshot):
        if hasattr(self, 'components'):self.components.invalidate()
        if hasattr(self, 'gear_measurement'):self.gear_measurement.invalidate()
        if hasattr(self, 'backlash'):self.backlash.invalidate()
        if hasattr(self, 'interference'):self.interference.invalidate('Document replaced · run a new check')
        if hasattr(self, 'combination_search'):self.combination_search.invalidate('Document replaced · run a new search')
        self.project_restoring = True
        try:
            self.family = snapshot['family']
            self.values = deepcopy(snapshot['values'])
            self.raw_edits = deepcopy(snapshot['raw'])
            self.automatic_edits = deepcopy(snapshot.get('automatic', {}))
            self.building = True
            self.selector.set_selected(list(FAMILIES).index(self.family))
            self.make_fields()
        finally:
            self.building = False
            self.project_restoring = False

    def restore_raw_fields(self):
        automatic = set(getattr(self, 'automatic_edits', {}).get(self.family, []))
        for key, value in getattr(self, 'raw_edits', {}).get(self.family, {}).items():
            if key in self.inputs and self.inputs[key].get_sensitive():
                widget = self.inputs[key]
                if key in automatic:
                    try:
                        number = float(value.strip().replace(',', '.'))
                        if isfinite(number):
                            set_numeric_value(widget, number)
                            continue
                    except ValueError:
                        pass
                widget.set_text(value)
            elif key == 'input_rpm' and hasattr(self, 'motion_rpm'):
                self.motion_rate_editing = key not in automatic
                try:
                    number = float(value.strip().replace(',', '.'))
                    low, high = self.motion_rate_limits
                    if not isfinite(number) or not low <= number <= high:
                        raise ValueError('Input speed is outside its allowed range.')
                    if key in automatic:
                        set_numeric_value(self.motion_speed_text, number)
                    else:
                        self.motion_speed_text.set_text(value)
                    self.motion_rpm = number
                except ValueError:
                    self.motion_speed_text.set_text(value)
                    self.motion_rate_editing = True
                    self.motion_input_invalid = True
                    self.motion_rate_error.set_text('Complete a valid input speed.')
                    self.motion_rate_error.set_visible(True)

    def undo_project(self, *args):
        if self.busy:
            return
        self.project_changed()
        self.undo_reset.set_visible(False)
        self.restore_project_snapshot(self.document.undo())
        self.update_document()

    def redo_project(self, *args):
        if self.busy:
            return
        self.project_changed()
        self.undo_reset.set_visible(False)
        self.restore_project_snapshot(self.document.redo())
        self.update_document()

    def config(self):
        # Generation validates finite numbers, enum choices and geometric constraints.
        values = self.read_values()
        checked = generate(self.family, values)
        return dict(format='solidcraft-riduttori/1', family=self.family, parameters=checked.values)

    def checked_config(self, obj):
        if not isinstance(obj, dict) or obj.get('format') != 'solidcraft-riduttori/1':
            raise ValueError('Unknown configuration format')
        family = obj.get('family')
        if family not in FAMILIES:
            raise ValueError('Unsupported reducer: '+str(family))
        if not isinstance(obj.get('parameters'), dict):
            raise ValueError('Configuration parameters must be an object')
        return generate(family, obj['parameters'])

    def load_config_data(self, obj, path=None):
        checked = self.checked_config(obj)
        old = self.project_snapshot() if hasattr(self, 'document') else None
        snapshot = dict(family=checked.family, values={checked.family: checked.values}, raw={})
        try:
            self.restore_project_snapshot(snapshot)
        except Exception:
            if old:
                self.restore_project_snapshot(old)
            raise
        self.document = Document(self.project_snapshot(), path)
        if hasattr(self,'components') and self.design:self.components.refreshed(self.design)
        if hasattr(self,'gear_measurement') and self.design:self.gear_measurement.refreshed(self.design)
        if hasattr(self,'backlash') and self.design:self.backlash.refreshed(self.design)
        self.update_document()
        if path:
            self.remember_project(path)

    def remember_project(self, path):
        try:
            self.project_store.remember(path)
        except OSError as error:
            self.status_text(f'Project ready; recent files could not be updated: {error}')

    def current_answer(self, token):
        # Record any uncommitted widget edit before comparing a dialog's token.
        # Equal saved parameters cannot make a reply from another revision current.
        self.project_changed()
        if not self.project_alive or self.document.token != token or self.busy:
            self.status_text('The document changed while the dialog was open. Please try again.')
            return False
        return True

    def message_dialog(self, title, detail, choices, callback):
        dialog = Gtk.MessageDialog(transient_for=self.win, modal=True, text=title,
                                   secondary_text=detail)
        for label, code in choices:
            dialog.add_button(label, code)
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        self.project_dialog = dialog
        def response(widget, code):
            self.project_dialog = None
            widget.destroy()
            callback(code)
        dialog.connect('response', response)
        dialog.present()
        return dialog

    def protect_document(self, continuation, cancelled=None):
        if self.busy or self.project_dialog:
            self.status_text('Finish the current operation before replacing or closing the project.')
            if cancelled:cancelled()
            return
        self.settle_project()
        self.document.barrier()
        token = self.document.token
        if not self.document.dirty:
            continuation()
            return
        def answer(code):
            if not self.current_answer(token):
                if cancelled:cancelled()
                return
            if code == Gtk.ResponseType.REJECT:
                continuation()
            elif code == Gtk.ResponseType.ACCEPT:
                self.save_project(after=continuation, cancelled=cancelled)
            elif cancelled:cancelled()
        self.message_dialog('Save changes to this project?',
            'Save the current configuration, discard its edits, or cancel to keep working.',
            [('Cancel', Gtk.ResponseType.CANCEL), ('Discard', Gtk.ResponseType.REJECT),
             ('Save', Gtk.ResponseType.ACCEPT)], answer)

    def new_project(self, *args):
        self.protect_document(lambda: self.load_config_data(dict(
            format='solidcraft-riduttori/1', family='parallel', parameters=defaults('parallel'))))

    def close_project(self, *args):
        if getattr(self, 'closing_project', False):
            return False
        self.protect_document(self.finish_close_project)
        return True

    def finish_close_project(self, before_close=None):
        """Finish an accepted close without asking Save/Discard a second time.

        The updater's fast handoff runs only after recovery can be cleared.
        Its caller must use protect_document before reaching this continuation.
        """
        if not self.project_alive or self.busy or self.project_dialog:
            return False
        try:
            self.project_store.session.unlink(missing_ok=True)
        except OSError as error:
            self.status_text(f'Could not clear session recovery: {error}')
            return False
        try:
            if before_close is not None:before_close()
            self.closing_project = True
            self.win.close()
            if self.win.get_visible():
                raise RuntimeError('The project window could not be closed')
        except Exception:
            self.closing_project = False
            self.update_document()
            raise
        return True

    def save_dialog(self, *args):
        self.save_project()

    def save_config(self, *args):
        self.save_project()

    def save_as_dialog(self, *args):
        self.save_project(save_as=True)

    def save_project(self, save_as=False, after=None, path=None, cancelled=None):
        if self.busy or self.project_dialog:
            if cancelled:cancelled()
            return
        self.settle_project()
        self.document.barrier()
        token = self.document.token
        try:
            config = self.config()
        except Exception as error:
            self.status_text(f'Configuration could not be saved: {error}')
            if cancelled:cancelled()
            return
        def write(path):
            if not path or not self.current_answer(token):
                if cancelled:cancelled()
                return
            try:
                atomic_json(path, config)
            except (OSError, ValueError) as error:
                self.status_text(f'Configuration could not be saved: {error}')
                if cancelled:cancelled()
                return
            self.document.mark_saved(path)
            self.update_document()
            self.status_text(f'Configuration saved: {path}')
            self.remember_project(path)
            if after:
                after()
            return True
        if path is not None:
            return write(Path(path).absolute())
        if self.document.path and not save_as:
            return write(self.document.path)
        dialog = Gtk.FileChooserNative(title='Save model configuration', transient_for=self.win,
            action=Gtk.FileChooserAction.SAVE, accept_label='Save', cancel_label='Cancel')
        path = self.document.path
        dialog.set_current_name(path.name if path else f'{self.family}.config.json')
        folder = path.parent if path else self.output_dir
        if folder.exists():
            dialog.set_current_folder(Gio.File.new_for_path(str(folder)))
        self.project_dialog = dialog
        def response(widget, code):
            self.project_dialog = None
            selected = widget.get_file() if code == Gtk.ResponseType.ACCEPT else None
            local = selected.get_path() if selected else None
            widget.destroy()
            if code == Gtk.ResponseType.ACCEPT:
                if local:
                    write(Path(local))
                else:
                    self.status_text('No local project file selected. The document is unchanged.')
                    if cancelled:cancelled()
            elif cancelled:cancelled()
        dialog.connect('response', response)
        dialog.show()

    def open_project_path(self, path, token=None):
        if self.busy or (token is not None and not self.current_answer(token)):
            return
        self.settle_project()
        try:
            obj = json.loads(Path(path).read_text(encoding='utf-8'))
            self.checked_config(obj)
        except (OSError, ValueError, TypeError, KeyError) as error:
            self.status_text(f'Configuration could not be loaded: {error}')
            return
        def replace():
            try:
                current = json.loads(Path(path).read_text(encoding='utf-8'))
                self.load_config_data(current, Path(path).absolute())
            except Exception as error:
                self.status_text(f'Configuration could not be loaded: {error}')
        self.protect_document(replace)

    def load_dialog(self, *args):
        if self.busy or self.project_dialog:
            return
        self.settle_project()
        token = self.document.token
        dialog = Gtk.FileChooserNative(title='Open reducer configuration', transient_for=self.win,
            action=Gtk.FileChooserAction.OPEN, accept_label='Open', cancel_label='Cancel')
        file_filter = Gtk.FileFilter()
        file_filter.set_name('JSON configurations')
        file_filter.add_pattern('*.json')
        dialog.add_filter(file_filter)
        self.project_dialog = dialog
        def response(widget, code):
            self.project_dialog = None
            selected = widget.get_file() if code == Gtk.ResponseType.ACCEPT else None
            local = selected.get_path() if selected else None
            widget.destroy()
            if code == Gtk.ResponseType.ACCEPT:
                if local:
                    self.open_project_path(local, token)
                else:
                    self.status_text('No local project file selected. The document is unchanged.')
        dialog.connect('response', response)
        dialog.show()

    def show_recent(self, *args):
        if self.busy or self.project_dialog:
            return
        paths = self.project_store.recent()
        from gi.repository import Pango
        popup = Gtk.Window(title='Recent projects', application=self, transient_for=self.win, modal=True,
                           default_width=560, default_height=420)
        popup.add_css_class('reducers')
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        popup.set_child(scroll)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                      margin_top=16, margin_bottom=16, margin_start=16, margin_end=16)
        scroll.set_child(box)
        if self.project_store.recent_error:
            box.append(Gtk.Label(label='Recent files could not be read: '+self.project_store.recent_error, wrap=True))
        elif not paths:
            box.append(Gtk.Label(label='No recent projects'))
        for path in paths:
            button = Gtk.Button()
            content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            content.append(Gtk.Label(label=Path(path).name+(' · Missing' if not Path(path).is_file() else ''),
                                     xalign=0, ellipsize=Pango.EllipsizeMode.MIDDLE, css_classes=['action-title']))
            content.append(Gtk.Label(label=path, xalign=0, max_width_chars=55,
                                     ellipsize=Pango.EllipsizeMode.MIDDLE, css_classes=['muted']))
            button.set_child(content)
            button.set_tooltip_text(path)
            button.connect('clicked', lambda _, p=path: (popup.destroy(), self.open_project_path(p)))
            box.append(button)
        popup.present()

    def offer_recovery(self):
        self.recovery_idle = 0
        if not self.project_alive or self.project_dialog or self.document.dirty:
            return False
        candidates = self.project_store.candidates()
        def next_record():
            if not candidates:
                return
            path = candidates.pop(0)
            try:
                recovered = self.project_store.read_recovery(path, FAMILIES)
                # Preflight options/UI construction is transactional during Restore.
                title = 'Recover an interrupted session?'
                detail = str(recovered.path or 'Untitled project')+'\nIncomplete numeric edits are included.'
                choices = [('Keep for later', Gtk.ResponseType.CANCEL), ('Discard recovery', Gtk.ResponseType.REJECT), ('Restore', Gtk.ResponseType.ACCEPT)]
            except (OSError, ValueError, TypeError, KeyError) as error:
                recovered = None
                title = 'A session recovery record cannot be read'
                detail = f'{path.name}\n{error}'
                choices = [('Keep for later', Gtk.ResponseType.CANCEL), ('Discard recovery', Gtk.ResponseType.REJECT)]
            token = self.document.token
            def answer(code):
                if not self.current_answer(token):
                    return
                try:
                    if code == Gtk.ResponseType.REJECT:
                        path.unlink()
                    elif code == Gtk.ResponseType.ACCEPT and recovered:
                        previous = self.document
                        snapshot = self.project_snapshot()
                        try:
                            self.restore_project_snapshot(recovered.current)
                            # Normalize layout-added defaults, retaining the original clean checkpoint.
                            recovered.states[recovered.index] = self.project_snapshot()
                            self.project_store.checkpoint(recovered)
                        except Exception:
                            self.restore_project_snapshot(snapshot)
                            self.document = previous
                            raise
                        self.document = recovered
                        if hasattr(self,'components') and self.design:self.components.refreshed(self.design)
                        if hasattr(self,'gear_measurement') and self.design:self.gear_measurement.refreshed(self.design)
                        if hasattr(self,'backlash') and self.design:self.backlash.refreshed(self.design)
                        self.update_document()
                        path.unlink()
                        self.status_text('Interrupted session restored. Review the parameters before saving.')
                        return
                except Exception as error:
                    self.status_text(f'Recovery could not be completed: {error}')
                next_record()
            self.message_dialog(title, detail, choices, answer)
        next_record()
        return False
