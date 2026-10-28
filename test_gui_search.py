"""Exercise the actual GTK popup filter and its selection mapping (needs a display)."""
import unittest
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk
from gui_workflow import CATALOG, searchable_dropdown
from printed_shaft import DESIGNS


def descendants(widget):
    yield widget
    child = widget.get_first_child()
    while child:
        yield from descendants(child)
        child = child.get_next_sibling()


class SearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # GTK can report successful initialization even when the sandbox cannot
        # connect to a display. Constructing widgets then crashes in libgtk.
        if not Gtk.init_check() or Gdk.Display.get_default() is None:
            raise unittest.SkipTest('GTK display required')

    def make_dropdown(self, labels):
        dropdown = searchable_dropdown(labels)
        window = Gtk.Window()
        window.set_child(dropdown)
        self.addCleanup(window.destroy)
        widgets = list(descendants(dropdown))
        search = next(w for w in widgets if isinstance(w, Gtk.SearchEntry))
        results = next(w for w in widgets if isinstance(w, Gtk.ListView))
        return dropdown, search, results

    def search(self, entry, results, query):
        entry.set_text(query)
        entry.emit('search-changed')
        model = results.get_model()
        return [model.get_item(i).get_string() for i in range(model.get_n_items())]

    def test_model_search_and_selection_use_original_indices(self):
        labels = [row[0] for row in CATALOG.values()]
        dropdown, search, results = self.make_dropdown(labels)
        dropdown.set_selected(0)
        self.assertEqual(self.search(search, results, 'SHAFT'), ['Parallel shaft reducer'])
        self.assertEqual(dropdown.get_selected(), 0)
        results.emit('activate', 0)
        self.assertEqual(dropdown.get_selected(), labels.index('Parallel shaft reducer'))

    def test_construction_search_matches_details_and_clears(self):
        labels = list(DESIGNS.values())
        dropdown, search, results = self.make_dropdown(labels)
        self.assertEqual(self.search(search, results, 'THROUGH BOLTS'), [DESIGNS['fdm_bolted']])
        self.assertEqual(self.search(search, results, 'separate'), [DESIGNS['standard']])
        self.assertEqual(self.search(search, results, 'no such construction'), [])
        self.assertEqual(self.search(search, results, ''), labels)

    def test_repeated_search_and_unicode_custom_names(self):
        dropdown, search, results = self.make_dropdown(['Riduttore · qualità speciale', 'Cycloidal'])
        self.assertEqual(self.search(search, results, 'QUALITÀ'), ['Riduttore · qualità speciale'])
        self.assertEqual(self.search(search, results, 'cycloidal'), ['Cycloidal'])
        self.assertEqual(self.search(search, results, 'speciale'), ['Riduttore · qualità speciale'])


if __name__ == '__main__':
    unittest.main()
