import unittest

from app.service.email_text import html_to_text


class TestHtmlToText(unittest.TestCase):
    def test_a_link_keeps_its_address(self):
        text = html_to_text(
            '<p>Open <a href="https://d.example/x">the dataset</a> now.</p>'
        )

        self.assertEqual(text, "Open the dataset (https://d.example/x) now.")

    def test_a_link_whose_label_is_its_address_is_written_once(self):
        text = html_to_text('<a href="https://d.example/x">https://d.example/x</a>')

        self.assertEqual(text, "https://d.example/x")

    def test_rows_and_breaks_become_lines_and_whitespace_collapses(self):
        html = "<table><tr><td>  First   line </td></tr><tr><td>Second<br>Third</td></tr></table>"

        self.assertEqual(html_to_text(html), "First line\nSecond\nThird")

    def test_head_style_and_hidden_preheader_are_left_out(self):
        html = (
            '<html><head><title>Subject</title><meta charset="utf-8"><style>a{color:red}</style></head>'
            '<body><span style="display:none!important;">preheader &#8199;&#847;</span>'
            "<p>Body</p></body></html>"
        )

        self.assertEqual(html_to_text(html), "Body")

    def test_entities_are_decoded(self):
        self.assertEqual(
            html_to_text("<p>A&nbsp;&amp;&nbsp;B &middot; C</p>"), "A & B · C"
        )

    def test_blank_lines_never_pile_up(self):
        html = "<p>One</p><p></p><p></p><p>Two</p>"

        self.assertEqual(html_to_text(html), "One\n\nTwo")
