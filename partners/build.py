"""Build the Partners hub and partner detail pages for lifeonwalls.co.uk.

The site renders each page from a self-contained HTML block (header, page body,
footer and init script). This script reuses the live site's shared chrome from
src/ and writes one ready-to-paste HTML file per page into dist/.
"""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).parent
SRC = ROOT / "src"
DIST = ROOT / "dist"
DIST.mkdir(exist_ok=True)

SITE = "https://lifeonwalls.co.uk"
UP = SITE + "/wp-content/uploads"
PARTNERS_URL = SITE + "/partners/"
EVERGREEN_URL = SITE + "/partners/evergreen-exterior-services/"
ILO_URL = SITE + "/partners/ilo-bloom/"

# ---------------------------------------------------------------- shared chrome
top = (SRC / "top.html").read_text()
foot = (SRC / "foot.html").read_text()
init = (SRC / "init-slim.js.html").read_text()
track = (SRC / "track.js.html").read_text().strip()

top = top.replace("lh-jectwestin-", "lh-prtnr-")
foot = foot.replace("lh-jectwestin-", "lh-prtnr-")

NAV_LINK = "color:#12160F;font-size:13.5px;letter-spacing:.09em;text-transform:uppercase"
desk_partners = (
    f'<span data-menu><a class="lh-prtnr-nav" href="{PARTNERS_URL}" style="{NAV_LINK}">Partners</a>'
    f'<span data-submenu><span><a href="{EVERGREEN_URL}">Evergreen Exterior Services</a>'
    f'<a href="{ILO_URL}">Ilo Bloom</a></span></span></span>'
)
MOB_LINK = "font-family:var(--d);font-size:clamp(34px,7vw,64px);font-weight:300;color:#12160F;line-height:1.15"
mob_partners = (
    f'<a href="{PARTNERS_URL}" style="{MOB_LINK}">Partners</a>'
    f'<span data-subnav><a href="{EVERGREEN_URL}">Evergreen Exterior Services</a>'
    f'<a href="{ILO_URL}">Ilo Bloom</a></span>'
)
FOOT_PARTNERS = f'<a href="{PARTNERS_URL}" style="color:#3A4034;font-size:15px">Partners</a>'


def insert_after(text, needle, addition):
    assert text.count(needle) == 1, (needle, text.count(needle))
    return text.replace(needle, needle + "\n" + addition)


top = insert_after(top, 'text-transform:uppercase">Projects</a>', desk_partners)
top = insert_after(top, 'line-height:1.15">Projects</a>', mob_partners)
foot = insert_after(foot, 'font-size:15px">Portfolio</a>', FOOT_PARTNERS)
# hover colour for the new nav item, matching the other top-level links
top = top.replace("</style>", ".low-root .lh-prtnr-nav:hover{color:#3F4E0A!important}</style>", 1)

FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Newsreader:ital,opsz,wght@0,6..72,300;0,6..72,400;'
    '0,6..72,500;1,6..72,300&family=Archivo:wght@400;500;600&display=swap" rel="stylesheet">'
)
LIBS = (
    '<script defer src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js"></script>'
    '<script defer src="https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/ScrollTrigger.min.js"></script>'
)

# ---------------------------------------------------------------- UI helpers
EYEBROW = "display:flex;align-items:center;gap:14px;font-size:12px;letter-spacing:.24em;text-transform:uppercase"
BTN = ("display:inline-flex;align-items:center;gap:12px;padding:17px 28px;background:#9BB222;color:#0B0F0B;"
       "border-radius:999px;font-size:13px;letter-spacing:.1em;text-transform:uppercase;font-weight:600")
BTN_GHOST = ("display:inline-flex;align-items:center;gap:12px;padding:16px 26px;border:1px solid currentColor;color:inherit;"
             "border-radius:999px;font-size:13px;letter-spacing:.1em;text-transform:uppercase;font-weight:600")
WRAP = "max-width:1500px;margin:0 auto;padding:clamp(70px,9vw,130px) clamp(18px,4vw,56px)"
H2 = "font-family:var(--d);font-weight:300;font-size:clamp(30px,4.2vw,64px);line-height:1.06;letter-spacing:-.015em;max-width:24ch;text-wrap:pretty"
H3 = "font-family:var(--d);font-size:24px;font-weight:400;margin-bottom:10px;line-height:1.2"
BODY = "color:#3A4034;max-width:62ch;text-wrap:pretty"

EXTRA_CSS = """<style>
.low-root .prt-btn:hover{background:#C6DE4E!important}
.low-root .prt-ghost:hover{background:#9BB222!important;border-color:#9BB222!important;color:#0B0F0B!important}
.low-root .prt-card{transition:transform .5s cubic-bezier(.2,.7,.2,1),box-shadow .5s ease}
.low-root .prt-card:hover{transform:translateY(-4px);box-shadow:0 24px 60px rgba(11,15,11,.12)}
.low-root .prt-card img{transition:transform 1.2s cubic-bezier(.2,.7,.2,1)}
.low-root .prt-card:hover img{transform:scale(1.04)}
.low-root .prt-more:hover{color:#12160F!important}
.low-root .prt-faq summary{justify-content:space-between;gap:20px;padding:22px 0;font-family:var(--d);font-size:clamp(19px,1.6vw,24px);line-height:1.3}
.low-root .prt-faq summary::after{content:'+';font-family:var(--t);font-size:26px;font-weight:300;color:#3F4E0A;transition:transform .25s ease;flex:0 0 auto}
.low-root .prt-faq details[open] summary::after{transform:rotate(45deg)}
.low-root .prt-gal{display:grid;grid-template-columns:repeat(12,1fr);gap:clamp(10px,1.2vw,18px)}
.low-root .prt-gal figure{grid-column:span 12;overflow:hidden;background:#EDF1E3}
.low-root .prt-gal img{width:100%;height:100%;object-fit:cover}
@media (min-width:760px){.low-root .prt-gal .g-w{grid-column:span 8}.low-root .prt-gal .g-n{grid-column:span 4}.low-root .prt-gal .g-h{grid-column:span 6}}
.low-root .prt-facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,220px),1fr));border-top:1px solid var(--line)}
.low-root .prt-facts > div{padding:22px 0;border-bottom:1px solid var(--line)}
@media (min-width:760px){.low-root .prt-facts > div{padding:24px 24px 24px 0}}
</style>"""


def eyebrow(text, colour="#3F4E0A", line="#9BB222"):
    return (f'<p data-fade style="{EYEBROW};color:{colour}"><span style="display:inline-block;width:38px;'
            f'height:1px;background:{line}"></span>{text}</p>')


def breadcrumb(items):
    parts = []
    for name, url in items:
        if url:
            parts.append(f'<a href="{url}" style="color:#B4B7AC">{name}</a>')
        else:
            parts.append(f'<span aria-current="page">{name}</span>')
    sep = ' <span style="color:#9BB222">/</span> '
    return (f'<nav aria-label="Breadcrumb" data-fade style="font-size:11.5px;letter-spacing:.16em;'
            f'text-transform:uppercase;color:#B4B7AC">{sep.join(parts)}</nav>')


def img(src, alt, w, h, eager=False, style="width:100%;height:100%;object-fit:cover"):
    load = 'fetchpriority="high" decoding="async"' if eager else 'loading="lazy" decoding="async"'
    return f'<img {load} src="{src}" alt="{alt}" width="{w}" height="{h}" style="{style}" />'


def hero(crumbs, kicker, h1, sub, lede, image, ctas):
    src, alt, w, h = image
    btns = "".join(ctas)
    return f"""<section data-screen-label="Hero" style="color:#F2F1EA;position:relative;min-height:min(88svh,760px);display:flex;align-items:flex-end;overflow:hidden;isolation:isolate;background:#0B0F0B">
<div data-parallax style="position:absolute;inset:-10% 0;z-index:-2">{img(src, alt, w, h, eager=True)}</div>
<div style="position:absolute;inset:0;z-index:-1;background:linear-gradient(180deg,rgba(11,15,11,.78) 0%,rgba(11,15,11,.48) 40%,rgba(11,15,11,.93) 100%)"></div>
<div style="max-width:1500px;margin:0 auto;width:100%;padding:clamp(130px,18vh,220px) clamp(18px,4vw,56px) clamp(40px,5vw,70px);display:flex;flex-direction:column;gap:clamp(18px,2.4vw,30px)">
{breadcrumb(crumbs)}
{eyebrow(kicker, "#C6DE4E")}
<h1 data-split style="font-family:var(--d);font-weight:300;font-size:clamp(38px,6.6vw,104px);line-height:1;letter-spacing:-.02em;max-width:19ch;text-wrap:balance">{h1}</h1>
<p data-fade style="font-family:var(--d);font-weight:300;font-size:clamp(20px,2.1vw,31px);line-height:1.22;letter-spacing:-.01em;max-width:36ch;text-wrap:pretty">{sub}</p>
<p data-fade style="font-size:clamp(16px,1.2vw,19px);color:#DDDED7;max-width:56ch;text-wrap:pretty">{lede}</p>
<div data-fade style="display:flex;flex-wrap:wrap;gap:12px;margin-top:6px">{btns}</div>
</div>
</section>"""


def faq_section(num, faqs, bg="#FFFFFF"):
    items = "".join(
        f'<details style="border-bottom:1px solid var(--line)"><summary>{q}</summary>'
        f'<p style="{BODY};padding:0 0 24px">{a}</p></details>'
        for q, a in faqs
    )
    return f"""<section data-screen-label="FAQ" style="background:{bg};border-top:1px solid var(--line)">
<div style="{WRAP};display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,380px),1fr));gap:clamp(30px,5vw,90px)">
<div>{eyebrow(f"{num} — Questions")}<h2 data-split style="{H2};margin-top:clamp(20px,2.5vw,34px)">Frequently asked questions</h2></div>
<div class="prt-faq" data-fade style="border-top:1px solid var(--line)">{items}</div>
</div>
</section>"""


def cta_band(heading, text, buttons):
    return f"""<section data-screen-label="Next step" style="background:#0B0F0B;color:#F2F1EA">
<div style="{WRAP};display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,380px),1fr));gap:clamp(28px,4vw,70px);align-items:end">
<div>{eyebrow("Next step", "#C6DE4E")}<h2 data-split style="{H2};margin-top:clamp(20px,2.5vw,34px)">{heading}</h2></div>
<div data-fade style="display:grid;gap:26px"><p style="color:#DDDED7;max-width:52ch;text-wrap:pretty">{text}</p>
<div style="display:flex;flex-wrap:wrap;gap:12px">{"".join(buttons)}</div></div>
</div>
</section>"""


def btn(href, label, ghost=False, external=False):
    rel = ' target="_blank" rel="noopener"' if external else ""
    if ghost:
        return f'<a class="prt-ghost" href="{href}"{rel} style="{BTN_GHOST}">{label}</a>'
    return f'<a class="prt-btn" href="{href}"{rel} style="{BTN}">{label}</a>'


def schema(graph):
    return ('<script type="application/ld+json">'
            + json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False)
            + "</script>")


def crumbs_schema(items):
    return {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": n, "item": u}
            for i, (n, u) in enumerate(items)
        ],
    }


def faq_schema(url, faqs):
    strip = lambda s: re.sub(r"<[^>]+>", "", s)
    return {
        "@type": "FAQPage",
        "@id": url + "#faq",
        "mainEntity": [
            {"@type": "Question", "name": strip(q),
             "acceptedAnswer": {"@type": "Answer", "text": strip(a)}}
            for q, a in faqs
        ],
    }


LOW_ORG = {"@type": "Organization", "@id": SITE + "/#organization", "name": "Life on Walls", "url": SITE + "/"}


def page(body, graph):
    return ("<!-- wp:html -->\n" + schema(graph) + FONTS + top.split("<header", 1)[0].replace(
        "</style>", "</style>" + EXTRA_CSS, 1) + "<header" + top.split("<header", 1)[1]
            + '<main id="main">' + body + "</main>" + foot + LIBS + init + "\n" + track + "\n<!-- /wp:html -->\n")


# ---------------------------------------------------------------- images
EV = {
    "hero": (f"{UP}/2026/11/evergreen-living-louvres-display-banstead.jpg",
             "Life on Walls Living Louvres display at Evergreen Exterior Services nursery in Banstead, Surrey, with a planted vertical wall, banner and slatted louvre panels", 1600, 1200),
    "wide": (f"{UP}/2026/11/living-wall-stand-evergreen-nursery-glasshouse.jpg",
             "Wide view of the Life on Walls living wall stand inside the Evergreen nursery glasshouse, with Living Louvres, a planted vertical wall and potted rosemary", 1600, 1200),
    "louvre": (f"{UP}/2026/11/living-louvres-planted-close-up-evergreen.jpg",
               "Close-up of Life on Walls Living Louvres planted with trailing and red-leaved plants beneath the steel Life on Walls logo", 1200, 1600),
    "planting": (f"{UP}/2026/11/life-on-walls-team-planting-living-louvres-evergreen.jpg",
                 "Life on Walls team planting up the Living Louvres display at Evergreen Exterior Services nursery, Banstead", 1600, 1200),
    "team": (f"{UP}/2026/11/life-on-walls-team-evergreen-exterior-services.jpg",
             "Two Life on Walls team members in front of the planted living wall stand at Evergreen Exterior Services", 1600, 1200),
    "demo": (f"{UP}/2026/11/life-on-walls-living-wall-demonstration-evergreen.jpg",
             "Life on Walls presenting the living wall display to trade visitors at Evergreen Exterior Services, Banstead", 1200, 1600),
    "y2025": (f"{UP}/2026/11/life-on-walls-living-wall-display-evergreen-2025.jpg",
              "Life on Walls living wall display at Evergreen in 2025, with a fern wall, black planter pockets on a slatted panel and a Bespoke Living Wall Solutions banner", 2000, 1710),
    "olive": (f"{UP}/2026/11/evergreen-nursery-specimen-olive-tree.jpg",
              "Cloud-pruned specimen olive tree with banana plants and shrubs under the glasshouse roof at Evergreen nursery", 2000, 1500),
    "trees": (f"{UP}/2026/11/evergreen-nursery-specimen-trees-shrubs.jpg",
              "Multi-stem specimen tree with hydrangeas and clipped shrubs in pots at Evergreen nursery", 1500, 2000),
}
ILO = {
    "hero": (f"{UP}/2026/04/Indoor-living-wall-smeg.jpg",
             "Indoor living wall designed and installed by Life on Walls", 1600, 1200),
    "detail": (f"{UP}/2026/05/L1_PHOTO-2024-06-07-10-56-39.jpg",
               "Established living wall planting by Life on Walls showing a mix of foliage textures", 1200, 1600),
}


def fig(image, cls, ratio):
    src, alt, w, h = image
    return f'<figure class="{cls}" data-fade style="aspect-ratio:{ratio}">{img(src, alt, w, h)}</figure>'


def two_col(num, label, heading, paras, aside="", bg="#FFFFFF", sid=""):
    ps = "".join(f'<p style="{BODY}">{p}</p>' for p in paras)
    sid_attr = f' id="{sid}"' if sid else ""
    return f"""<section{sid_attr} data-screen-label="{label}" style="background:{bg};border-top:1px solid var(--line)">
<div style="{WRAP};display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,380px),1fr));gap:clamp(30px,5vw,90px);align-items:start">
<div>{eyebrow(f"{num} — {label}")}<h2 data-split style="{H2};margin-top:clamp(20px,2.5vw,34px)">{heading}</h2></div>
<div data-fade style="display:grid;gap:20px;padding-top:clamp(0px,1vw,10px)">{ps}{aside}</div>
</div>
</section>"""


def facts(rows):
    cells = "".join(
        f'<div><span style="display:block;font-size:11.5px;letter-spacing:.18em;text-transform:uppercase;color:#3F4E0A;margin-bottom:8px">{k}</span>'
        f'<span style="display:block;font-family:var(--d);font-size:21px;line-height:1.3">{v}</span></div>'
        for k, v in rows
    )
    return f'<div class="prt-facts" data-fade>{cells}</div>'


def visit(num, label, heading, name, address_lines, text, buttons, map_q, bg="#EDF1E3"):
    addr = "<br>".join(address_lines)
    return f"""<section data-screen-label="{label}" style="background:{bg};border-top:1px solid var(--line)">
<div style="{WRAP};display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,380px),1fr));gap:clamp(30px,5vw,90px);align-items:start">
<div>{eyebrow(f"{num} — {label}")}<h2 data-split style="{H2};margin-top:clamp(20px,2.5vw,34px)">{heading}</h2></div>
<div data-fade style="display:grid;gap:26px">
<address style="font-style:normal;border-top:1px solid var(--line);padding-top:22px"><strong style="display:block;font-family:var(--d)!important;font-size:26px;font-weight:400;margin-bottom:8px">{name}</strong><span style="font-size:18px;line-height:1.6;color:#3A4034">{addr}</span><br><a href="https://www.google.com/maps/search/?api=1&amp;query={map_q}" target="_blank" rel="noopener" class="prt-more" style="display:inline-block;margin-top:10px;font-size:13px;letter-spacing:.1em;text-transform:uppercase;font-weight:600">Get directions →</a></address>
<p style="{BODY}">{text}</p>
<div style="display:flex;flex-wrap:wrap;gap:12px">{"".join(buttons)}</div>
</div>
</div>
</section>"""


def related(current):
    other = {"evergreen": ("Ilo Bloom", ILO_URL, "Plant wholesaler · New Covent Garden Flower Market, London"),
             "ilo": ("Evergreen Exterior Services", EVERGREEN_URL, "Wholesale plant nursery · Banstead, Surrey")}[current]
    return f"""<section data-screen-label="More partners" style="border-top:1px solid var(--line)">
<div style="max-width:1500px;margin:0 auto;padding:clamp(40px,5vw,70px) clamp(18px,4vw,56px);display:flex;flex-wrap:wrap;gap:20px;align-items:center;justify-content:space-between">
<p style="font-size:12px;letter-spacing:.22em;text-transform:uppercase;color:#3F4E0A">Also in our partner network</p>
<a href="{other[1]}" class="prt-more" style="display:grid;gap:4px;text-align:right"><span style="font-family:var(--d);font-size:clamp(24px,2.6vw,38px);line-height:1.1">{other[0]} →</span><span style="font-size:14px;color:#5A6055">{other[2]}</span></a>
<a href="{PARTNERS_URL}" class="prt-more" style="font-size:13px;letter-spacing:.1em;text-transform:uppercase;font-weight:600">← All partners</a>
</div>
</section>"""


# ================================================================ HUB PAGE
hub_crumbs = [("Home", SITE + "/"), ("Partners", None)]
hub_faqs = [
    ("Who are Life on Walls’ partners?",
     "Life on Walls currently partners with two UK plant wholesalers: <a href=\"" + EVERGREEN_URL + "\">Evergreen Exterior Services</a>, "
     "a wholesale plant nursery in Banstead, Surrey, and <a href=\"" + ILO_URL + "\">Ilo Bloom</a>, a specialist plant wholesaler "
     "at New Covent Garden Flower Market in London."),
    ("Why does Life on Walls partner with plant wholesalers?",
     "Plant wholesalers already supply the landscape professionals, garden designers, contractors and retailers who specify greening. "
     "Partnering with them brings Life on Walls’ modular living wall systems, such as Living Louvres, to those customers alongside "
     "the plants they already buy, making vertical greening more accessible."),
    ("Where can I see Life on Walls products through a partner?",
     "Evergreen Exterior Services is introducing selected Life on Walls products, including Living Louvres, to its trade offering at its "
     "nursery in Banstead, Surrey. Ilo Bloom works with Life on Walls from New Covent Garden Flower Market in London."),
    ("Can my business become a Life on Walls partner?",
     "Yes. Life on Walls welcomes conversations with nurseries, plant wholesalers, landscapers and other horticultural businesses. "
     "<a href=\"" + SITE + "/contact-us/\">Get in touch with the team</a> to discuss a partnership."),
]


def partner_card(n, name, url, place, kind, summary, image):
    src, alt, w, h = image
    return f"""<article class="prt-card" data-fade style="background:#FFFFFF;border:1px solid var(--line);display:flex;flex-direction:column">
<a href="{url}" aria-hidden="true" tabindex="-1" style="display:block;overflow:hidden;aspect-ratio:4/3">{img(src, alt, w, h)}</a>
<div style="padding:clamp(22px,2.6vw,38px);display:flex;flex-direction:column;gap:14px;flex:1">
<p style="font-size:11.5px;letter-spacing:.18em;text-transform:uppercase;color:#3F4E0A">0{n} · {kind}</p>
<h3 style="font-family:var(--d);font-weight:300;font-size:clamp(30px,3vw,46px);line-height:1.05;letter-spacing:-.01em"><a href="{url}" style="color:#12160F">{name}</a></h3>
<p style="font-size:14px;letter-spacing:.04em;color:#5A6055">{place}</p>
<p style="{BODY}">{summary}</p>
<a href="{url}" class="prt-more" aria-label="Learn more about {name}" style="margin-top:auto;padding-top:10px;display:inline-flex;align-items:center;gap:10px;font-size:13px;letter-spacing:.1em;text-transform:uppercase;font-weight:600">Learn more <span aria-hidden="true">→</span></a>
</div>
</article>"""


hub_body = hero(
    hub_crumbs,
    "Partners &amp; suppliers · UK",
    "Living wall partners &amp; suppliers",
    "Working with leading UK plant wholesalers to bring living walls to more projects.",
    "Life on Walls partners with established horticultural businesses so that landscape professionals, garden designers, "
    "contractors and retailers can discover modular living wall systems, including Living Louvres, alongside the plants they already source.",
    EV["wide"],
    [btn("#our-partners", "Meet our partners"), btn(SITE + "/contact-us/", "Become a partner", ghost=True)],
) + f"""
<section id="our-partners" data-screen-label="Our partners" style="background:#EDF1E3;border-top:1px solid var(--line)">
<div style="{WRAP}">
<div style="display:flex;flex-wrap:wrap;align-items:end;justify-content:space-between;gap:24px;margin-bottom:clamp(36px,5vw,70px)">
<div>{eyebrow("01 — Our partners")}<h2 data-split style="{H2};margin-top:clamp(20px,2.5vw,34px)">Two partners, one aim: more greening in more places.</h2></div>
<p data-fade style="{BODY};max-width:44ch">Our partners combine horticultural expertise and trade networks with our living wall technology.</p>
</div>
<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:clamp(18px,2.4vw,34px)">
{partner_card(1, "Evergreen Exterior Services", EVERGREEN_URL, "Banstead, Surrey", "Wholesale plant nursery",
              "An established wholesale plant nursery, founded in 1986, supplying trees, shrubs, climbers, grasses, perennials and specimen plants to trade customers across the UK. Evergreen is introducing selected Life on Walls products, including Living Louvres, to its offering.",
              EV["hero"])}
{partner_card(2, "Ilo Bloom", ILO_URL, "New Covent Garden Flower Market, London", "Plant wholesaler",
              "A specialist plant wholesaler at New Covent Garden Flower Market, known for its approachable team, fresh plant selections and industry knowledge. Together we help professionals bring planting into indoor and outdoor spaces.",
              ILO["hero"])}
</div>
</div>
</section>
""" + two_col(
    "02", "Why we partner", "Making vertical greening more accessible.",
    [
        "Living walls work best when the right plants, the right system and the right advice come together. Our partners are trusted "
        "sources of plants for the people who design and build gardens, terraces and commercial spaces.",
        "By working with them, Life on Walls can introduce its modular living wall systems, such as "
        f"<a href=\"{SITE}/living-wall-systems/\">Living Louvres</a>, to more landscape professionals, while our partners offer their "
        "customers practical, innovative ways to add greenery to vertical surfaces.",
    ],
    aside=facts([("Partners", "2 UK plant wholesalers"), ("Regions", "Surrey &amp; London, supplying nationwide"),
                 ("Featured system", "Living Louvres")]),
) + faq_section("03", hub_faqs) + cta_band(
    "Interested in partnering with Life on Walls?",
    "We work with nurseries, wholesalers and horticultural businesses that share our passion for long-lasting, well-engineered greening. "
    "Tell us about your business and we will be in touch.",
    [btn(SITE + "/contact-us/", "Talk to our team"), btn(SITE + "/living-wall-supplier/", "Explore system supply", ghost=True)],
)

hub_graph = [
    {"@type": "CollectionPage", "@id": PARTNERS_URL + "#webpage", "url": PARTNERS_URL,
     "name": "Living Wall Partners & Suppliers UK", "isPartOf": {"@id": SITE + "/#website"},
     "about": LOW_ORG, "breadcrumb": {"@id": PARTNERS_URL + "#breadcrumb"},
     "primaryImageOfPage": {"@type": "ImageObject", "url": EV["wide"][0]},
     "mainEntity": {"@type": "ItemList", "itemListElement": [
         {"@type": "ListItem", "position": 1, "url": EVERGREEN_URL, "name": "Evergreen Exterior Services"},
         {"@type": "ListItem", "position": 2, "url": ILO_URL, "name": "Ilo Bloom"}]}},
    dict(crumbs_schema([("Home", SITE + "/"), ("Partners", PARTNERS_URL)]), **{"@id": PARTNERS_URL + "#breadcrumb"}),
    faq_schema(PARTNERS_URL, hub_faqs),
]

# ================================================================ EVERGREEN
ev_crumbs = [("Home", SITE + "/"), ("Partners", PARTNERS_URL), ("Evergreen Exterior Services", None)]
ev_faqs = [
    ("Who is Evergreen Exterior Services?",
     "Evergreen Exterior Services is a wholesale plant nursery based at 21 Croydon Lane, Banstead, Surrey. Established in 1986, it supplies "
     "trees, shrubs, climbers, grasses, perennials and specimen plants to landscape professionals, garden designers, contractors and garden centres across the UK."),
    ("What is the partnership between Life on Walls and Evergreen?",
     "Through the partnership, Evergreen is introducing selected Life on Walls products to its offering. It brings together Evergreen’s "
     "horticultural knowledge and trade network with Life on Walls’ living wall technology, to make vertical greening more accessible to landscape professionals."),
    ("Which Life on Walls products are available through Evergreen?",
     "The partnership showcases selected <a href=\"" + SITE + "/living-wall-systems/\">Living Louvres</a> products, a modular planted louvre system "
     "for adding greenery to gardens, terraces, commercial spaces and other projects. Contact Evergreen or Life on Walls for current availability."),
    ("Where is Evergreen Exterior Services located?",
     "Evergreen’s main nursery is at 21 Croydon Lane, Banstead, Surrey SM7 3BW. It also runs a delivery network serving trade customers nationwide."),
]
ev_body = hero(
    ev_crumbs,
    "Partner · Wholesale plant nursery · Banstead, Surrey",
    "Evergreen Exterior Services",
    "Bringing living wall innovation to the landscaping industry.",
    "Life on Walls is pleased to partner with Evergreen Exterior Services, an established wholesale plant nursery based in Banstead, Surrey, "
    "with a strong reputation for horticultural expertise, plant sourcing and trade supply.",
    EV["hero"],
    [btn("https://www.evergreenext.co.uk/", "Visit Evergreen’s website", external=True),
     btn("#visit", "Find the nursery", ghost=True)],
) + two_col(
    "01", "Overview", "Innovative living wall systems for trade customers.",
    [
        "With a strong reputation for horticultural expertise, plant sourcing and trade supply, Evergreen supports landscape professionals, "
        "garden designers, contractors and garden centres across the UK.",
        "Through our partnership, Evergreen is introducing selected Life on Walls products to its offering, giving trade customers more "
        "opportunities to incorporate innovative, modular living wall systems into their projects.",
    ],
    aside=facts([("Established", "1986"), ("Location", "Banstead, Surrey"), ("Type", "Wholesale plant nursery"),
                 ("Serves", "Trade customers nationwide")]),
) + f"""
<section data-screen-label="Gallery" aria-label="Life on Walls at Evergreen gallery" style="border-top:1px solid var(--line)">
<div style="max-width:1500px;margin:0 auto;padding:clamp(40px,5vw,70px) clamp(18px,4vw,56px)">
<div class="prt-gal">
{fig(EV["planting"], "g-w", "4/3")}{fig(EV["louvre"], "g-n", "3/4")}
{fig(EV["team"], "g-h", "4/3")}{fig(EV["y2025"], "g-h", "4/3")}
</div>
</div>
</section>
""" + two_col(
    "02", "About Evergreen", "A broad plant range, delivered nationwide.",
    [
        "Established in 1986, Evergreen Exterior Services supplies an extensive selection of plants, including trees, shrubs, climbers, "
        "grasses, perennials and specimen plants.",
        "Operating from its main nursery in Banstead, Evergreen combines a broad plant range with a dedicated delivery network serving trade "
        "customers nationwide.",
    ],
    aside=f'<div class="prt-gal">{fig(EV["olive"], "g-h", "4/3")}{fig(EV["trees"], "g-h", "4/3")}</div>',
    bg="#EDF1E3",
) + two_col(
    "03", "Our partnership", "Horticultural knowledge meets living wall technology.",
    [
        "By combining Evergreen’s horticultural knowledge and established trade network with Life on Walls’ innovative living wall technology, "
        "we aim to make vertical greening more accessible to landscape professionals.",
        f"The partnership will showcase selected <a href=\"{SITE}/living-wall-systems/\">Living Louvres</a> products, helping customers explore "
        "practical solutions for incorporating greenery into gardens, terraces, commercial spaces and other projects.",
    ],
    aside=f'<div class="prt-gal">{fig(EV["demo"], "g-h", "3/4")}{fig(EV["hero"], "g-h", "3/4")}</div>',
) + visit(
    "04", "Visit Evergreen", "Visit the nursery in Banstead.", "Evergreen Exterior Services",
    ["21 Croydon Lane", "Banstead, Surrey", "SM7 3BW"],
    "Discover Evergreen’s plant range, trade services and more information about the nursery.",
    [btn("https://www.evergreenext.co.uk/", "Visit Evergreen’s website", external=True),
     btn(SITE + "/contact-us/", "Ask Life on Walls", ghost=True)],
    "Evergreen+Exterior+Services%2C+21+Croydon+Lane%2C+Banstead+SM7+3BW",
).replace('<section data-screen-label="Visit Evergreen"', '<section id="visit" data-screen-label="Visit Evergreen"') \
    + faq_section("05", ev_faqs) + related("evergreen")

ev_graph = [
    {"@type": "WebPage", "@id": EVERGREEN_URL + "#webpage", "url": EVERGREEN_URL,
     "name": "Evergreen Exterior Services | Life on Walls Partner", "isPartOf": {"@id": SITE + "/#website"},
     "breadcrumb": {"@id": EVERGREEN_URL + "#breadcrumb"}, "about": {"@id": EVERGREEN_URL + "#partner"},
     "primaryImageOfPage": {"@type": "ImageObject", "url": EV["hero"][0], "caption": EV["hero"][1]}},
    {"@type": ["LocalBusiness", "WholesaleStore"], "@id": EVERGREEN_URL + "#partner", "name": "Evergreen Exterior Services",
     "description": "Wholesale plant nursery established in 1986, supplying trees, shrubs, climbers, grasses, perennials and specimen plants to trade customers across the UK.",
     "url": "https://www.evergreenext.co.uk/", "foundingDate": "1986", "image": EV["olive"][0],
     "address": {"@type": "PostalAddress", "streetAddress": "21 Croydon Lane", "addressLocality": "Banstead",
                 "addressRegion": "Surrey", "postalCode": "SM7 3BW", "addressCountry": "GB"},
     "areaServed": {"@type": "Country", "name": "United Kingdom"},
     "knowsAbout": ["Trees", "Shrubs", "Climbers", "Grasses", "Perennials", "Specimen plants"]},
    dict(crumbs_schema([("Home", SITE + "/"), ("Partners", PARTNERS_URL), ("Evergreen Exterior Services", EVERGREEN_URL)]),
         **{"@id": EVERGREEN_URL + "#breadcrumb"}),
    faq_schema(EVERGREEN_URL, ev_faqs),
]

# ================================================================ ILO BLOOM
ilo_crumbs = [("Home", SITE + "/"), ("Partners", PARTNERS_URL), ("Ilo Bloom", None)]
ilo_faqs = [
    ("Who is Ilo Bloom?",
     "Ilo Bloom is a specialist plant wholesaler based at New Covent Garden Flower Market, London SW8 5EH. It offers a wide range of plants "
     "to the horticultural trade and supports designers, retailers and other horticultural professionals."),
    ("What is the partnership between Life on Walls and Ilo Bloom?",
     "The partnership brings together Ilo Bloom’s expertise in plants and growing substrates with Life on Walls’ modular living wall technology, "
     "to make living wall solutions more accessible to professionals integrating planting into indoor and outdoor spaces."),
    ("Where is Ilo Bloom based?",
     "Ilo Bloom is based at New Covent Garden Flower Market, London SW8 5EH."),
    ("How can I buy from Ilo Bloom?",
     "You can explore Ilo Bloom’s plant offering through its <a href=\"https://iloshop.onflorisoft.cloud/\" target=\"_blank\" rel=\"noopener\">online shop</a> "
     "and follow its latest selections on <a href=\"https://www.instagram.com/ilobloom/\" target=\"_blank\" rel=\"noopener\">Instagram</a>."),
]
ilo_body = hero(
    ilo_crumbs,
    "Partner · Plant wholesaler · New Covent Garden Flower Market, London",
    "Ilo Bloom",
    "Bringing plants and living walls together.",
    "Life on Walls is delighted to partner with Ilo Bloom, a specialist plant wholesaler based at New Covent Garden Flower Market in London.",
    ILO["hero"],
    [btn("https://iloshop.onflorisoft.cloud/", "Explore Ilo Bloom’s online shop", external=True),
     btn("https://www.instagram.com/ilobloom/", "Follow on Instagram", ghost=True, external=True)],
) + two_col(
    "01", "Overview", "Quality plants, a friendly approach.",
    [
        "With a passion for plants, an experienced team and a friendly approach to wholesale supply, Ilo Bloom supports designers, retailers "
        "and other horticultural professionals in finding quality plants for their projects.",
        "Our partnership brings together Ilo Bloom’s plant expertise and Life on Walls’ innovative living wall systems, helping customers "
        "discover new possibilities for vertical greening.",
    ],
    aside=facts([("Location", "New Covent Garden Flower Market"), ("Type", "Plant wholesaler"),
                 ("Serves", "Designers, retailers &amp; horticultural professionals")]),
) + two_col(
    "02", "About Ilo Bloom", "Fresh selections from London’s flower market.",
    [
        "Based at London’s New Covent Garden Flower Market, Ilo Bloom offers a wide range of plants to the horticultural trade.",
        "Known for its approachable team, fresh plant selections and industry knowledge, Ilo Bloom helps customers source plants for creative "
        "and commercial projects.",
    ],
    bg="#EDF1E3",
) + two_col(
    "03", "Our partnership", "Plants, substrates and modular living walls.",
    [
        "Together, Life on Walls and Ilo Bloom aim to make living wall solutions more accessible to professionals looking to integrate planting "
        "into indoor and outdoor spaces.",
        f"The collaboration combines Ilo Bloom’s expertise in plants and growing substrates with Life on Walls’ modular "
        f"<a href=\"{SITE}/living-wall-systems/\">living wall technology</a>, supporting practical, creative and sustainable greening solutions.",
    ],
    aside=f'<div class="prt-gal">{fig(ILO["detail"], "g-f", "4/3")}</div>',
) + visit(
    "04", "Discover Ilo Bloom", "Find Ilo Bloom at New Covent Garden.", "Ilo Bloom",
    ["New Covent Garden Flower Market", "London", "SW8 5EH"],
    "Explore their plant offering and learn more about their business.",
    [btn("https://iloshop.onflorisoft.cloud/", "Explore Ilo Bloom’s online shop", external=True),
     btn("https://www.instagram.com/ilobloom/", "Follow Ilo Bloom on Instagram", ghost=True, external=True)],
    "New+Covent+Garden+Flower+Market%2C+London+SW8+5EH",
) + faq_section("05", ilo_faqs) + related("ilo")

ilo_graph = [
    {"@type": "WebPage", "@id": ILO_URL + "#webpage", "url": ILO_URL, "name": "Ilo Bloom | Life on Walls Partner",
     "isPartOf": {"@id": SITE + "/#website"}, "breadcrumb": {"@id": ILO_URL + "#breadcrumb"},
     "about": {"@id": ILO_URL + "#partner"}},
    {"@type": ["LocalBusiness", "WholesaleStore"], "@id": ILO_URL + "#partner", "name": "Ilo Bloom",
     "description": "Specialist plant wholesaler at New Covent Garden Flower Market, London, supplying plants to designers, retailers and horticultural professionals.",
     "url": "https://iloshop.onflorisoft.cloud/", "sameAs": ["https://www.instagram.com/ilobloom/"],
     "address": {"@type": "PostalAddress", "streetAddress": "New Covent Garden Flower Market", "addressLocality": "London",
                 "postalCode": "SW8 5EH", "addressCountry": "GB"}},
    dict(crumbs_schema([("Home", SITE + "/"), ("Partners", PARTNERS_URL), ("Ilo Bloom", ILO_URL)]),
         **{"@id": ILO_URL + "#breadcrumb"}),
    faq_schema(ILO_URL, ilo_faqs),
]

# ---------------------------------------------------------------- write
for name, body, graph in [("partners", hub_body, hub_graph), ("evergreen-exterior-services", ev_body, ev_graph),
                          ("ilo-bloom", ilo_body, ilo_graph)]:
    html = page(body, graph)
    assert html.count("<h1") == 1
    (DIST / f"{name}.html").write_text(html)
    print(name, len(html))

# nav snippets for updating existing pages
(DIST / "nav-desktop.html").write_text(desk_partners)
(DIST / "nav-mobile.html").write_text(mob_partners)
(DIST / "nav-footer.html").write_text(FOOT_PARTNERS)
