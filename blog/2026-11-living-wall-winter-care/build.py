"""Build the 'living wall winter care' blog post body for lifeonwalls.co.uk.

Usage: python3 -I build.py <out_dir> [image_base_url]
Writes body.html (what goes inside <main id="main"> ... </main> of the
site's page template), head.html (JSON-LD + page-specific styles) and
meta.json (Yoast fields), plus motion.html (GSAP scroll motion,
appended straight after </article>). Copy text is from the client's Google Doc,
kept verbatim; only the summary, checklist, FAQ and schema are added.
"""
import json, sys, html

OUT = sys.argv[1]
IMG = sys.argv[2] if len(sys.argv) > 2 else 'https://lifeonwalls.co.uk/wp-content/uploads/2026/11/'
BASE = 'https://lifeonwalls.co.uk'
SLUG = 'living-wall-winter-care'
URL = f'{BASE}/{SLUG}/'
DATE = '2026-11-13'
TITLE = 'How to care for indoor and outdoor living walls in winter'
DESC = ('How to care for indoor and outdoor living walls in winter: evergreen planting, '
        'irrigation changes, frost protection, pruning, and light and humidity checks.')

img = {
    'hero':   ('outdoor-living-wall-soho-railway-arch.webp', 1800, 809,
               'Outdoor living wall by Life on Walls beneath a railway bridge in Soho, London'),
    'plants': ('outdoor-evergreen-living-wall-terapia.webp', 1200, 1600,
               'Evergreen outdoor living wall by Life on Walls on a grey clad building'),
    'water':  ('outdoor-living-wall-winter-foliage.webp', 1800, 809,
               'Outdoor living wall with mixed evergreen foliage beside a glazed entrance in late autumn'),
    'prune':  ('living-wall-winter-maintenance-visit.webp', 1122, 1402,
               'Life on Walls technician carrying out a pre-winter maintenance visit on an outdoor living wall'),
    'indoor': ('indoor-living-wall-staircase-shree-temple.webp', 1600, 1200,
               'Indoor living wall by Life on Walls beside a glass staircase at Shree Temple'),
}

e = html.escape
EYEBROW = 'font-size:12px;letter-spacing:.24em;text-transform:uppercase;color:#3F4E0A;margin-bottom:18px'
H2 = ('font-family:var(--d);font-weight:300;font-size:clamp(30px,4.2vw,60px);line-height:1.05;'
      'letter-spacing:-.015em;max-width:20ch;text-wrap:pretty;margin-bottom:clamp(24px,3vw,40px)')
H3 = ('font-family:var(--d);font-weight:400;font-size:clamp(24px,2.4vw,34px);line-height:1.15;'
      'margin:clamp(30px,4vw,50px) 0 16px')
P = 'color:#3A4034;max-width:66ch;text-wrap:pretty;margin-bottom:18px'
SEC = 'padding:clamp(60px,8vw,110px) clamp(18px,4vw,56px)'
ALT = 'border-top:1px solid rgba(63,78,10,.16);background:#EDF1E3;'
WRAP = 'max-width:1200px;margin:0 auto'
TWO = ('display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,340px),1fr));'
       'gap:clamp(30px,5vw,80px);align-items:start')
BTN1 = ('display:inline-flex;align-items:center;min-height:48px;padding:0 26px;background:#9BB222;'
        'color:#0B0F0B;border-radius:999px;font-size:13px;letter-spacing:.1em;text-transform:uppercase;font-weight:600')
BTN2 = ('display:inline-flex;align-items:center;min-height:48px;padding:0 26px;border:1px solid rgba(63,78,10,.22);'
        'color:#12160F;border-radius:999px;font-size:13px;letter-spacing:.1em;text-transform:uppercase;font-weight:600')
LINK = 'color:#3F4E0A;border-bottom:1px solid #9BB222'
P_FAQ = P.replace(';margin-bottom:18px', '') + ';margin:14px 0 0'
H2_CTA = H2.replace('margin-bottom:clamp(24px,3vw,40px)', 'margin-bottom:0')


def p(t): return f'<p data-fade style="{P}">{t}</p>'
def h3(t, id_=''): return f'<h3{f" id={chr(34)}{id_}{chr(34)}" if id_ else ""} data-fade style="{H3}">{t}</h3>'


def fig(key, cap, eager=False):
    f, w, h, alt = img[key]
    load = 'fetchpriority="high"' if eager else 'loading="lazy"'
    return (f'<figure data-reveal style="margin:0"><img {load} decoding="async" src="{IMG}{f}" alt="{e(alt)}" '
            f'width="{w}" height="{h}" style="width:100%;height:auto" />'
            f'<figcaption style="font-size:13px;color:#5A6055;margin-top:10px">{cap}</figcaption></figure>')


def plant_list(items):
    li = ''.join(
        f'<li style="border-top:1px solid rgba(63,78,10,.22);padding:14px 0;color:#3A4034">'
        f'<strong style="color:#12160F;font-weight:600">{n}</strong> {d}</li>' for n, d in items)
    return f'<ul data-stagger style="list-style:none;padding:0;margin:8px 0 0;max-width:66ch">{li}</ul>'


outdoor_plants = [
    ('<em>Euonymus japonicus</em> ‘Microphyllus Albovariegatus’', 'is a compact evergreen shrub with small, dark green leaves edged in creamy white. It suits full sun or partial shade.'),
    ('<em>Fatsia japonica</em>', 'brings large, glossy, deeply lobed leaves to sheltered planting schemes. Its spreading habit makes it a good choice where the design can accommodate its mature size.'),
    ('<em>Asplenium scolopendrium</em>, or hart’s tongue fern,', 'has arching, strap-shaped evergreen fronds that bring texture to sheltered, shady areas.'),
    ('<em>Carex elata</em> ‘Aurea’', 'adds movement and contrast with its arching, golden-yellow foliage. Consider it for parts of the wall where the growing medium stays reliably moist.'),
    ('<em>Erysimum</em> ‘Bowles’s Mauve’', 'brings upright clusters of mauve flowers and narrow, grey-green foliage. It suits a sunny, free-draining position and adds colour during its flowering season.'),
]
indoor_plants = [
    ('<em>Spathiphyllum</em> ‘Alana’, or peace lily,', 'combines glossy green foliage with white spathes and suits bright, filtered or indirect light.'),
    ('Heartleaf philodendron,', 'often sold as <em>Philodendron scandens</em>, has trailing stems and glossy, heart-shaped leaves that soften the edges of a wall. It suits bright, indirect light.'),
    ('<em>Scindapsus pictus</em>, or satin pothos,', 'adds silver markings and a trailing habit. Bright, indirect light helps show off its leaf pattern.'),
    ('<em>Aglaonema</em> ‘Maria’, or Chinese evergreen,', 'has compact growth and mint-green markings, making it an option for more shaded parts of an indoor scheme.'),
    ('<em>Asplenium nidus</em>, or bird’s nest fern,', 'adds structure with its upright rosette of broad, wavy fronds. Give it indirect light and a position away from drying airflow.'),
    ('<em>Adiantum raddianum</em>, or maidenhair fern,', 'brings fine-textured foliage to sheltered, humid areas. Position it away from heating vents and keep its growing medium evenly moist.'),
]

checklist = [
    ('Outdoor', 'Check moisture at several heights, then reduce irrigation frequency and duration as growth slows.'),
    ('Outdoor', 'Inspect taps, pipework, valves, connectors and timers before the first freeze; insulate or drain as the system requires.'),
    ('Outdoor', 'Remove dead or damaged material, clear drainage points and secure loose planting.'),
    ('Outdoor', 'Recheck the wall after storms or freezing weather.'),
    ('Indoor', 'Confirm grow lights cover the whole planting area and review their timing for shorter days.'),
    ('Indoor', 'Measure humidity close to the wall and keep plants away from radiators and heating vents.'),
    ('Indoor', 'Adjust watering and feeding to how actively the plants are growing.'),
]

faqs = [
    ('Do living walls need less water in winter?',
     'Outdoor living walls usually need less water in winter because cooler temperatures slow plant growth. Check the growing medium in several places before reducing irrigation, as wind-exposed upper sections can dry faster and walls under overhangs can stay dry even in wet weather. Indoor walls in warm, well-lit spaces may keep growing and need little change.'),
    ('How do you protect a living wall irrigation system from frost?',
     'Inspect outdoor taps, pipework, valves, connectors and timers before the first freeze, because water expands as it freezes and can damage them. Insulate exposed parts and, where the system requires it, drain or winterise vulnerable sections. Follow the instructions for the installed system and check for leaks after a cold spell.'),
    ('Which plants keep an outdoor living wall green in winter?',
     'Life on Walls generally aims for 90 to 95% evergreen planting on suitable outdoor walls. Reliable options include Euonymus japonicus ‘Microphyllus Albovariegatus’, Fatsia japonica, hart’s tongue fern (Asplenium scolopendrium) and Carex elata ‘Aurea’, chosen to suit the wall’s exposure, shade and moisture.'),
    ('Why do indoor living wall plants get brown leaf tips in winter?',
     'Brown or crispy tips are often caused by dry air from indoor heating, although there can be other causes. Check the growing medium first; if it is already moist, lightly mist the affected foliage once a week and move plants away from direct heat from radiators or vents.'),
    ('Should you prune a living wall before winter?',
     'Yes, selectively. A pre-winter visit is a good time to remove dead or damaged material, clear drainage points, check for loose planting and trim growth likely to catch the wind. Cut back herbaceous perennials only where the timing suits the species, and use a lighter touch on evergreen shrubs and ferns.'),
]

toc = [('outdoor', 'Outdoor living walls'), ('indoor', 'Indoor living walls'),
       ('checklist', 'Winter checklist'), ('faq', 'FAQ')]

body = f'''<article data-lswc>
<section data-hero data-screen-label="Hero" style="color:#F2F1EA;position:relative;min-height:min(80svh,700px);display:flex;align-items:flex-end;overflow:hidden;isolation:isolate;background:#0B0F0B">
  <div data-hero-media style="position:absolute;inset:0;z-index:-2"><img fetchpriority="high" decoding="async" src="{IMG}{img['hero'][0]}" alt="{e(img['hero'][3])}" width="1800" height="809" style="width:100%;height:100%;object-fit:cover" /></div>
  <div style="position:absolute;inset:0;z-index:-1;background:linear-gradient(180deg,rgba(11,15,11,.78) 0%,rgba(11,15,11,.5) 40%,rgba(11,15,11,.93) 100%)"></div>
  <div style="max-width:1500px;margin:0 auto;width:100%;padding:clamp(130px,18vh,220px) clamp(18px,4vw,56px) clamp(40px,5vw,70px);display:flex;flex-direction:column;gap:clamp(18px,2.4vw,28px)">
    <nav data-fade aria-label="Breadcrumb" style="font-size:11.5px;letter-spacing:.16em;text-transform:uppercase;color:#B4B7AC"><a href="{BASE}/" style="color:#B4B7AC">Home</a> <span style="color:#9BB222">/</span> <a href="{BASE}/blog/" style="color:#B4B7AC">Blog</a> <span style="color:#9BB222">/</span> Winter care</nav>
    <p data-fade style="display:flex;align-items:center;gap:14px;font-size:12px;letter-spacing:.24em;text-transform:uppercase;color:#C6DE4E"><span style="display:inline-block;width:38px;height:1px;background:#9BB222"></span>Maintenance · <time datetime="{DATE}">13 November 2026</time> · 5 min read</p>
    <h1 data-split style="font-family:var(--d);font-weight:300;font-size:clamp(36px,5.6vw,88px);line-height:1.02;letter-spacing:-.02em;max-width:20ch;text-wrap:balance">{TITLE}</h1>
    <p data-fade style="font-size:clamp(17px,1.35vw,21px);color:#DDDED7;max-width:60ch;text-wrap:pretty">Seasonal guidance from the Life on Walls maintenance team on planting, irrigation, frost protection, light and humidity.</p>
  </div>
</section>

<section id="summary" data-screen-label="Summary" style="{SEC}">
  <div style="{WRAP};{TWO}">
    <div>
      <p data-fade style="{EYEBROW}">In short</p>
      <p data-fade style="{P};font-size:clamp(18px,1.3vw,20px);color:#12160F">To care for a living wall in winter, check it before reacting. Outdoors, reduce irrigation as growth slows, protect exposed pipework and timers from frost, and clear drainage. Indoors, check that lighting still covers the wall, watch humidity near heating vents, and adjust watering and feeding to how actively the plants are growing.</p>
      {p('Winter brings changing conditions that affect how living walls grow and the care they need. Outdoors, cooler temperatures can slow plant growth and reduce water demand, while frost may pose a risk to exposed irrigation systems. Indoors, shorter daylight hours and dry air from heating can affect plant health, even when temperatures remain comfortable.')}
      {p('Whether indoors or outdoors, effective winter maintenance starts with understanding the conditions of your living wall. Regularly checking foliage, moisture levels in the growing medium, and irrigation and drainage systems can help identify potential issues early. For outdoor walls, pay particular attention to frost and exposure, while indoor installations may require adjustments to lighting and airflow. By observing how your living wall responds to seasonal changes, you can make small, targeted adjustments that help keep it healthy throughout winter.')}
    </div>
    <nav data-fade aria-label="On this page" style="background:#EDF1E3;border:1px solid rgba(63,78,10,.16);padding:clamp(24px,3vw,40px)">
      <p data-fade style="{EYEBROW}">On this page</p>
      <ol style="list-style:none;padding:0;display:grid;gap:12px">{''.join(f'<li><a href="#{a}" style="{LINK};font-size:16px">{t}</a></li>' for a, t in toc)}</ol>
      <p style="font-size:14px;color:#5A6055;margin-top:22px">By the Life on Walls maintenance team, who care for indoor and outdoor living walls across London and the UK.</p>
    </nav>
  </div>
</section>

<section id="outdoor" data-screen-label="Outdoor" style="{ALT}{SEC}">
  <div style="{WRAP}">
    <p data-fade style="{EYEBROW}">01 — Outdoor</p>
    <h2 data-split style="{H2}">Outdoor living walls</h2>
    <div style="{TWO}">
      <div>
        {h3('Choose plants for the wall’s microclimate').replace('margin:clamp(30px,4vw,50px) 0 16px', 'margin:0 0 16px')}
        {p('At Life on Walls, we generally aim for 90-95% evergreen planting in suitable outdoor designs to retain foliage through winter. Hardiness is a separate consideration. A sheltered courtyard and an exposed façade can call for different planting, even on the same site. When choosing plants, consider local minimum temperatures, wind exposure, shade, and how much rain actually reaches the wall.')}
        {p('These plants offer different textures, colours, and forms, depending on the conditions:')}
        {plant_list(outdoor_plants)}
      </div>
      {fig('plants', 'Mostly evergreen planting keeps an outdoor living wall full through winter.')}
    </div>

    {h3('Adjust irrigation to the weather')}
    {p('As temperatures drop and growth slows, an outdoor wall will often need less water. Check the growing medium in several places before reducing irrigation. An upper section exposed to wind may dry faster than the planting below, and a wall beneath an overhang can stay surprisingly dry during a wet spell.')}
    {p(f'Adjust the frequency and duration of watering to suit the wall. Use the plants, recent weather, and moisture readings or checks to guide the schedule. Revisit the settings after sustained rain, a dry spell, or a significant change in temperature. Our article on <a href="{BASE}/the-landscaper-make-living-walls-waterwise/" style="{LINK}">waterwise living walls</a> covers irrigation design in more depth.')}
    <div style="margin:clamp(24px,3vw,40px) 0">{fig('water', 'Exposure varies across a single wall, so check moisture at several heights before changing the schedule.')}</div>

    {h3('Protect exposed irrigation before frost')}
    {p('Inspect outdoor taps, pipework, valves, connectors, and timers before the first freeze. Water can expand as it freezes and damages vulnerable components. Insulation can reduce exposure, and some systems also require vulnerable sections to be drained or winterised. Follow the instructions for the installed system, and check for leaks or damage after a cold spell.')}

    <div style="{TWO};align-items:center;margin-top:clamp(10px,2vw,20px)">
      <div>
        {h3('Prune selectively and keep drainage clear')}
        {p('A pre-winter visit is a good time to remove dead or damaged material, clear debris from drainage points, and check for loose planting. Trim excessive growth where it is likely to catch the wind or overhang neighbouring plants. Cut back herbaceous perennials only where the timing suits the species, and use a lighter touch with evergreen shrubs and ferns. A follow-up check after storms or freezing weather can catch loose plants, blocked drainage, or irrigation problems early.')}
      </div>
      {fig('prune', 'A pre-winter maintenance visit on an outdoor living wall.')}
    </div>
  </div>
</section>

<section id="indoor" data-screen-label="Indoor" style="{SEC}">
  <div style="{WRAP}">
    <p data-fade style="{EYEBROW}">02 — Indoor</p>
    <h2 data-split style="{H2}">Indoor living walls</h2>
    <div style="{TWO}">
      <div>
        {h3('Check light and humidity when the heating comes on').replace('margin:clamp(30px,4vw,50px) 0 16px', 'margin:0 0 16px')}
        {p('Shorter days can reduce the light reaching an indoor wall, particularly in areas that rely on daylight. Check whether existing grow lights still cover the full planting area, and review their timing if needed. Heating and ventilation can also create dry spots, particularly near vents. Check humidity close to the wall, where the plants experience it.')}
        {p('Brown or crispy leaf tips can be a sign of dry air, particularly when indoor heating is on, but they can also have other causes. Before increasing irrigation, check the moisture levels in the growing medium. If the growing medium is already sufficiently moist, consider lightly misting the affected foliage once a week to help counteract dry indoor air. Also, ensure plants are not exposed to direct heat from radiators or heating vents.')}
      </div>
      {fig('indoor', 'An indoor living wall beside a staircase, where heating and daylight change through the winter.')}
    </div>

    {h3('Water and feed according to plant growth')}
    {p(f'An indoor wall in a warm, consistently lit space may continue growing through winter. A wall that relies on natural daylight may slow down and use less water. Check moisture at several heights, review how actively the plants are growing, and use those observations to adjust watering and feeding. Pay particular attention to ferns near vents and to lower sections that may stay damp for longer. For design advice, see <a href="{BASE}/how-to-design-a-long-lasting-internal-living-wall/" style="{LINK}">how to design a long-lasting internal living wall</a>.')}

    {h3('Match indoor plants to light and humidity')}
    {plant_list(indoor_plants)}
  </div>
</section>

<section id="checklist" data-screen-label="Checklist" style="border-top:1px solid rgba(63,78,10,.16);background:#0B0F0B;color:#F2F1EA;{SEC}">
  <div style="{WRAP}">
    <p data-fade style="font-size:12px;letter-spacing:.24em;text-transform:uppercase;color:#C6DE4E;margin-bottom:18px">03 — Checklist</p>
    <h2 data-split style="{H2};color:#F2F1EA">Winter living wall checklist</h2>
    <ol data-stagger style="list-style:none;padding:0;display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,300px),1fr));gap:clamp(14px,2vw,24px) clamp(24px,3vw,44px)">
{''.join(f'      <li style="border-top:1px solid #9BB222;padding-top:14px;display:grid;gap:6px"><span style="font-size:11.5px;letter-spacing:.16em;text-transform:uppercase;color:#C6DE4E">{n:02d} · {w}</span><span style="color:#DDDED7">{t}</span></li>{chr(10)}' for n, (w, t) in enumerate(checklist, 1))}    </ol>
  </div>
</section>

<section id="faq" data-screen-label="FAQ" style="{ALT}{SEC}">
  <div style="{WRAP}">
    <p data-fade style="{EYEBROW}">04 — FAQ</p>
    <h2 data-split style="{H2}">Winter living wall care: common questions</h2>
    <div data-stagger style="border-top:1px solid rgba(63,78,10,.22)">
{''.join(f'      <details style="border-bottom:1px solid rgba(63,78,10,.22);padding:20px 0"><summary style="list-style:none;cursor:pointer;display:flex;justify-content:space-between;gap:20px;align-items:center"><h3 style="font-family:var(--d);font-weight:400;font-size:clamp(20px,1.8vw,25px);line-height:1.25;color:#12160F;margin:0">{e(q)}</h3><span class="lswc-plus" aria-hidden="true" style="font-size:26px;color:#3F4E0A;transition:transform .2s ease;flex:0 0 auto">+</span></summary><p style="{P_FAQ}">{e(a)}</p></details>{chr(10)}' for q, a in faqs)}    </div>
    <p data-fade style="font-size:15px;color:#5A6055;margin-top:24px">More answers on load, irrigation and plant selection are in our <a href="{BASE}/living-wall-faqs/" style="{LINK}">living wall FAQ</a>.</p>
  </div>
</section>

<section data-screen-label="CTA" style="border-top:1px solid rgba(63,78,10,.16);{SEC}">
  <div style="{WRAP};display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,320px),1fr));gap:clamp(28px,4vw,70px);align-items:end">
    <div><p data-fade style="{EYEBROW}">— Next step</p><h2 data-split style="{H2_CTA}">Need help preparing your living wall for winter?</h2></div>
    <div data-fade>
      <p style="color:#5A6055;max-width:46ch;margin-bottom:24px;text-wrap:pretty">Get in touch with Life on Walls™ to discuss seasonal maintenance, irrigation, or planting suited to your site. We also maintain living walls installed by other companies.</p>
      <p style="display:flex;flex-wrap:wrap;gap:12px"><a class="lh-lswc-1" href="{BASE}/contact-us/" style="{BTN1}">Book a consultation</a><a class="lh-lswc-2" href="{BASE}/living-wall-maintenance/" style="{BTN2}">Maintenance services</a></p>
    </div>
  </div>
</section>
</article>'''

# Motion: same GSAP 3.12.5 + ScrollTrigger build as the /blog/ index. Content is
# only hidden once GSAP has loaded, nothing moves under prefers-reduced-motion,
# and a watchdog reveals everything if the animation loop never starts.
MOTION = '''<style>
.low-root [data-lswc] .wordwrap{display:inline-block;overflow:hidden;vertical-align:top;padding-bottom:.12em;margin-bottom:-.12em}
.low-root [data-lswc] .word{display:inline-block;will-change:transform}
.low-root [data-lswc] [data-reveal]{overflow:hidden}
.lswc-progress{position:fixed;top:0;left:0;right:0;height:3px;background:#9BB222;transform-origin:0 50%;transform:scaleX(0);z-index:2147483001;pointer-events:none}
</style>
<script defer src="https://cdn.jsdelivr.net/npm/gsap@3.12.5/dist/gsap.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/gsap@3.12.5/dist/ScrollTrigger.min.js"></script>
<script>
(function(){
  var art = document.querySelector('[data-lswc]');
  if (!art || art.dataset.motion) return;
  art.dataset.motion = '1';
  var reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* reading progress */
  var bar = document.createElement('div');
  bar.className = 'lswc-progress';
  bar.setAttribute('aria-hidden', 'true');
  document.body.appendChild(bar);
  var ticking = false;
  function prog(){
    ticking = false;
    var r = art.getBoundingClientRect(), total = art.offsetHeight - window.innerHeight;
    var p = total > 0 ? Math.min(1, Math.max(0, -r.top / total)) : 0;
    bar.style.transform = 'scaleX(' + p + ')';
  }
  function onScroll(){ if (!ticking) { ticking = true; requestAnimationFrame(prog); } }
  window.addEventListener('scroll', onScroll, { passive: true });
  window.addEventListener('resize', onScroll);
  prog();

  function boot(){
    var gsap = window.gsap, ST = window.ScrollTrigger;
    if (!gsap || !ST || reduced) return;
    gsap.registerPlugin(ST);

    /* GSAP arrives late on this site (LiteSpeed defers it), so only animate
       what the reader has not reached yet: anything on screen stays put. */
    var vh = window.innerHeight;
    var hero = art.querySelector('[data-hero]');
    function ahead(el){ return !(hero && hero.contains(el)) && el.getBoundingClientRect().top > vh; }
    function st(el){ return { trigger: el, start: 'top bottom-=40', once: true }; }

    /* hero photo drifts slightly on scroll */
    var media = hero && hero.querySelector('[data-hero-media]');
    if (media) gsap.to(media, { yPercent: 12, ease: 'none', scrollTrigger: { trigger: hero, start: 'top top', end: 'bottom top', scrub: true } });

    /* headings rise word by word */
    art.querySelectorAll('[data-split]').forEach(function(el){
      if (!ahead(el)) return;
      var text = el.textContent.trim();
      el.setAttribute('aria-label', text);
      el.innerHTML = text.split(/\\s+/).map(function(w){
        return '<span class="wordwrap" aria-hidden="true"><span class="word">' + w + '</span></span>';
      }).join(' ');
      gsap.from(el.querySelectorAll('.word'), { yPercent: 110, duration: 0.8, ease: 'expo.out', stagger: 0.03, scrollTrigger: st(el) });
    });

    /* text fades up */
    art.querySelectorAll('[data-fade]').forEach(function(el){
      if (!ahead(el)) return;
      gsap.from(el, { opacity: 0, y: 18, duration: 0.6, ease: 'power2.out', scrollTrigger: st(el) });
    });

    /* photographs wipe open */
    art.querySelectorAll('[data-reveal]').forEach(function(fig){
      var img = fig.querySelector('img');
      if (!img || !ahead(fig)) return;
      gsap.fromTo(img, { clipPath: 'inset(0 0 100% 0)', scale: 1.08 }, { clipPath: 'inset(0 0 0% 0)', scale: 1, duration: 1, ease: 'expo.out', clearProps: 'clipPath,transform', scrollTrigger: st(fig) });
    });

    /* list rows, checklist and FAQ arrive as each row comes into view */
    var rows = [];
    art.querySelectorAll('[data-stagger]').forEach(function(list){ [].forEach.call(list.children, function(li){ if (ahead(li)) rows.push(li); }); });
    if (rows.length) {
      gsap.set(rows, { opacity: 0, y: 16 });
      ST.batch(rows, { start: 'top bottom-=40', once: true, onEnter: function(b){ gsap.to(b, { opacity: 1, y: 0, duration: 0.6, ease: 'power2.out', stagger: 0.06, overwrite: true }); } });
    }

    /* lazy images, fonts and FAQ toggles change the page height after setup;
       recalculate reveal points whenever the layout settles */
    if (window.ResizeObserver) { var rt; var ro = new ResizeObserver(function(){ clearTimeout(rt); rt = setTimeout(function(){ ST.refresh(); }, 120); }); ro.observe(art); ro.observe(document.body); }
    art.querySelectorAll('details').forEach(function(d){ d.addEventListener('toggle', function(){ ST.refresh(); }); });

    /* watchdog: never leave content hidden */
    setTimeout(function(){
      if (gsap.ticker.frame > 0) return;
      gsap.globalTimeline.getChildren().forEach(function(t){ t.kill(); });
      ST.getAll().forEach(function(t){ t.kill(); });
      gsap.set(art.querySelectorAll('[data-fade],[data-stagger] > *,[data-reveal] img,.word,[data-hero-media]'), { clearProps: 'opacity,transform,clipPath' });
    }, 1100);

    window.addEventListener('load', function(){ ST.refresh(); });
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(function(){ ST.refresh(); });
  }

  function waitLibs(n){
    if (window.gsap && window.ScrollTrigger) return boot();
    if (n > 80) return;
    setTimeout(function(){ waitLibs(n + 1); }, 100);
  }
  waitLibs(0);
})();
</script>'''

ORG = {'@id': BASE + '/#organization'}
graph = [
    {'@type': 'BlogPosting', '@id': URL + '#article', 'mainEntityOfPage': URL, 'url': URL,
     'headline': TITLE, 'description': DESC,
     'image': [IMG.replace(IMG, 'https://lifeonwalls.co.uk/wp-content/uploads/2026/11/') + v[0] for v in img.values()],
     'datePublished': DATE + 'T09:00:00+00:00', 'dateModified': DATE + 'T09:00:00+00:00',
     'inLanguage': 'en-GB', 'author': ORG, 'publisher': ORG,
     'articleSection': 'Maintenance', 'wordCount': 1100,
     'about': [{'@type': 'Thing', 'name': n} for n in ('Living walls', 'Living wall maintenance', 'Winter plant care')],
     'keywords': 'living wall winter care, living wall maintenance, winter living wall, indoor living wall care, outdoor living wall frost, living wall irrigation winter, evergreen living wall plants'},
    {'@type': 'FAQPage', '@id': URL + '#faq',
     'mainEntity': [{'@type': 'Question', 'name': q, 'acceptedAnswer': {'@type': 'Answer', 'text': a}} for q, a in faqs]},
]
head = ('<script type="application/ld+json">' + json.dumps({'@context': 'https://schema.org', '@graph': graph}, ensure_ascii=False, separators=(',', ':')) + '</script>\n'
        '<style>.low-root .lh-lswc-1:hover{background:#C6DE4E !important;color:#0B0F0B !important}'
        '.low-root .lh-lswc-2:hover{border-color:#3F4E0A !important;color:#3F4E0A !important}'
        '.low-root details summary::-webkit-details-marker{display:none}'
        '.low-root details[open] .lswc-plus{transform:rotate(45deg)}</style>')
meta = {'slug': SLUG, 'title': TITLE, 'seo_title': 'Living Wall Winter Care: Indoor and Outdoor Guide',
        'seo_description': DESC, 'focus_keyphrase': 'living wall winter care',
        'excerpt': 'Seasonal guidance on caring for indoor and outdoor living walls in winter: planting, irrigation, frost protection, pruning, light and humidity.',
        'og_image': 'https://lifeonwalls.co.uk/wp-content/uploads/2026/11/' + img['hero'][0]}
open(f'{OUT}/body.html', 'w').write(body)
open(f'{OUT}/head.html', 'w').write(head)
open(f'{OUT}/motion.html', 'w').write(MOTION)
open(f'{OUT}/meta.json', 'w').write(json.dumps(meta, indent=2, ensure_ascii=False))
print(len(head), len(body), len(meta['seo_title']), len(DESC))
