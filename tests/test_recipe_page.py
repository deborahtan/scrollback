from scrollback.collectors import recipe_page

JSONLD = """<html><head><title>Best Tantanmen</title>
<script type="application/ld+json">{"@context":"https://schema.org","@graph":[
 {"@type":"WebPage","name":"x"},
 {"@type":["Recipe"],"name":"Tantanmen","recipeIngredient":["ramen noodles","tahini","pork mince"],
  "totalTime":"PT30M","recipeInstructions":[{"@type":"HowToStep","text":"Cook noodles."}]}
]}</script></head><body><p>Story...</p></body></html>"""

PLAIN = """<html><head><title>Cosy soup</title><style>p{}</style></head>
<body><nav>Menu</nav><p>Simmer daikon   with ginger.</p><script>var x=1;</script></body></html>"""


def test_prefers_structured_recipe():
    page = recipe_page.parse("https://e.com/r", JSONLD)
    assert page.title == "Best Tantanmen"
    assert page.recipe["name"] == "Tantanmen"
    assert "tahini" in page.recipe["recipeIngredient"]
    assert page.text_excerpt is None


def test_falls_back_to_clean_text():
    page = recipe_page.parse("https://e.com/s", PLAIN)
    assert page.recipe is None
    assert page.text_excerpt == "Simmer daikon with ginger."
