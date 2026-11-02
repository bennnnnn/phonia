# ruff: noqa: RUF001 - the words matched are the languages' own
"""The words a picture subject asked in another language may hold besides its nouns.

``gen_intent_drawable`` reads a subject word by word: each must be a listed noun
(``gen_intent_drawable_romance``, ``gen_intent_drawable_other``), a plain descriptor or a
function word from here. "Dibújame un gato negro en la playa" draws; "un gato en ASCII",
"un árbol binario", "una pizza dividida en fracciones", "un perro y sugiéreme nombres"
are answered in words, because "ASCII", "binario", "dividida" and "sugiéreme" are none.

- ``DESCRIBE``: colours, sizes, ages, simple looks and moods, a few poses ("sleeping",
  "flying": what a picture shows, never a task), simple art styles ("watercolour",
  "realistic", "futuristic"), the seasons and a few festive words used as looks
  ("snowy", "Christmas", "birthday"). Not "pixel art", "ASCII" or any other format.
  Each is written once, in the masculine singular; its other forms are made from it
  (``gen_intent_drawable``):
  "rojo" → roja, rojos, rojas; "rot" → rote, roten …; "красный" → красная, красного …
  Irregular forms follow "/" ("beau/bel/belle/beaux").
- ``GLUE``: articles, "of", "with", "on", "in", "under", "next to", "near", "behind",
  "between", "my", numbers up to ten, "very". Places are built from these and listed nouns ("en la
  playa", "unter dem Baum", "на луне").
- ``AND``: "and", allowed only between two drawable nouns ("un gato y un perro").

Amharic is kept small on purpose (a few colours and sizes) and wants a native review.
"""

from __future__ import annotations

DESCRIBE = {
    "es": """
rojo negro blanco azul/azules verde amarillo morado violeta gris/grises marrón/marrones
dorado plateado rosado celeste multicolor colorido pequeño pequeñito chiquito diminuto
grande/grandes gran enorme gigantesco mini viejo antiguo joven/jóvenes nuevo bonito lindo
hermoso precioso bello adorable tierno feo peludo esponjoso suave brillante oscuro mágico
encantado misterioso majestuoso valiente feroz/feroces salvaje gracioso divertido simpático
amigable feliz/felices alegre triste enojado sonriente dormido sentado alado nevado
futurista realista acuarela otoño invierno primavera verano navidad cumpleaños durmiendo
saltando volando nadando corriendo bailando jugando sonriendo surfeando tocando
""",
    "fr": """
rouge noir blanc/blanche/blancs/blanches bleu vert jaune violet/violette/violets/violettes
gris/grise/grises marron doré argenté rose orange multicolore coloré petit grand
gros/grosse/grosses énorme immense gigantesque minuscule mini géant
vieux/vieil/vieille/vieilles jeune nouveau/nouvel/nouvelle/nouveaux/nouvelles
ancien/ancienne/anciens/anciennes beau/bel/belle/beaux/belles joli
mignon/mignonne/mignons/mignonnes adorable magnifique superbe drôle poilu doux/douce
brillant sombre magique enchanté mystérieux/mystérieuse/mystérieuses
majestueux/majestueuse/majestueuses courageux/courageuse féroce sauvage
gentil/gentille/gentils/gentilles sympa amical/amicale/amicaux heureux/heureuse
joyeux/joyeuse triste fâché souriant endormi assis enneigé ailé futuriste réaliste automne
hiver printemps été aquarelle noël anniversaire dort joue vole nage court saute danse sourit
""",
    "it": """
rosso nero bianco/bianchi/bianche azzurro blu verde giallo viola grigio/grigi marrone dorato
argentato rosa arancione colorato piccolo grande/grandi gran enorme/enormi
gigantesco/giganteschi/gigantesche minuscolo mini grosso vecchio/vecchi
antico/antichi/antiche giovane/giovani nuovo bello/bel/bei/begli carino adorabile/adorabili
simpatico/simpatici/simpatiche magnifico/magnifici/magnifiche splendido strano misterioso
maestoso coraggioso feroce/feroci selvaggio/selvaggi buffo divertente peloso soffice morbido
luminoso scuro magico/magici/magiche incantato felice/felici allegro triste arrabbiato
sorridente addormentato innevato futurista autunno inverno primavera estate seduto alato
tenero realistico/realistici acquerello natale compleanno dorme gioca vola nuota corre salta
balla sorride surfa suona dormendo volando nuotando correndo
""",
    "pt": """
vermelho preto negro branco azul/azuis verde amarelo roxo violeta cinza cinzento marrom
castanho dourado prateado rosa laranja colorido pequeno pequenino grande/grandes enorme
gigante/gigantes gigantesco minúsculo mini velho antigo jovem/jovens novo belo lindo bonito
fofo adorável/adoráveis simpático magnífico estranho misterioso majestoso corajoso
feroz/ferozes selvagem engraçado divertido peludo macio brilhante escuro mágico encantado
feliz/felizes alegre triste zangado sorridente sentado adormecido nevado alado futurista
realista aquarela outono inverno primavera verão natal aniversário dormindo pulando saltando
voando nadando correndo dançando brincando sorrindo surfando tocando
""",
    "de": """
rot schwarz weiß blau grün gelb lila rosa orange braun grau golden silbern bunt klein groß
riesig winzig mini dick alt jung neu süß niedlich hübsch schön lieb freundlich hässlich
flauschig weich glänzend dunkel/dunkle/dunklen/dunkler/dunkles/dunklem magisch verzaubert
geheimnisvoll majestätisch mutig wild lustig fröhlich glücklich traurig wütend lächelnd
schlafend fliegend tanzend springend schwimmend sitzend verschneit verspielt futuristisch
realistisch Herbst Winter Frühling Sommer Aquarell
""",
    "ru": """
красный чёрный белый синий голубой зелёный жёлтый фиолетовый серый коричневый золотой
серебряный розовый оранжевый разноцветный маленький большой огромный крошечный гигантский
старый древний молодой новый милый красивый симпатичный пушистый мягкий яркий тёмный
волшебный заколдованный таинственный величественный храбрый смелый дикий весёлый смешной
забавный счастливый грустный добрый улыбающийся спящий летающий летящий бегущий танцующий
плавающий сидящий заснеженный футуристический осенний зимний весенний летний осенью зимой
весной летом пиратский солнечный реалистичный новогодний рождественский праздничный
воздушный акварелью
""",
    "tr": """
kırmızı siyah kara beyaz mavi yeşil sarı mor gri kahverengi altın gümüş pembe turuncu renkli
rengarenk küçük büyük kocaman minik minicik yaşlı eski genç yeni sevimli tatlı güzel şirin
tüylü yumuşak parlak karanlık büyülü gizemli görkemli cesur vahşi komik neşeli mutlu üzgün
kızgın gülümseyen uyuyan uçan koşan yüzen oturan karlı fütüristik sonbaharda kışın
ilkbaharda yazın gerçekçi suluboya yılbaşı noel doğum günü kardan
""",
    "am": "ቀይ ጥቁር ነጭ ሰማያዊ አረንጓዴ ቢጫ ትንሽ ትልቅ ቆንጆ",
}

GLUE = {
    "es": """
un una unos unas el la los las de del al a en con sobre bajo debajo encima junto lado cerca
entre detrás delante mi mis muy súper super dos tres cuatro cinco seis siete ocho nueve diez
varios varias muchos muchas
""",
    "fr": """
un une des de du d' l' le la les au aux à dans sur sous avec près côté devant derrière entre
en qui mon ma mes très super deux trois quatre cinq six sept huit neuf dix plusieurs
quelques
""",
    "it": """
un uno una un' il lo la l' i gli le di del dello della dell' dei degli delle a al allo alla
all' ai agli alle da dal dalla in nel nello nella nell' nei negli nelle su sul sullo sulla
sull' sui sugli sulle con col sotto sopra accanto vicino tra fra dietro davanti che mio mia
miei mie molto super due tre quattro cinque sei sette otto nove dieci alcuni alcune
""",
    "pt": """
um uma uns umas o a os as de do da dos das em no na nos nas num numa com sob sobre ao à aos
lado perto entre atrás frente meu minha meus minhas muito super dois duas três quatro cinco
seis sete oito nove dez alguns algumas
""",
    "de": """
ein eine einen einem einer eines der die das den dem des mit auf in im am an unter neben
zwischen bei beim vor hinter von vom mein meine meinen meinem meiner sehr super ganz zwei
drei vier fünf sechs sieben acht neun zehn paar viele einige
""",
    "ru": """
в во на с со под над у около рядом возле среди между за перед мой моя моё мои моего моей
моих моим мою очень супер два две три четыре пять шесть семь восемь девять десять двух трёх
четырёх пару несколько нескольких много божья божью божьей
""",
    "tr": """
bir iki üç dört beş altı yedi sekiz dokuz on çok süper ile üstünde üzerinde altında arasında
yanında içinde önünde arkasında kenarında
""",
    "am": "ላይ ውስጥ ጋር",
}

AND = {
    "es": "y e",
    "fr": "et",
    "it": "e ed",
    "pt": "e",
    "de": "und",
    "ru": "и",
    "tr": "ve",
    "am": "እና",
}

# German compounds may start with these besides a listed noun or descriptor
# ("Weihnachtsbaum", "Feuerdrache", "Zauberwald").
GERMAN_LEADS = "weihnacht geburtstag feuer zauber märchen riesen"

# Amharic writes "of", "in" and "from" as a noun's first letter ("የድመት", "በጫካ").
AMHARIC_PREFIXES = "የ በ ከ"
