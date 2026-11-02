# ruff: noqa: RUF001, RUF002 - the words matched are the languages' own
"""What a picture asked in German, Russian, Turkish or Amharic may be of.

As ``gen_intent_drawable_romance``: concrete things only (animals, people and roles,
creatures, objects, vehicles, buildings and places, nature and weather, food, plants,
sky, toys, instruments). Left out with a homework or figurative sense: "Feder" (a
spring), "Kreisel" (a gyroscope), "Birne" (a bulb), "Figur", "Geist", "Krebs"; "поле" (a
field), "труба" (a pipe), "кольцо" (an annulus), "палочка" (a bacillus); "ışık" (light),
"kabuk" (a crust), "araç" (a tool), "makine", "daire" (a circle), "şeker", "kazan".

German: "Katze+n" is "Katze" and "Katzen" ("+e+en" two endings); a "*" noun also ends a
compound ("Feuerdrache", "Leuchtturm", "Segelschiff"); only nouns no abstract compound
ends with are marked, so "Baum", "Pferd" and "Landschaft" are not ("Stammbaum",
"Steckenpferd" and "Medienlandschaft" are no pictures).
Russian: the nominative; its case and plural forms are made from it, and irregular ones
follow "/" ("лев/льва/львы/львов"). Turkish: the bare noun; plural and compound forms
("kediler", "gemisi", "ağacı") are made from it. Amharic: the forms listed, plurals where
sure; the Amharic words want a native speaker's review.
"""

from __future__ import annotations

GERMAN = """
*Katze+n Kätzchen Kater Hund+e+en Hündchen Welpe+n Pferd+e+en Fohlen Pony+s Kuh/Kühe Stier+e
Bulle+n Schwein+e+en Ferkel Schaf+e+en Lamm/Lämmer Ziege+n Huhn/Hühner Henne+n Hahn/Hähne
Küken Ente+n Entchen Gans/Gänse Truthahn Pute+n *Kaninchen Hase+n Häschen Maus/Mäuse Ratte+n
Hamster Meerschweinchen *Eichhörnchen Fuchs/Füchse Wolf/Wölfe Bär+en Eisbär+en Teddybär+en
Waschbär+en Panda+s Koala+s Löwe+n Löwin+nen Tiger Leopard+en Gepard+en Jaguar+e Panther
*Elefant+en *Giraffe+n Zebra+s Affe+n Gorilla+s Schimpanse+n Nilpferd+e Nashorn/Nashörner
Kamel+e Lama+s Alpaka+s Känguru+s Hirsch+e Reh+e Rentier+e Elch+e Esel *Eule+n Uhu+s *Adler
Falke+n *Papagei+en *Pinguin+e Flamingo+s Schwan/Schwäne Pfau+en *Vogel/Vögel/Vögeln Vögelchen
Rabe+n Krähe+n Taube+n Spatz+en Tukan+e Kolibri+s Möwe+n *Schmetterling+e Biene+n Marienkäfer
Libelle+n Spinne+n Ameise+n Schnecke+n Raupe+n Frosch/Frösche Kröte+n *Schildkröte+n
Schlange+n *Krokodil+e Alligator+en *Eidechse+n Chamäleon+s Leguan+e *Fisch+e+en Hai+e Wal+e
Delfin+e Delphin+e Krake+n Oktopus Tintenfisch+e Qualle+n Krabbe+n Hummer Seepferdchen
*Seestern+e Robbe+n Seehund+e Otter Biber Igel Fledermaus/Fledermäuse Faultier+e Haustier+e
Kuscheltier+e Dinosaurier Dino+s
*Drache+n *Einhorn/Einhörner Fee+n Meerjungfrau+en Nixe+n Elf+en Elfe+n Zwerg+e Gnom+e
Riese+n Troll+e Kobold+e Zauberer Zauberin Hexe+n Gespenst+er Vampir+e Werwolf/Werwölfe
Zombie+s Mumie+n Monster Ungeheuer Außerirdische+n Alien+s *Roboter Phönix Greif+en
Zentaur+en Engel Superheld+en Superheldin Ninja+s Pirat+en *Ritter Samurai Wikinger Cowboy+s
Mädchen Junge+n Kind+er+ern Baby+s Frau+en Mann/Männer Dame+n Oma+s Opa+s Großmutter
Großvater König+e Königin+nen Prinz+en Prinzessin+nen Kaiser Kaiserin Krieger Kriegerin
Soldat+en Astronaut+en Astronautin Pilot+en Pilotin Seemann Matrose+n Kapitän+e
Feuerwehrmann Polizist+en Polizistin Arzt/Ärztin Doktor Krankenschwester Koch/Köchin Bauer+n
Bäuerin Fischer Wissenschaftler Maler Musiker Sänger Sängerin Tänzer Tänzerin Ballerina Clown+s
Detektiv+e Entdecker Fußballspieler Schneemann/Schneemänner Weihnachtsmann Vogelscheuche+n
*Puppe+n
Hut/Hüte Mütze+n Kappe+n Krone+n *Regenschirm+e Schirm+e Stuhl/Stühle Sessel Sofa+s Bett+en
Lampe+n *Kerze+n *Laterne+n Tasse+n Becher Teekanne+n Vase+n Flasche+n Korb/Körbe *Geschenk+e
*Luftballon+s Ballon+s Ball/Bälle *Spielzeug+e *Schwert+er Schild+e Ring+e Halskette+n Schuh+e
Stiefel Kleid+er Schal+s Brille+n Sonnenbrille+n Rucksack/Rucksäcke Tasche+n Koffer Kamera+s
Fahne+n Flagge+n Pokal+e Medaille+n Diamant+en Edelstein+e Juwel+en Maske+n
Zauberstab/Zauberstäbe Besen Glocke+n Muschel+n Teddy+s Marionette+n Schaukelpferd+e
*Auto+s Wagen Lastwagen Lkw Bus/Busse Zug/Züge Straßenbahn+en Taxi+s *Flugzeug+e Hubschrauber
Helikopter *Boot+e *Schiff+e Jacht+en Yacht+en Kanu+s U-Boot+e *Rakete+n *Raumschiff+e Ufo+s
*Fahrrad/Fahrräder Motorrad/Motorräder Roller Skateboard+s *Traktor+en Feuerwehrauto+s
Krankenwagen Rennwagen Kutsche+n Schlitten Heißluftballon+s
*Haus/Häuser Häuschen *Hütte+n *Burg+en *Schloss/Schlösser *Palast/Paläste *Turm/Türme
Brücke+n *Kirche+n Kathedrale+n Dom+e Tempel Moschee+n Mühle+n Scheune+n
Bauernhof/Bauernhöfe Iglu+s Zelt+e Wolkenkratzer Stadt/Städte Dorf/Dörfer *Strand/Strände
*Wald/Wälder Dschungel Urwald Wüste+n *Insel+n See+n Fluss/Flüsse *Wasserfall/Wasserfälle
Ozean+e Meer+e Berg+e Gebirge *Vulkan+e Tal/Täler Höhle+n *Wiese+n *Garten/Gärten Park+s
Landschaft+en Schlucht+en Klippe+n Küste+n Hafen/Häfen Ruine+n Zoo+s Aquarium Zirkus Stadion
Schwimmbad
*Sonnenuntergang/Sonnenuntergänge Sonnenaufgang/Sonnenaufgänge *Regenbogen/Regenbögen Wolke+n
Regen Schnee Gewitter Sturm/Stürme Blitz+e Tornado+s Himmel Sternenhimmel Nordlicht+er
Polarlicht+er Baum/Bäume Bäumchen Weihnachtsbaum/Weihnachtsbäume Tannenbaum/Tannenbäume
Apfelbaum/Apfelbäume *Palme+n Tanne+n Eiche+n *Blume+n Rose+n *Sonnenblume+n Tulpe+n
Gänseblümchen Lilie+n Lotus Orchidee+n Kaktus/Kakteen Pilz+e Mond+e Halbmond+e Vollmond
*Sonne+n *Stern+e *Planet+en Komet+en Galaxie+n Schneeflocke+n Eisberg+e
Pizza+s Hamburger Burger Hotdog+s Sandwich+es Sushi Taco+s *Kuchen *Torte+n Cupcake+s Muffin+s
Keks+e Plätzchen Donut+s Krapfen Eis Eiscreme Schokolade+n Bonbon+s Lutscher Croissant+s
Brezel+n Brot+e Brötchen Pfannkuchen Apfel/Äpfel Banane+n Orange+n *Erdbeere+n Kirsche+n
Traube+n Wassermelone+n Melone+n Ananas Zitrone+n Pfirsich+e Avocado+s Karotte+n Möhre+n
Tomate+n Kürbis+se Käse Obst Kaffee
*Gitarre+n Klavier+e Geige+n Violine+n Cello+s *Trommel+n Schlagzeug+e *Trompete+n Flöte+n
Harfe+n Saxophon+e Akkordeon+s Ukulele+n Xylophon+e Tamburin+e
Ast/Äste Weltraum
Leuchtturm/Leuchttürme Flügel Segelboot+e
"""

RUSSIAN = """
кот/кота/коты/котов кошка/кошек котёнок/котёнка/котята/котят котик пёс/пса/псы/псов
собака/собак собачка/собачек щенок/щенка/щенки/щенков/щенята/щенят лошадь/лошадей конь
лошадка/лошадок жеребёнок/жеребёнка пони корова/коров бык свинья/свиней поросёнок/поросёнка
овца/овец ягнёнок/ягнёнка барашек/барашка коза/коз курица/кур петух/петуха цыплёнок/цыплёнка
утка/уток утёнок/утёнка гусь индюк кролик заяц/зайца/зайцы/зайцев зайчик/зайчика мышь
мышка/мышек крыса хомяк белка/белок лиса/лис лисица волк медведь медвежонок/медвежонка
мишка/мишек панда коала лев/льва/львы/львов львица тигр тигрёнок/тигрёнка леопард гепард
ягуар пантера слон слонёнок/слонёнка жираф зебра обезьяна/обезьян горилла шимпанзе орангутан
бегемот носорог верблюд лама альпака кенгуру олень лось осёл/осла/ослы/ослов сова/сов филин
орёл/орла/орлы/орлов сокол попугай пингвин фламинго лебедь павлин птица/птиц птичка/птичек
ворона/ворон ворон голубь воробей/воробья/воробьи/воробьёв тукан колибри чайка/чаек
бабочка/бабочек пчела/пчёл коровка/коровок стрекоза/стрекоз паук муравей/муравья/муравьи/муравьёв
улитка/улиток гусеница лягушка/лягушек жаба/жаб черепаха/черепах змея/змей крокодил аллигатор
ящерица/ящериц хамелеон игуана рыба/рыб рыбка/рыбок акула/акул кит дельфин осьминог кальмар
медуза/медуз краб омар конёк/конька/коньки тюлень морж выдра/выдр бобр/бобра/бобры/бобров
ёж/ежа/ежи/ежей ёжик енот ленивец/ленивца скунс животное/животного/животные/животных
зверь/зверя/звери/зверей зверёк/зверька динозавр питомец/питомца
дракон дракончик единорог фея/фей русалка/русалок эльф гном великан тролль гоблин волшебник
колдун ведьма/ведьм маг чародей/чародея призрак привидение/привидения вампир
оборотень/оборотня/оборотни/оборотней зомби мумия/мумий монстр монстрик чудовище/чудовища
инопланетянин/инопланетянина/инопланетяне/инопланетян пришелец/пришельца/пришельцы/пришельцев
робот киборг феникс грифон пегас кентавр ангел супергерой/супергероя ниндзя пират
рыцарь/рыцаря самурай/самурая викинг ковбой
девочка/девочек мальчик девушка/девушек парень/парня/парни/парней ребёнок/ребёнка/дети/детей
малыш малышка/малышек младенец/младенца женщина/женщин мужчина/мужчин дама/дам
старик/старика старушка/старушек бабушка/бабушек дедушка/дедушек король/короля/короли/королей
королева/королев принц принцесса/принцесс император воин солдат космонавт астронавт пилот
лётчик моряк капитан пожарный/пожарного/пожарные/пожарных
полицейский/полицейского/полицейские/полицейских врач/врача/врачи/врачей доктор/доктора
медсестра/медсестёр повар/повара фермер рыбак/рыбака художник/художника музыкант
певец/певца/певцы/певцов певица танцор танцовщица/танцовщиц балерина/балерин клоун фокусник
детектив путешественник/путешественника футболист снеговик/снеговика пугало кукла/кукол
шляпа/шляп шапка/шапок кепка/кепок корона/корон зонт зонтик стул/стула/стулья/стульев кресло
диван кровать лампа/ламп свеча/свечей фонарь/фонаря чашка/чашек кружка/кружек чайник ваза/ваз
бутылка/бутылок корзина/корзин подарок/подарка/подарки/подарков шарик мяч/мяча
игрушка/игрушек меч/меча щит/щита ожерелье туфля/туфель ботинок/ботинка/ботинки сапог/сапога
платье шарф очки рюкзак сумка/сумок чемодан фотоаппарат флаг кубок медаль алмаз бриллиант
маска/масок метла/метлу котёл/котла колокол колокольчик перо/перья ракушка/ракушек
марионетка/марионеток юла волчок/волчка
машина/машин машинка/машинок автомобиль грузовик автобус поезд/поезда паровоз трамвай такси
самолёт/самолёта вертолёт/вертолёта лодка/лодок подлодка/подлодок корабль/корабля кораблик
парусник яхта/яхт каноэ ракета/ракет звездолёт нло тарелка/тарелок велосипед мотоцикл самокат
скейт скейтборд трактор карета/карет сани санки
дом/дома/домов домик/домика хижина/хижин избушка/избушек замок/замка/замки/замков
дворец/дворца/дворцы/дворцов башня/башен маяк/маяка мост/моста/мосты церковь/церкви собор храм
мечеть мельница/мельниц амбар ферма/ферм иглу палатка/палаток шатёр/шатра небоскрёб
город/города/городов деревня/деревень посёлок/посёлка пляж лес/леса/лесов джунгли
пустыня/пустынь остров/острова/островов озеро/озера/озёр река/рек водопад океан
море/моря/морей гора/гор вулкан долина/долин пещера/пещер луг/луга сад/сада/сады парк пейзаж
каньон скала утёс берег/берега порт гавань руины зоопарк аквариум цирк стадион бассейн
закат/заката/закаты рассвет восход радуга облако/облака/облаков облачко туча/туч дождь/дождя
снег/снега гроза буря молния торнадо ураган небо/неба/небеса сияние дерево/деревья/деревьев
ёлка/ёлок ёлочка пальма/пальм сосна/сосен дуб/дуба цветок/цветка/цветы/цветов
цветочек/цветочка роза/роз подсолнух/подсолнуха тюльпан ромашка/ромашек лилия/лилий лотос
орхидея/орхидей кактус гриб/гриба луна месяц/месяца солнце/солнца звезда/звёзды/звёзд
звёздочка планета/планет комета/комет галактика/галактик туманность снежинка/снежинок айсберг
пицца/пицц бургер гамбургер бутерброд сэндвич суши тако торт/торта тортик
пирожное/пирожного/пирожные/пирожных капкейк печенье/печенек пончик мороженое/мороженого
шоколад конфета/конфет леденец/леденца круассан хлеб/хлеба батон пирог/пирога блин/блинов
яблоко/яблок банан апельсин клубника вишня/вишен черешня виноград арбуз ананас лимон
груша/груш персик авокадо морковь помидор тыква сыр/сыра фрукт кофе
гитара/гитар пианино рояль/рояля скрипка/скрипок виолончель барабан флейта/флейт арфа/арф
саксофон аккордеон баян укулеле ксилофон бубен/бубна
ветка/веток серф космос
шторм крыло/крылья/крыльями/крыльях очки/очках/очками джунгли/джунглях
"""

TURKISH = """
kedi kedicik köpek at tay midilli inek boğa domuz koyun kuzu keçi tavuk horoz civciv ördek
kaz hindi tavşan fare hamster sincap tilki kurt ayı panda koala aslan kaplan leopar çita
jaguar panter fil zürafa zebra maymun goril şempanze orangutan aygır gergedan deve lama
alpaka kanguru geyik eşek baykuş kartal şahin papağan penguen flamingo kuğu kuş serçe karga
güvercin tukan sinekkuşu martı kelebek arı böcek yusufçuk örümcek karınca salyangoz tırtıl
kurbağa kaplumbağa yılan timsah kertenkele bukalemun iguana balık köpekbalığı balina yunus
ahtapot denizanası yengeç ıstakoz denizatı denizyıldızı fok mors samur kunduz kirpi yarasa
rakun kokarca hayvan dinozor yavru
ejderha ejder unicorn peri kız elf cüce dev trol goblin büyücü cadı hayalet vampir zombi
mumya canavar uzaylı robot grifon kentaur melek kahraman ninja korsan şövalye samuray viking
kovboy
çocuk bebek kadın adam nine dede büyükanne büyükbaba kral kraliçe prens prenses imparator
savaşçı asker astronot pilot denizci kaptan itfaiyeci polis doktor hemşire aşçı çiftçi
balıkçı ressam müzisyen şarkıcı dansçı balerin palyaço sihirbaz dedektif kaşif futbolcu
insan noel_baba korkuluk
şapka taç şemsiye sandalye koltuk kanepe yatak lamba mum fener fincan kupa çaydanlık vazo
sepet hediye balon uçurtma top oyuncak kılıç kalkan yüzük kolye ayakkabı çizme elbise atkı
gözlük çanta bavul valiz bayrak madalya elmas mücevher maske asa süpürge çan zil tüy peluş
kukla topaç
araba otomobil kamyon otobüs tren tramvay taksi uçak helikopter tekne gemi yelkenli yat kano
denizaltı roket ufo bisiklet motosiklet kaykay traktör ambulans fayton kızak
ev kulübe şato kale saray kule köprü kilise katedral cami tapınak değirmen ahır çiftlik iglo
çadır gökdelen şehir kasaba köy sahil plaj orman çöl ada göl nehir ırmak şelale okyanus deniz
dağ yanardağ volkan vadi mağara çayır bahçe park manzara kanyon uçurum kıyı liman harabe
akvaryum sirk stadyum havuz
gökkuşağı bulut yağmur kar fırtına şimşek yıldırım kasırga hortum gökyüzü batım ağaç palmiye
çam meşe çiçek gül ayçiçeği lale papatya zambak nilüfer orkide kaktüs mantar ay güneş yıldız
gezegen galaksi bulutsu buzdağı kar_tanesi gün_doğumu
pizza hamburger sandviç suşi tako pasta kek kurabiye bisküvi donut çörek dondurma çikolata
lolipop kruvasan simit ekmek turta krep elma muz portakal çilek kiraz üzüm karpuz ananas limon
armut şeftali avokado havuç domates kabak peynir meyve kahve
gitar piyano keman çello davul bateri trompet flüt arp saksafon akordeon ukulele ksilofon
bağlama saz ud tef
dal uzay gün_batım tek_boynuzlu_at
kanat
kutup_ayı
"""

AMHARIC = """
ድመት ድመቶች ውሻ ውሾች ቡችላ ፈረስ ፈረሶች ላም በሬ አሳማ በግ በጎች ፍየል ዶሮ ዶሮዎች ዳክዬ ጥንቸል አይጥ ቀበሮ ተኩላ ድብ
አንበሳ አንበሶች ነብር ዝሆን ቀጭኔ ጦጣ ዝንጀሮ ጉማሬ አውራሪስ ግመል አህያ የሜዳ_አህያ አጋዘን ወፍ ወፎች ንስር ጉጉት ርግብ
ፔንግዊን በቀቀን ቢራቢሮ ንብ ሸረሪት ጉንዳን እባብ አዞ ኤሊ እንቁራሪት ዓሣ ዓሳ አሳ ሻርክ ዓሣ_ነባሪ ዶልፊን ዳይኖሰር እንስሳ
ዘንዶ ዩኒኮርን መልአክ ጭራቅ ሮቦት ልጅ ልጆች ልጃገረድ ሕፃን ህፃን ሴት ሰው ንጉሥ ንጉስ ንግሥት ንግስት ልዕልት ልዑል ወታደር
ጠፈርተኛ አብራሪ ዶክተር ቤት ቤቶች ግንብ መኪና መኪኖች አውሮፕላን ባቡር መርከብ ጀልባ ብስክሌት ሮኬት ሄሊኮፕተር አውቶቡስ
ዛፍ ዛፎች አበባ አበቦች ጽጌረዳ ተራራ ወንዝ ሐይቅ ሀይቅ ባሕር ባህር ውቅያኖስ ደሴት ጫካ በረሃ ፏፏቴ ሰማይ ደመና ዝናብ በረዶ
ቀስተ_ደመና ጨረቃ ፀሐይ ፀሀይ ጸሐይ ኮከብ ኮከቦች ፕላኔት ሙዝ ፖም ብርቱካን ኬክ ዳቦ ፒዛ ቡና ጊታር ፒያኖ ከበሮ ክራር ማሲንቆ
ዋሽንት ኳስ አሻንጉሊት ኮፍያ ጃንጥላ ዘውድ ሰይፍ ጋሻ ሻማ ወንበር
"""
