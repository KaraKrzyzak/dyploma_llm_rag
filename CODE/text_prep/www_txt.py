import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import os
from CODE.text_prep.prep_clean_code import clean_code_text

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# ══════════════════════════════════════════════════════════════════════════════
# LABTESTSONLINE.PL
# Polska wersja międzynarodowego portalu AACC poświęconego badaniom laboratoryjnym.
# Artykuły pisane przez diagnostów i lekarzy, przeznaczone dla pacjentów.
# Struktura URL: /test/{slug}/ — statyczny HTML, działa z requests.
# ══════════════════════════════════════════════════════════════════════════════

LABTEST_BASE = "https://labtestsonline.pl"

LABTEST_SECTIONS = [

    # ── MORFOLOGIA I KREW ─────────────────────────────────────────────────────
    "/test/morfologia/",
    # Morfologia pełna – RBC, WBC, HGB, HCT, MCV, MCH, MCHC, PLT, retikulocyty; normy i interpretacja

    "/test/rozmaz-krwi-obwodowej/",
    # Rozmaz krwi – mikroskopowa ocena erytrocytów, leukocytów, płytek; wskazania

    "/test/retikulocyty/",
    # Retikulocyty – młode krwinki czerwone; ocena czynności szpiku kostnego

    "/test/mchc/",
    # MCHC – średnie stężenie hemoglobiny w krwince; mikrocytoza, sferocytoza

    "/test/rdw/",
    # RDW – szerokość rozkładu objętości erytrocytów; anemie mieszane, niedobory

    # ── ŻELAZO I GOSPODARKA ŻELAZEM ──────────────────────────────────────────
    "/test/ferrytyna/",
    # Ferrytyna – ocena zapasów żelaza; normy, interpretacja niskiej i wysokiej wartości

    "/test/zelazo/",
    # Żelazo w surowicy – diagnostyka niedokrwistości z niedoboru żelaza

    "/test/transferyna/",
    # Transferyna i TIBC – zdolność wiązania żelaza; saturacja transferyny

    # ── ELEKTROLITY I MINERAŁY ────────────────────────────────────────────────
    "/test/sod/",
    # Sód – hipo/hipernatremia; gospodarka wodno-elektrolitowa, nerki

    "/test/potas/",
    # Potas – hipo/hiperkaliemia; arytmia, choroby nerek, nadnercza

    "/test/wapn/",
    # Wapń – hipo/hiperkalcemia; osteoporoza, przytarczyce, nerki

    "/test/magnez/",
    # Magnez – niedobór, skurcze mięśni, arytmia; normy i interpretacja

    "/test/fosfor/",
    # Fosfor – hipofosfatemia; metabolizm kostny, nerki, witamina D

    # ── GLUKOZA I METABOLIZM WĘGLOWODANÓW ────────────────────────────────────
    "/test/glukoza/",
    # Glukoza – normy na czczo, cukrzyca (typ 1 i 2), hipoglikemia, interpretacja

    "/test/hemoglobina-glikowana-hba1c/",
    # HbA1c – długoterminowa kontrola cukrzycy; normy, cele terapeutyczne

    "/test/insulina/",
    # Insulina – insulinooporność, hiperinsulinemia, diagnostyka cukrzycy

    # ── LIPIDOGRAM / CHOLESTEROL ─────────────────────────────────────────────
    "/test/lipidogram/",
    # Lipidogram – cholesterol całkowity, LDL, HDL, triglicerydy; ryzyko CVD

    "/test/cholesterol-ldl/",
    # LDL – „zły" cholesterol; miażdżyca, ryzyko zawału, normy terapeutyczne

    "/test/cholesterol-hdl/",
    # HDL – „dobry" cholesterol; ochrona przed miażdżycą, normy

    "/test/triglicerydy/",
    # Triglicerydy – hipertriglicerydemia; ryzyko CVD, trzustka, dieta

    # ── HORMONY TARCZYCY ──────────────────────────────────────────────────────
    "/test/tsh/",
    # TSH – hormon tyreotropowy; nadczynność vs. niedoczynność tarczycy, normy

    "/test/ft4/",
    # FT4 – wolna tyroksyna; niedoczynność tarczycy, leczenie lewotyroksyną

    "/test/ft3/",
    # FT3 – wolna trijodotyronina; nadczynność tarczycy, konwersja T4→T3

    "/test/anty-tpo/",
    # Anty-TPO – przeciwciała tarczycowe; Hashimoto, choroba Gravesa-Basedowa

    "/test/anty-tg/",
    # Anty-TG – przeciwciała przeciwtyreoglobulinowe; Hashimoto, diagnostyka

    # ── HORMONY PŁCIOWE I PŁODNOŚĆ ────────────────────────────────────────────
    "/test/fsh/",
    # FSH – hormon folikulotropowy; diagnostyka płodności, menopauza

    "/test/lh/",
    # LH – hormon luteinizujący; owulacja, PCOS, hipogonadyzm

    "/test/estradiol/",
    # Estradiol (E2) – cykl menstruacyjny, menopauza, diagnostyka płodności

    "/test/progesteron/",
    # Progesteron – faza lutealna, ciąża, diagnostyka niedoboru progesteronu

    "/test/testosteron/",
    # Testosteron – normy u mężczyzn i kobiet, hipogonadyzm, TRT

    "/test/prolaktyna/",
    # Prolaktyna – hiperprolaktynemia, zaburzenia miesiączkowania, laktacja

    # ── HORMONY NADNERCZY ─────────────────────────────────────────────────────
    "/test/kortyzol/",
    # Kortyzol – choroba Cushinga, niewydolność nadnerczy, stres; normy

    "/test/dhea-s/",
    # DHEA-S – androgen nadnerczowy; trądzik, PCOS, diagnostyka

    # ── NERKI ─────────────────────────────────────────────────────────────────
    "/test/kreatynina/",
    # Kreatynina – ocena czynności nerek, eGFR, przewlekła choroba nerek

    "/test/mocznik/",
    # Mocznik (BUN) – metabolizm białek, azotemia, ocena funkcji nerek

    "/test/kwas-moczowy/",
    # Kwas moczowy – dna moczanowa, hiperurykemia, kamica nerkowa

    "/test/badanie-ogolne-moczu/",
    # Badanie ogólne moczu – parametry, normy, interpretacja wyników

    # ── ENZYMY WĄTROBOWE ─────────────────────────────────────────────────────
    "/test/alt/",
    # ALT (ALAT) – enzym wątrobowy; uszkodzenie hepatocytów, hepatitis, normy

    "/test/ast/",
    # AST (AspAT) – enzym wątrobowy i mięśniowy; zawał serca, hepatitis

    "/test/ggtp/",
    # GGTP – enzym wątrobowy; alkohol, cholestaza, leki hepatotoksyczne

    "/test/bilirubina/",
    # Bilirubina – żółtaczka, choroby wątroby i dróg żółciowych; normy

    "/test/fosfataza-alkaliczna/",
    # ALP – fosfataza alkaliczna; choroby kości i wątroby, normy

    # ── STAN ZAPALNY ──────────────────────────────────────────────────────────
    "/test/crp/",
    # CRP – białko ostrej fazy; infekcje, stany zapalne, ryzyko CVD

    "/test/ob/",
    # OB – odczyn Biernackiego; stan zapalny, choroby autoimmunologiczne

    "/test/prokalcytonina/",
    # Prokalcytonina – marker sepsy bakteryjnej; różnicowanie infekcji

    # ── WITAMINY ──────────────────────────────────────────────────────────────
    "/test/witamina-b12/",
    # Witamina B12 – rola w erytropoezie i neurologii; niedobór, objawy

    "/test/kwas-foliowy/",
    # Kwas foliowy – niedobór, ciąża, anemie megaloblastyczne; normy

    "/test/witamina-d/",
    # Witamina D 25(OH) – forma oznaczana we krwi; niedobór, normy, suplementacja

    # ── INNE PARAMETRY ────────────────────────────────────────────────────────
    "/test/homocysteina/",
    # Homocysteina – ryzyko CVD i udaru; niedobór B12 i folianu; normy

    "/test/shbg/",
    # SHBG – globulina wiążąca hormony płciowe; insulinooporność, PCOS

    "/test/psa/",
    # PSA – antygen swoisty dla prostaty; rak prostaty, przesiewowe badanie mężczyzn

    "/test/d-dimer/",
    # D-dimer – zakrzepica, zatorowość płucna; normy i interpretacja

    "/test/troponina/",
    # Troponina – marker uszkodzenia mięśnia sercowego; zawał serca, diagnostyka

]


def scrape_article_labtest(url: str) -> dict | None:
    """
    Pobiera treść jednego artykułu z labtestsonline.pl.
    Strona używa statycznego HTML — requests działa bez przeglądarki.
    Zwraca słownik {source, url, title, text} lub None jeśli brak treści.
    """
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            print(f"  [SKIP] {url} → HTTP {r.status_code}")
            return None

        soup = BeautifulSoup(r.text, "html.parser")

        # Tytuł artykułu z tagu h1
        title_tag = soup.find("h1")
        title = title_tag.get_text(strip=True) if title_tag else url

        # Labtestsonline używa różnych kontenerów treści
        content_div = (
            soup.find("div", class_="entry-content")
            or soup.find("div", class_="post-content")
            or soup.find("article")
            or soup.find("main")
        )
        if not content_div:
            print(f"  [SKIP] {url} → brak treści")
            return None

        # Usuń nawigację, reklamy i elementy niebędące treścią
        for tag in content_div.find_all(["script", "style", "nav", "footer", "aside"]):
            tag.decompose()

        # Zamień HTML na czysty tekst, filtruj linie krótsze niż 20 znaków
        text = content_div.get_text(separator="\n", strip=True)
        text = "\n".join(l for l in text.split("\n") if len(l) > 20)

        if not text.strip():
            print(f"  [SKIP] {url} → pusty tekst po czyszczeniu")
            return None

        return {"source": "labtestsonline.pl", "url": url, "title": title, "text": text}
    except Exception as e:
        print(f"  [ERR] {url}: {e}")
        return None


def scrape_labtest_directly(sections: list) -> list:
    """
    Scrapuje listę URL-ów labtestsonline.pl bezpośrednio.
    Każdy URL to osobny artykuł o konkretnym badaniu.
    Zwraca listę artykułów (słowników).
    """
    articles = []
    for section in sections:
        url = urljoin(LABTEST_BASE, section)
        print(f"  LabTest: {url}")
        article = scrape_article_labtest(url)
        if article:
            article["text"] = clean_code_text(article["text"])
            articles.append(article)
    return articles


# ══════════════════════════════════════════════════════════════════════════════
# SYNEVO.PL
# Sieć laboratoriów diagnostycznych z bazą artykułów o badaniach.
# Artykuły pisane przez lekarzy, zawierają normy, wskazania i interpretację.
# Struktura URL: /badanie/{slug}/ — statyczny HTML, działa z requests.
# ══════════════════════════════════════════════════════════════════════════════

SYNEVO_BASE = "https://www.synevo.pl"

SYNEVO_SECTIONS = [

    # ── MORFOLOGIA I KREW ─────────────────────────────────────────────────────
    "/badanie/morfologia-krwi/",
    # Morfologia pełna – RBC, WBC, HGB, PLT i wskaźniki; normy, wskazania

    "/badanie/rozmaz-krwi/",
    # Rozmaz krwi – różnicowanie leukocytów, ocena erytrocytów i płytek

    # ── ŻELAZO ────────────────────────────────────────────────────────────────
    "/badanie/ferrytyna/",
    # Ferrytyna – zapasy żelaza; niska (niedobór), wysoka (hemochromatoza, zapalenie)

    "/badanie/zelazo/",
    # Żelazo w surowicy – niedokrwistość z niedoboru żelaza; normy

    "/badanie/transferyna/",
    # Transferyna – transport żelaza we krwi; saturacja, TIBC

    # ── ELEKTROLITY ───────────────────────────────────────────────────────────
    "/badanie/sod/",
    # Sód – gospodarka wodno-elektrolitowa; hiponatremia, hipernatremia

    "/badanie/potas/",
    # Potas – kaliemia; arytmia, niewydolność nerek, leki

    "/badanie/wapn/",
    # Wapń – metabolizm kostny; hiperkalcemia (przytarczyce), hipokalcemia

    "/badanie/magnez/",
    # Magnez – niedobór (skurcze, arytmia); normy i suplementacja

    # ── GLUKOZA I METABOLIZM ──────────────────────────────────────────────────
    "/badanie/glukoza/",
    # Glukoza na czczo – cukrzyca, stan przedcukrzycowy, hipoglikemia

    "/badanie/hemoglobina-glikowana-hba1c/",
    # HbA1c – kontrola cukrzycy; cel <7%, interpretacja wyników

    "/badanie/insulina/",
    # Insulina – insulinooporność, HOMA-IR; diagnostyka cukrzycy typu 2

    # ── LIPIDOGRAM ────────────────────────────────────────────────────────────
    "/badanie/lipidogram/",
    # Lipidogram – cholesterol całkowity, LDL, HDL, TG; ryzyko sercowo-naczyniowe

    "/badanie/cholesterol-ldl/",
    # LDL – miażdżyca; normy zależne od ryzyka CVD, leczenie statyną

    "/badanie/cholesterol-hdl/",
    # HDL – ochronny; niskie HDL jako czynnik ryzyka CVD

    "/badanie/triglicerydy/",
    # Triglicerydy – hypertriglicerydemia; otyłość, alkohol, cukrzyca

    # ── HORMONY TARCZYCY ──────────────────────────────────────────────────────
    "/badanie/tsh/",
    # TSH – podstawowe badanie tarczycy; nadczynność (↓) vs. niedoczynność (↑)

    "/badanie/ft4/",
    # FT4 – wolna tyroksyna; leczenie niedoczynności tarczycy

    "/badanie/ft3/",
    # FT3 – wolna trijodotyronina; nadczynność, konwersja obwodowa

    "/badanie/anty-tpo/",
    # Anty-TPO – autoimmunologiczne zapalenie tarczycy (Hashimoto)

    # ── HORMONY PŁCIOWE ───────────────────────────────────────────────────────
    "/badanie/fsh/",
    # FSH – płodność, menopauza, hipogonadyzm; normy zależne od fazy cyklu

    "/badanie/lh/",
    # LH – owulacja, PCOS, diagnostyka zaburzeń hormonalnych

    "/badanie/estradiol/",
    # Estradiol – cykl menstruacyjny, menopauza, stymulacja owulacji

    "/badanie/progesteron/",
    # Progesteron – faza lutealna, ciąża, diagnostyka niepłodności

    "/badanie/testosteron/",
    # Testosteron – mężczyźni (hipogonadyzm) i kobiety (hiperandrogenizm, PCOS)

    "/badanie/prolaktyna/",
    # Prolaktyna – hiperprolaktynemia, gruczolak przysadki, zaburzenia miesiączkowania

    # ── NERKI ─────────────────────────────────────────────────────────────────
    "/badanie/kreatynina/",
    # Kreatynina – czynność nerek; eGFR, przewlekła choroba nerek (CKD)

    "/badanie/mocznik/",
    # Mocznik – azotemia, dieta wysokobiałkowa; ocena nerek

    "/badanie/kwas-moczowy/",
    # Kwas moczowy – dna moczanowa, hiperurykemia; normy

    "/badanie/badanie-ogolne-moczu/",
    # Badanie ogólne moczu – barwa, pH, białko, glukoza, osad; interpretacja

    # ── ENZYMY WĄTROBOWE ─────────────────────────────────────────────────────
    "/badanie/alt-alat/",
    # ALT – hepatitis, stłuszczenie wątroby, toksyczne uszkodzenie; normy

    "/badanie/ast-aspat/",
    # AST – uszkodzenie wątroby i mięśnia sercowego; stosunek AST/ALT

    "/badanie/ggtp/",
    # GGTP – alkohol, cholestaza, leki; normy u kobiet i mężczyzn

    "/badanie/bilirubina/",
    # Bilirubina całkowita, bezpośrednia, pośrednia; żółtaczka, hemoliza

    # ── STAN ZAPALNY ──────────────────────────────────────────────────────────
    "/badanie/crp/",
    # CRP – infekcje bakteryjne, stany zapalne, ryzyko chorób sercowo-naczyniowych

    "/badanie/ob/",
    # OB – nieswoisty marker zapalny; choroby autoimmunologiczne, infekcje

    # ── WITAMINY ──────────────────────────────────────────────────────────────
    "/badanie/witamina-b12/",
    # Witamina B12 – niedokrwistość megaloblastyczna, neuropatia; niedobór u wegetarian

    "/badanie/kwas-foliowy/",
    # Kwas foliowy – ciąża (wady cewy nerwowej), anemia megaloblastyczna; normy

    "/badanie/witamina-d/",
    # Witamina D 25(OH) – niedobór (osteoporoza, odporność); normy suplementacyjne

    # ── INNE ──────────────────────────────────────────────────────────────────
    "/badanie/homocysteina/",
    # Homocysteina – ryzyko miażdżycy i zakrzepicy; niedobór B12 i kwasu foliowego

    "/badanie/psa-antygen-swoisty-dla-prostaty/",
    # PSA – rak prostaty, łagodny rozrost; normy zależne od wieku

    "/badanie/d-dimer/",
    # D-dimer – zakrzepica żył głębokich, zatorowość płucna; interpretacja

]


def scrape_article_synevo(url: str) -> dict | None:
    """
    Pobiera treść jednego artykułu z synevo.pl.
    Strona używa statycznego HTML — requests działa bez przeglądarki.
    Zwraca słownik {source, url, title, text} lub None jeśli brak treści.
    """
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            print(f"  [SKIP] {url} → HTTP {r.status_code}")
            return None

        soup = BeautifulSoup(r.text, "html.parser")

        title_tag = soup.find("h1")
        title = title_tag.get_text(strip=True) if title_tag else url

        # Synevo używa różnych kontenerów treści w zależności od szablonu
        content_div = (
            soup.find("div", class_="post-content")
            or soup.find("div", class_="entry-content")
            or soup.find("div", class_="content")
            or soup.find("article")
            or soup.find("main")
        )
        if not content_div:
            print(f"  [SKIP] {url} → brak treści")
            return None

        for tag in content_div.find_all(["script", "style", "nav", "footer", "aside"]):
            tag.decompose()

        text = content_div.get_text(separator="\n", strip=True)
        text = "\n".join(l for l in text.split("\n") if len(l) > 20)

        if not text.strip():
            print(f"  [SKIP] {url} → pusty tekst po czyszczeniu")
            return None

        return {"source": "synevo.pl", "url": url, "title": title, "text": text}
    except Exception as e:
        print(f"  [ERR] {url}: {e}")
        return None


def scrape_synevo_directly(sections: list) -> list:
    """
    Scrapuje listę URL-ów synevo.pl bezpośrednio.
    Każdy URL to osobny artykuł o konkretnym badaniu.
    Zwraca listę artykułów (słowników).
    """
    articles = []
    for section in sections:
        url = urljoin(SYNEVO_BASE, section)
        print(f"  Synevo: {url}")
        article = scrape_article_synevo(url)
        if article:
            article["text"] = clean_code_text(article["text"])
            articles.append(article)
    return articles


# ══════════════════════════════════════════════════════════════════════════════
# UPACJENTA.PL
# Portal zdrowotny z artykułami poradnikowymi dla pacjentów.
# Dobra struktura HTML, scrapujemy artykuły z listy + linki z ich treści.
# ══════════════════════════════════════════════════════════════════════════════

UPACJENTA_BASE = "https://www.upacjenta.pl"

UPACJENTA_SECTIONS = [

    # ── INTERPRETACJA WYNIKÓW I PRZEGLĄDY OGÓLNE ──────────────────────────────
    "/poradnik/interpretacja-wynikow-badan",           # Kompleksowa interpretacja wyników krwi (morfologia, glukoza, cholesterol, kreatynina, TSH, ferrytyna…)
    "/poradnik/morfologia-wyniki",                     # Wyniki morfologii – kiedy powinny niepokoić
    "/poradnik/jak-przygotowac-sie-do-badania-krwi",   # Przygotowanie do badania krwi – post, leki, pora dnia
    "/poradnik/kiedy-wykonac-badanie-crp",             # CRP – kiedy i dlaczego warto zbadać
    "/poradnik/badanie-alat-jaki-wynik-jest-niepokojacy",  # ALT (ALAT) – interpretacja wyniku, normy

    # ── WITAMINY ──────────────────────────────────────────────────────────────
    "/poradnik/niedobor-witaminy-d-objawy",            # Witamina D – objawy niedoboru, normy, znaczenie kliniczne
    "/poradnik/witamina-b12",                          # Witamina B12 – objawy niedoboru, suplementacja, ryzyko niedoboru
    "/poradnik/jak-sprawdzic-niedobory-witamin-i-skladnikow-mineralnych",  # Przegląd badań na niedobory: wit. D, B12, kwas foliowy, magnez, żelazo
    "/poradnik/jak-laczyc-witaminy-i-mineraly-tabela", # Synergizm i antagonizm – jak łączyć witaminy i minerały (tabela)
    "/poradnik/6-niedoborow-ktore-moga-powodowac-stany-depresyjne",  # Wit. D, B12, magnez, cynk, selen – niedobory a nastrój
    "/poradnik/witaminy-suplementy-dla-kobiet",        # Witaminy i suplementy dla kobiet (30+, 40+, 50+, 60+)
    "/poradnik/najlepsze-witaminy-suplementy-dla-mezczyzn",  # Witaminy i suplementy dla mężczyzn

    # ── MINERAŁY I ELEKTROLITY ────────────────────────────────────────────────
    "/poradnik/magnez-wlasciwosci-niedobory-dawkowanie",   # Magnez – objawy niedoboru, dieta, suplementacja, formy magnezu
    "/poradnik/niedobor-zelaza-objawy-skutki-leczenie",    # Żelazo – objawy niedoboru, diagnostyka, leczenie
    "/poradnik/co-to-jest-ferrytyna-i-dlaczego-warto-ja-kontrolowac",  # Ferrytyna – rola, badanie, interpretacja wyników
    "/poradnik/niska-ferrytyna-objawy-jak-podniesc-jej-poziom",  # Niska ferrytyna – objawy i jak podnieść poziom
    "/poradnik/wysoka-ferrytyna-jak-obnizyc-jej-poziom",   # Wysoka ferrytyna – przyczyny (hemochromatoza, stany zapalne), leczenie

    # ── HORMONY ───────────────────────────────────────────────────────────────
    "/poradnik/hormony",                               # Ogólny poradnik o hormonach – podział, funkcje, badania
    "/poradnik/choroby-tarczycy-leczenie-dieta-badania",   # Tarczyca – TSH, FT3, FT4, aTPO, aTG, TRAb; normy i interpretacja
    "/poradnik/niedoczynnosc-tarczycy-objawy-badania-dieta",  # Niedoczynność tarczycy – diagnostyka, objawy, leczenie lewotyroksyną
    "/poradnik/nadczynnosc-tarczycy-objawy-badania-dieta",   # Nadczynność tarczycy – diagnostyka, dieta, leczenie
    "/poradnik/hashimoto-jak-je-zdiagnozowac-i-leczyc",     # Hashimoto – anty-TPO, anty-TG, TSH, FT3, FT4; diagnostyka i leczenie
    "/poradnik/niedoczynnosc-tarczycy-dieta",               # Dieta przy niedoczynności tarczycy; jod, selen, cynk a TSH
    "/poradnik/tradzik-hormonalny-objawy-badania-leczenie",  # Trądzik hormonalny – testosteron, DHEA-SO4, SHBG, kortyzol, androstendion
    "/poradnik/tradzik-u-doroslych-przyczyny-leczenie-badania",  # Trądzik u dorosłych – badania hormonalne, leczenie
    "/poradnik/niedobor-testosteronu-u-mezczyzn",           # Testosteron – niedobór, objawy, diagnostyka, TRT

    # ── MORFOLOGIA I KREW ─────────────────────────────────────────────────────
    "/poradnik/morfologia",                            # Morfologia krwi – parametry, normy, interpretacja
    "/poradnik/biochemia",                             # Biochemia krwi – przegląd parametrów biochemicznych
    "/poradnik/anemia-objawy-przyczyny-badania",       # Anemia – objawy, rodzaje, badania (ferrytyna, B12, kwas foliowy, OB)
    "/poradnik/badania-w-trakcie-okresu-tak-czy-nie",  # Badania krwi podczas miesiączki – co się zmienia w wynikach

    # ── LIPIDY I METABOLIZM ───────────────────────────────────────────────────
    "/poradnik/lipidogram",                            # Lipidogram – cholesterol całkowity, LDL, HDL, trójglicerydy; normy
    "/poradnik/zdrowie-metaboliczne",                  # Zdrowie metaboliczne – jakie badania wykonać, interpretacja

    # ── BADANIA MOCZU ─────────────────────────────────────────────────────────
    "/poradnik/badania-moczu",                         # Badania moczu – przegląd parametrów, normy, interpretacja

    # ── PAKIETY I LISTY BADAŃ ─────────────────────────────────────────────────
    "/poradnik/badania-na-plodnosc-lista-badan",       # Badania na płodność – FSH, LH, AMH, estradiol, progesteron, TSH
    "/poradnik/badania-krwi-a-endometrioza",           # Badania krwi a endometrioza – CA-125, markery stanu zapalnego
    "/poradnik/badania-profilaktyczne-dla-40-latkow",  # Badania po 40. roku życia (hormony, PSA, glukoza, cholesterol, TSH)
    "/poradnik/badania-dla-30-latkow",                 # Badania po 30. roku życia (tarczyca, lipidogram, ferrytyna, PSA, AFP)
    "/poradnik/badania-dla-mlodej-mamy-sprawdz-ktore-wykonac",  # Badania dla młodej mamy – morfologia, ferrytyna, tarczyca
    "/poradnik/domowe-badanie-dla-kobiet-w-ciazy",     # Badania dla kobiet w ciąży – morfologia, glukoza, TSH, ferrytyna

    # ── KONKRETNE PARAMETRY / CHOROBY ─────────────────────────────────────────
    "/poradnik/objawy-raka-jelita-grubego",            # Rak jelita grubego – objawy, badania przesiewowe
    "/poradnik/konsultacja-online-czy-raport-zdrowia", # Raport zdrowia vs konsultacja online – porównanie
    "/katalog-badan/badanie-morfologia-krwi-rozmaz-automatyczny",  # Morfologia z rozmazem automatycznym – opis badania, wskazania
]


def get_article_links_upacjenta(section_url: str) -> list[str]:
    """
    Zbiera linki do artykułów z treści strony upacjenta.pl.
    WAŻNE: szuka linków TYLKO w głównej treści artykułu (post-content/main),
    NIE w nawigacji ani stopce — bo tam są linki do wszystkich artykułów
    i powodowałoby to ogromne duplikaty (każdy artykuł pojawiałby się 40+ razy).
    Zwraca listę unikalnych URL-ów do artykułów /poradnik/.
    """
    links = []
    try:
        r = requests.get(section_url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return []

        soup = BeautifulSoup(r.text, "html.parser")

        # Szukaj linków tylko w głównej treści, nie w nawigacji/stopce/sidebarze
        content = (
            soup.find("div", class_="post-content")
            or soup.find("div", class_="entry-content")
            or soup.find("main")
            or soup.find("article")
        )
        if not content:
            return []

        for a in content.find_all("a", href=True):
            href = a["href"]
            full = urljoin(UPACJENTA_BASE, href)
            if (
                "/poradnik/" in href          # tylko artykuły poradnikowe
                and full not in links         # bez duplikatów w tej liście
                and full != section_url       # nie linkuj do siebie
                and "#" not in href           # pomijaj kotwice na stronie
                and "?" not in href           # pomijaj parametry query
            ):
                links.append(full)

    except Exception as e:
        print(f"  [ERR] upacjenta.pl linki {section_url}: {e}")
    return links


def scrape_article_upacjenta(url: str) -> dict | None:
    """
    Pobiera treść jednego artykułu z upacjenta.pl.
    Zwraca słownik {source, url, title, text} lub None jeśli brak treści.
    """
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            print(f"  [SKIP] {url} → HTTP {r.status_code}")
            return None

        soup = BeautifulSoup(r.text, "html.parser")

        title_tag = soup.find("h1")
        title = title_tag.get_text(strip=True) if title_tag else url

        # Upacjenta używa różnych klas w zależności od szablonu strony
        content_div = (
            soup.find("div", class_="post-content")
            or soup.find("div", class_="entry-content")
            or soup.find("article")
            or soup.find("main")
        )
        if not content_div:
            print(f"  [SKIP] {url} → brak treści")
            return None

        for tag in content_div.find_all(["script", "style", "nav", "aside"]):
            tag.decompose()

        text = content_div.get_text(separator="\n", strip=True)
        text = "\n".join(l for l in text.split("\n") if len(l) > 20)

        if not text.strip():
            print(f"  [SKIP] {url} → pusty tekst po czyszczeniu")
            return None

        return {"source": "upacjenta.pl", "url": url, "title": title, "text": text}
    except Exception as e:
        print(f"  [ERR] {url}: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# GŁÓWNA FUNKCJA SCRAPINGU
# Przepływ:
#   1. labtestsonline.pl — scrapuj każdy URL z listy bezpośrednio
#   2. synevo.pl         — scrapuj każdy URL z listy bezpośrednio
#   3. upacjenta.pl      — scrapuj każdy URL + linki z treści artykułu (1 poziom)
#   4. Deduplikacja po URL (seen_urls) — żaden artykuł nie zostanie zapisany dwa razy
#   5. Zapis każdego artykułu jako osobny plik .txt
# ══════════════════════════════════════════════════════════════════════════════

def run_scraping(output_dir: str):
    os.makedirs(output_dir, exist_ok=True)
    all_articles = []
    seen_urls = set()  # globalna deduplikacja — pilnuje że żaden URL nie jest scrapowany dwa razy

    # ── LABTESTSONLINE.PL ─────────────────────────────────────────────────────
    print("Scraping labtestsonline.pl...")
    for article in scrape_labtest_directly(LABTEST_SECTIONS):
        if article["url"] not in seen_urls:
            seen_urls.add(article["url"])
            all_articles.append(article)
    print(f"  labtestsonline.pl łącznie: {sum(1 for a in all_articles if a['source'] == 'labtestsonline.pl')} artykułów")

    # ── SYNEVO.PL ─────────────────────────────────────────────────────────────
    print("Scraping synevo.pl...")
    synevo_start = len(all_articles)
    for article in scrape_synevo_directly(SYNEVO_SECTIONS):
        if article["url"] not in seen_urls:
            seen_urls.add(article["url"])
            all_articles.append(article)
    print(f"  synevo.pl łącznie: {len(all_articles) - synevo_start} artykułów")

    # ── UPACJENTA.PL ──────────────────────────────────────────────────────────
    # Scrapujemy każdy URL z listy jako artykuł,
    # a dodatkowo zbieramy linki z treści każdego artykułu (głębokość 1 poziom)
    print("Scraping upacjenta.pl...")
    upacjenta_start = len(all_articles)

    for section in UPACJENTA_SECTIONS:
        url = urljoin(UPACJENTA_BASE, section)

        # Krok 1: scrapuj sam artykuł sekcji
        if url not in seen_urls:
            seen_urls.add(url)
            article = scrape_article_upacjenta(url)
            if article:
                article["text"] = clean_code_text(article["text"])
                all_articles.append(article)
                print(f"  [OK] {url}")

        # Krok 2: zbierz linki z treści artykułu i scrapuj je też (1 poziom głębiej)
        child_links = get_article_links_upacjenta(url)
        for link in child_links:
            if link not in seen_urls:
                seen_urls.add(link)
                child_article = scrape_article_upacjenta(link)
                if child_article:
                    child_article["text"] = clean_code_text(child_article["text"])
                    all_articles.append(child_article)

    print(f"  upacjenta.pl łącznie: {len(all_articles) - upacjenta_start} artykułów")
    print(f"Łącznie artykułów po deduplikacji: {len(all_articles)}")

    # ── ZAPIS DO PLIKÓW ───────────────────────────────────────────────────────
    # Każdy artykuł zapisywany jako osobny plik txt z nagłówkiem źródła i linku
    for i, article in enumerate(all_articles):
        # Bezpieczna nazwa pliku — tylko litery, cyfry, spacje, podkreślenia, myślniki
        safe_title = "".join(
            c for c in article["title"] if c.isalnum() or c in " _-"
        )[:80]
        filename = f"{i}_{safe_title}.txt"
        filepath = os.path.join(output_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"Źródło: {article['source']}\n")
            f.write(f"Link: {article['url']}\n\n")
            f.write(article["text"])

    print(f"Zapisano {len(all_articles)} plików w: {output_dir}")
    return all_articles