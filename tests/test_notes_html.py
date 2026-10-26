import importlib.util
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / 'app'
spec = importlib.util.spec_from_file_location('notes_html', APP / 'notes-html.py')
notes_html = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notes_html)


def item(description):
    """The appcast item make-app.sh writes, with the notes in it."""
    return ET.fromstring('<rss xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle"><channel><item>'
                         f'<description><![CDATA[{description}]]></description></item></channel></rss>')


class NotesHtmlTest(unittest.TestCase):
    def test_renders_headings_bullets_and_inline_code(self):
        out = notes_html.render('---\nbig: true\n---\n- One `runway init` line.\n- **Bold** <b>raw</b>\n\n'
                                '### Hands off\n- Stats.\nA paragraph.\n', '0.2.0')
        self.assertNotIn('big: true', out)
        self.assertIn('<h2>Runway 0.2.0</h2>', out)
        self.assertIn('<li>One <code>runway init</code> line.</li>', out)
        self.assertIn('<li><strong>Bold</strong> &lt;b&gt;raw&lt;/b&gt;</li>', out)   # tags in notes are text
        self.assertIn('<h3>Hands off</h3>', out)
        self.assertIn('<p>A paragraph.</p>', out)
        self.assertEqual(out.count('<ul>'), out.count('</ul>'))
        self.assertIn('prefers-color-scheme: dark', out)

    def test_never_breaks_out_of_the_cdata(self):
        out = notes_html.render('- odd ]]> text')
        self.assertNotIn(']]>', out)
        self.assertIn('odd', item(out).find('.//description').text)

    def test_every_repo_note_makes_a_valid_feed_item(self):
        files = sorted((APP / 'release-notes').glob('*.md'))
        self.assertTrue(files)
        for f in files:
            out = notes_html.render(f.read_text(), f.stem)
            desc = item(out).find('.//description').text
            self.assertIn(f'Runway {f.stem}', desc)
            self.assertIn('<li>', desc)


if __name__ == '__main__':
    unittest.main()
