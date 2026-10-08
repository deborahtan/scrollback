"""Captures the page a pin links to, so the recipe survives if the site goes.

Prefers schema.org Recipe JSON-LD (most recipe sites publish it). Falls back to
the page title and a short plain-text excerpt.
"""

from __future__ import annotations

import json
from html.parser import HTMLParser

import httpx

from scrollback.models import LinkedPage

EXCERPT_CHARS = 4000
USER_AGENT = "Scrollback/0.1 (personal archive of saved links)"


def capture(http: httpx.Client, url: str) -> LinkedPage | None:
    try:
        resp = http.get(url, timeout=20, follow_redirects=True, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
    except httpx.HTTPError:
        return None
    if "html" not in resp.headers.get("content-type", ""):
        return LinkedPage(url=str(resp.url))
    return parse(str(resp.url), resp.text)


def parse(url: str, html: str) -> LinkedPage:
    parser = _PageParser()
    parser.feed(html)
    recipe = None
    for block in parser.json_ld:
        recipe = _find_recipe(block)
        if recipe:
            break
    excerpt = None
    if recipe is None:
        text = " ".join(" ".join(parser.text).split())
        excerpt = text[:EXCERPT_CHARS] or None
    return LinkedPage(url=url, title=parser.title or None, recipe=recipe, text_excerpt=excerpt)


def _find_recipe(node):
    if isinstance(node, list):
        for item in node:
            found = _find_recipe(item)
            if found:
                return found
    elif isinstance(node, dict):
        kind = node.get("@type")
        kinds = kind if isinstance(kind, list) else [kind]
        if "Recipe" in kinds:
            keep = (
                "name", "description", "recipeIngredient", "recipeInstructions",
                "totalTime", "prepTime", "cookTime", "recipeYield", "recipeCuisine",
                "recipeCategory", "keywords", "image",
            )
            return {k: node[k] for k in keep if k in node}
        if "@graph" in node:
            return _find_recipe(node["@graph"])
    return None


class _PageParser(HTMLParser):
    _SKIP = {"script", "style", "noscript", "nav", "footer", "header", "svg"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.text: list[str] = []
        self.json_ld: list = []
        self._stack: list[str] = []
        self._in_ld = False
        self._ld_buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        self._stack.append(tag)
        if tag == "script" and dict(attrs).get("type", "").lower() == "application/ld+json":
            self._in_ld = True
            self._ld_buf = []

    def handle_endtag(self, tag):
        if tag == "script" and self._in_ld:
            self._in_ld = False
            try:
                self.json_ld.append(json.loads("".join(self._ld_buf)))
            except ValueError:
                pass
        while self._stack:
            if self._stack.pop() == tag:
                break

    def handle_data(self, data):
        if self._in_ld:
            self._ld_buf.append(data)
            return
        if self._stack and self._stack[-1] == "title" and not self.title:
            self.title = data.strip()
            return
        if not any(t in self._SKIP for t in self._stack):
            self.text.append(data)
