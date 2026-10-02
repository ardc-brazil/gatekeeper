import re
from html.parser import HTMLParser

_SKIPPED = {"head", "title", "style", "script"}
_BLOCKS = {"div", "tr", "table", "br", "li", "ul", "ol"}
_PARAGRAPHS = {"p", "h1", "h2", "h3", "h4", "h5", "h6"}


class _Converter(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._skipped: list[str] = []
        self._hidden_tag: str | None = None
        self._hidden_depth = 0
        self._link_href: str | None = None
        self._link_text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if self._skipped:
            if tag in _SKIPPED:
                self._skipped.append(tag)
            return
        if tag in _SKIPPED:
            self._skipped.append(tag)
            return
        if self._hidden_tag is not None:
            if tag == self._hidden_tag:
                self._hidden_depth += 1
            return
        attributes = dict(attrs)
        if "display:none" in (attributes.get("style") or "").replace(" ", "").lower():
            self._hidden_tag, self._hidden_depth = tag, 1
            return
        if tag == "a":
            self._link_href = attributes.get("href")
            self._link_text = []
        elif tag in _PARAGRAPHS:
            self._parts.append("\n\n")
        elif tag in _BLOCKS:
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if self._skipped:
            if tag == self._skipped[-1]:
                self._skipped.pop()
            return
        if self._hidden_tag is not None:
            if tag == self._hidden_tag:
                self._hidden_depth -= 1
                if self._hidden_depth == 0:
                    self._hidden_tag = None
            return
        if tag == "a" and self._link_href is not None:
            label = " ".join("".join(self._link_text).split())
            href = self._link_href
            self._parts.append(
                href if not label or label == href else f"{label} ({href})"
            )
            self._link_href = None
        elif tag in _PARAGRAPHS:
            self._parts.append("\n\n")

    def handle_data(self, data):
        if self._skipped or self._hidden_tag is not None:
            return
        if self._link_href is not None:
            self._link_text.append(data)
        else:
            self._parts.append(data)

    def text(self) -> str:
        lines = [
            " ".join(line.split())
            for line in "".join(self._parts).replace("\xa0", " ").split("\n")
        ]
        return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def html_to_text(html: str) -> str:
    converter = _Converter()
    converter.feed(html)
    converter.close()
    return converter.text()
