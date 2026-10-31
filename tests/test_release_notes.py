# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Release history is readable plain text without development sections or links."""
import unittest
from release_notes import MAX_NOTES, plain_text


class ReleaseNotesTests(unittest.TestCase):
    def test_local_history_hides_nonempty_unreleased_and_keeps_numbered_versions(self):
        source = '''# Changelog
Repository introduction.
## [Unreleased]
### Added
- Future feature.
## [0.1.13] — 2026-10-31
### Added
- **Published** changes on a
  wrapped line with `code`.
## 0.1.12
- Older changes.
'''
        text = plain_text(source, history=True)
        self.assertNotIn('Unreleased', text)
        self.assertNotIn('Future', text)
        self.assertNotIn('Repository', text)
        self.assertIn('0.1.13', text)
        self.assertIn('• Published changes on a wrapped line with code.', text)
        self.assertIn('0.1.12', text)
        self.assertNotIn('##', text)

    def test_published_notes_render_bullets_links_tables_and_code_as_plain_text(self):
        text = plain_text('''## Fixed
- [Update](javascript:alert) and **restart**.
- <b>Keep safe</b> &amp; readable.
| Platform | Action |
| --- | --- |
| Linux | Update |
```
some command
```
''')
        self.assertIn('• Update and restart.', text)
        self.assertNotIn('javascript:', text)
        self.assertNotIn('<b>', text)
        self.assertIn('Keep safe & readable.', text)
        self.assertIn('Platform · Action', text)
        self.assertNotIn('|', text)
        self.assertNotIn('```', text)
        self.assertIn('some command', text)

    def test_unreleased_link_section_and_nested_headings_never_reach_notes(self):
        text = plain_text('''## [Unreleased](https://example.test)
secret
### Fixed
secret too
## Released
visible
''')
        self.assertEqual(text, 'Released\n\nvisible')

    def test_input_is_bounded_and_invalid_values_are_empty(self):
        self.assertEqual(plain_text(None), '')
        self.assertNotIn('outside bound', plain_text('a'*MAX_NOTES+'outside bound'))
        self.assertEqual(plain_text('## Unreleased\nfuture', history=True), '')


if __name__ == '__main__':
    unittest.main()
