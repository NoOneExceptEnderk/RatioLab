# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Visual family selection. Browsing never changes the working document."""
from copy import deepcopy
from gi.repository import Gtk, Gdk, Pango
from geometry import FAMILIES, VARIANTS, defaults
from app_paths import resource_path
from ui_language import translate
import gui_workflow


def apply_selection(app, family, variant, options=None):
    if app.busy:
        return
    app.remember()
    values = deepcopy(app.values.get(family, defaults(family)))
    values.update(options or {})
    if variant is not None:
        values['variant'] = variant
    if family == 'double':
        values['double_style'] = variant
    if family == 'wolfrom' and variant == 'double' and values.get('double_style') == 'separated' and values.get('gap') == 0:
        values.pop('gap')
    if family == 'face' and variant == 'double_helical' and values.get('double_style') == 'separated' and values.get('gap', 0) <= 0:
        values['gap'] = max(values.get('module', 2), getattr(app, 'face_groove_draft', 4.))
        app.raw_edits.get(family, {}).pop('gap', None)
    if family == 'parallel':
        from parallel_multistage import VARIANTS as multistage
        if variant in multistage:
            values.update(bearing_mode='manual', hardware_mode='none')
    if family == app.family and values == app.values.get(family):
        return
    app.values[family] = values
    app.building = True
    app.selector.set_selected(list(FAMILIES).index(family))
    app.family = family
    app.building = False
    app.make_fields()


class Catalog:
    def __init__(self, app):
        self.app = app
        self.family = app.family
        self.variant = None
        self.extra = {}
        self.window = Gtk.Window(application=app, transient_for=app.win, modal=True,
                                 title='Model catalog', default_width=970, default_height=660,
                                 css_classes=['reducers', 'model-catalog'])
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for setter in (root.set_margin_start,root.set_margin_end,root.set_margin_top,root.set_margin_bottom):
            setter(18)
        self.window.set_child(root)
        header = Gtk.Box(spacing=12)
        header.append(Gtk.Label(label='Model catalog', xalign=0, hexpand=True, css_classes=['step-title']))
        close = Gtk.Button(label='×', tooltip_text='Close')
        close.connect('clicked',lambda *_: self.window.close())
        header.append(close)
        for setter in (header.set_margin_start,header.set_margin_end,header.set_margin_top,header.set_margin_bottom):setter(12)
        handle=Gtk.WindowHandle();handle.set_child(header);self.window.set_titlebar(handle)
        self.search = Gtk.SearchEntry(placeholder_text='Search models…', hexpand=True)
        root.append(self.search)
        self.empty=Gtk.Label(label='No matching models.',visible=False,css_classes=['muted'])
        root.append(self.empty)
        content = Gtk.Box(spacing=18, vexpand=True);root.append(content)
        scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True,
                                   hscrollbar_policy=Gtk.PolicyType.NEVER, min_content_width=380)
        content.append(scroll)
        self.grid = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,
                                min_children_per_line=3,max_children_per_line=3,homogeneous=True,
                                row_spacing=10,column_spacing=10, valign=Gtk.Align.START)
        scroll.set_child(self.grid)
        self.cards={}
        for family in FAMILIES:
            label=gui_workflow.CATALOG[family][0]
            card=Gtk.Button(css_classes=['catalog-card'])
            box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
            image=Gtk.Picture.new_for_filename(str(resource_path('model-catalog/'+family+'.png')))
            image.set_can_shrink(True);image.set_content_fit(Gtk.ContentFit.CONTAIN)
            image.set_size_request(-1,100);box.append(image)
            caption=Gtk.Label(label=label,wrap=True,wrap_mode=Pango.WrapMode.WORD_CHAR,
                              xalign=0,max_width_chars=20,width_chars=1)
            box.append(caption);card.set_child(box)
            card.connect('clicked',lambda _, key=family:self.choose(key))
            self.grid.insert(card,-1);self.cards[family]=card
        self.detail=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
        self.detail.set_size_request(260,-1)
        detailscroll=Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, min_content_width=260)
        detailscroll.set_hexpand(False)
        detailscroll.set_child(self.detail);content.append(detailscroll)
        footer=Gtk.Box(spacing=8)
        footer.append(Gtk.Label(label='Choose a model, then its variants.',xalign=0,hexpand=True,
                                wrap=True,css_classes=['muted']))
        cancel=Gtk.Button(label='Cancel');cancel.connect('clicked',lambda *_:self.window.close())
        footer.append(cancel)
        self.apply=Gtk.Button(label='Use model',css_classes=['primary'])
        self.apply.connect('clicked',self.commit);footer.append(self.apply);root.append(footer)
        self.search.connect('search-changed',lambda *_:self.filter())
        keys=Gtk.EventControllerKey()
        keys.connect('key-pressed',lambda _,key,*args:self.window.close() or True if key==Gdk.KEY_Escape else False)
        self.window.add_controller(keys)
        self.window.connect('close-request',lambda *_:self.closed())
        self.choose(self.family)

    def closed(self):
        self.app.model_catalog=None
        return False

    def filter(self):
        query=self.search.get_text().strip().casefold()
        language=self.app.language.language
        for family,card in self.cards.items():
            label,description=gui_workflow.CATALOG[family]
            card.get_parent().set_visible(query in (translate(label,language)+' '+label+' '+family+' '+description).casefold())
        self.empty.set_visible(not any(card.get_parent().get_visible() for card in self.cards.values()))

    def choose(self,family,variant=None):
        if family!=self.family or not self.extra:
            self.extra=deepcopy(self.app.values.get(family,defaults(family)))
        self.family=family
        variants=VARIANTS.get(family,{})
        self.variant=variant or self.app.values.get(family,{}).get('variant',next(iter(variants),None))
        child=self.detail.get_first_child()
        while child:
            following=child.get_next_sibling();self.detail.remove(child);child=following
        for key,card in self.cards.items():
            if key==family:card.add_css_class('selected')
            else:card.remove_css_class('selected')
        image=Gtk.Picture.new_for_filename(str(resource_path('model-catalog/'+family+'.png')))
        image.set_can_shrink(True);image.set_content_fit(Gtk.ContentFit.CONTAIN)
        image.set_size_request(-1,160);self.detail.append(image)
        label,description=gui_workflow.CATALOG[family]
        self.detail.append(Gtk.Label(label=label,xalign=0,wrap=True,max_width_chars=28,css_classes=['step-title']))
        self.detail.append(Gtk.Label(label=description,xalign=0,wrap=True,max_width_chars=28,css_classes=['muted']))
        if family=='parallel':
            from parallel_multistage import selectors
            specs=selectors(self.variant)
        else:
            specs=[dict(label='Variant',choices=[dict(value=k,label=v) for k,v in variants.items()],value=self.variant)] if variants else []
        self.selectors=[]
        if family=='differential':
            from differential_wrist import CONFIGURATIONS
            specs.append(dict(key='configuration',label='Configuration',value=self.extra.get('configuration','wrist'),choices=[dict(value=k,label=v) for k,v in CONFIGURATIONS.items()]))
        if family!='double' and self.variant in ('double','two_stage_double','three_stage_double','double_helical'):
            from geometry import DOUBLE_STYLES
            if family=='wolfrom':
                self.extra.setdefault('double_style','joined')
            specs.append(dict(key='double_style',label='Double helix construction',value=self.extra.get('double_style','joined'),choices=[dict(value=k,label=v) for k,v in DOUBLE_STYLES.items()]))
        for spec in specs:
            self.detail.append(Gtk.Label(label=spec['label'],xalign=0,css_classes=['field-label']))
            control=gui_workflow.choice_dropdown([c['label'] for c in spec['choices']])
            keys=[c['value'] for c in spec['choices']]
            control.set_selected(keys.index(spec['value']))
            def changed(widget,_,keys=keys,key=spec.get('key','variant')):
                value=keys[widget.get_selected()]
                if key in ('configuration','double_style'):
                    self.extra[key]=value
                    self.choose(self.family,self.variant)
                else:self.choose(self.family,value)
            control.connect('notify::selected',changed)
            self.detail.append(control);self.selectors.append(control)
        if not specs:self.detail.append(Gtk.Label(label='Standard',xalign=0,css_classes=['muted']))
        self.app.language.refresh()

    def commit(self,*_):
        apply_selection(self.app,self.family,self.variant,{key:value for key,value in self.extra.items() if key in ('configuration','double_style')})
        self.window.close()


def show(app):
    if app.busy:return
    current=getattr(app,'model_catalog',None)
    if current is None:
        current=app.model_catalog=Catalog(app)
    current.window.present()
    current.search.grab_focus()


def sync_header(app, values=None):
    family=list(FAMILIES)[app.selector.get_selected()]
    values=values if values is not None else app.values.get(family,defaults(family))
    variant=values.get('variant',next(iter(VARIANTS.get(family,{})),None))
    parts=[]
    if family=='parallel':
        from parallel_multistage import selectors
        count=3 if variant.startswith('three_stage') else 2 if variant.startswith('two_stage') else 1
        teeth=selectors(variant)[1]
        parts=[f"{count} {'stage' if count==1 else 'stages'}",next(c['label'] for c in teeth['choices'] if c['value']==variant)]
    elif variant is not None:
        parts=[VARIANTS[family][variant]]
    if 'configuration' in values and family=='differential':
        from differential_wrist import CONFIGURATIONS
        parts.append(CONFIGURATIONS[values['configuration']])
    if family!='double' and variant in ('double','two_stage_double','three_stage_double','double_helical'):
        from geometry import DOUBLE_STYLES
        parts.append(DOUBLE_STYLES[values.get('double_style','joined')])
    app.catalog_caption.set_text(gui_workflow.CATALOG[family][0])
    app.catalog_summary.set_text(' · '.join(parts) or 'Standard')
    # PNG textures use GDK's native decoder, including in the frozen runtime.
    # GdkPixbuf's external glycin loader configuration may be absent there.
    app.catalog_picture.set_paintable(Gdk.Texture.new_from_filename(str(resource_path('model-catalog/'+family+'.png'))))
    app.catalog_button.set_sensitive(app.selector.get_sensitive())


def install(app,container):
    # Keep the canonical selection model for project/history restore and existing
    # consumers; the visible control opens the visual catalog instead.
    app.selector.set_visible(False)
    app.catalog_button=Gtk.Button(css_classes=['catalog-opener'])
    box=Gtk.Box(spacing=9)
    # Keep the same 50 x 44 frame in every language; the picture's aspect
    # ratio must not compete with the translated caption for header width.
    frame=Gtk.Overlay(css_classes=['catalog-thumbnail'],valign=Gtk.Align.CENTER)
    frame.set_size_request(50,44)
    app.catalog_picture=Gtk.Picture(can_shrink=True,content_fit=Gtk.ContentFit.CONTAIN)
    frame.add_overlay(app.catalog_picture)
    box.append(frame)
    copy=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4,hexpand=True)
    app.catalog_caption=Gtk.Label(xalign=0,hexpand=True,wrap=True,width_chars=1,
                                 wrap_mode=Pango.WrapMode.WORD_CHAR,css_classes=['catalog-name'])
    app.catalog_summary=Gtk.Label(xalign=0,wrap=True,width_chars=1,wrap_mode=Pango.WrapMode.WORD_CHAR,css_classes=['catalog-summary'])
    copy.append(app.catalog_caption);copy.append(app.catalog_summary)
    box.append(copy)
    from workspace_ui import workspace_glyph
    symbol=Gtk.Box(valign=Gtk.Align.CENTER,css_classes=['catalog-grid-symbol'])
    glyph=workspace_glyph('layout-grid',symbol)
    glyph.set_content_width(15);glyph.set_content_height(15)
    symbol.append(glyph);box.append(symbol)
    app.catalog_button.set_child(box)
    app.model_dimensions_heading=app.catalog_caption
    from parameter_help_ui import controller
    binding=controller(app).bind_section(app.catalog_caption,copy,control=app.catalog_button)
    app.model_dimensions_heading_row=binding.row
    binding.row.remove(binding.button)
    container.append(app.catalog_button)
    app.catalog_button.set_tooltip_text(None)
    app.catalog_button.connect('clicked',lambda *_:show(app))
    def sync(*_):sync_header(app)
    app.selector.connect('notify::selected',sync)
    app.selector.connect('notify::sensitive',sync)
    sync()
