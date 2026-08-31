"""Seed ontologies for the Agri Intelligence Lake (V1).

Curated, canonical content — never raw dataset names. This file is the source
of truth; `scripts/seed_lake.py` emits `data/seeds/*.csv` + the DuckDB/Parquet
lakehouse from it, and `domain/catalog.py` builds lookup indexes from it.

NOTE: agro-climatic zones / agro-ecological regions are representative
approximations (primary zone per state) and should be refined with official
ICAR/NBSS&LUP boundaries in a later milestone.
"""

from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# Crops (116 canonical entities; targets 500–1000 as the lake grows)
# ─────────────────────────────────────────────────────────────────────────────
CROPS = [
    # Cereals
    {"crop_id": "CROP_RICE", "canonical_en": "Rice", "scientific_name": "Oryza sativa", "family": "Poaceae", "type": "cereal", "group": "Cereals"},
    {"crop_id": "CROP_WHEAT", "canonical_en": "Wheat", "scientific_name": "Triticum aestivum", "family": "Poaceae", "type": "cereal", "group": "Cereals"},
    {"crop_id": "CROP_MAIZE", "canonical_en": "Maize", "scientific_name": "Zea mays", "family": "Poaceae", "type": "cereal", "group": "Cereals"},
    {"crop_id": "CROP_BARLEY", "canonical_en": "Barley", "scientific_name": "Hordeum vulgare", "family": "Poaceae", "type": "cereal", "group": "Cereals"},
    # Millets
    {"crop_id": "CROP_JOWAR", "canonical_en": "Sorghum (Jowar)", "scientific_name": "Sorghum bicolor", "family": "Poaceae", "type": "millet", "group": "Millets"},
    {"crop_id": "CROP_BAJRA", "canonical_en": "Pearl millet (Bajra)", "scientific_name": "Pennisetum glaucum", "family": "Poaceae", "type": "millet", "group": "Millets"},
    {"crop_id": "CROP_RAGI", "canonical_en": "Finger millet (Ragi)", "scientific_name": "Eleusine coracana", "family": "Poaceae", "type": "millet", "group": "Millets"},
    {"crop_id": "CROP_KODO_MILLET", "canonical_en": "Kodo millet", "scientific_name": "Paspalum scrobiculatum", "family": "Poaceae", "type": "millet", "group": "Millets"},
    {"crop_id": "CROP_LITTLE_MILLET", "canonical_en": "Little millet", "scientific_name": "Panicum sumatrense", "family": "Poaceae", "type": "millet", "group": "Millets"},
    {"crop_id": "CROP_FOXTAIL_MILLET", "canonical_en": "Foxtail millet", "scientific_name": "Setaria italica", "family": "Poaceae", "type": "millet", "group": "Millets"},
    {"crop_id": "CROP_PROSO_MILLET", "canonical_en": "Proso millet", "scientific_name": "Panicum miliaceum", "family": "Poaceae", "type": "millet", "group": "Millets"},
    {"crop_id": "CROP_BARNYARD_MILLET", "canonical_en": "Barnyard millet", "scientific_name": "Echinochloa frumentacea", "family": "Poaceae", "type": "millet", "group": "Millets"},
    # Pulses
    {"crop_id": "CROP_PIGEONPEA", "canonical_en": "Pigeon pea (Tur)", "scientific_name": "Cajanus cajan", "family": "Fabaceae", "type": "pulse", "group": "Pulses"},
    {"crop_id": "CROP_CHICKPEA", "canonical_en": "Chickpea (Gram)", "scientific_name": "Cicer arietinum", "family": "Fabaceae", "type": "pulse", "group": "Pulses"},
    {"crop_id": "CROP_GREENGRAM", "canonical_en": "Green gram (Moong)", "scientific_name": "Vigna radiata", "family": "Fabaceae", "type": "pulse", "group": "Pulses"},
    {"crop_id": "CROP_BLACKGRAM", "canonical_en": "Black gram (Urad)", "scientific_name": "Vigna mungo", "family": "Fabaceae", "type": "pulse", "group": "Pulses"},
    {"crop_id": "CROP_LENTIL", "canonical_en": "Lentil (Masoor)", "scientific_name": "Lens culinaris", "family": "Fabaceae", "type": "pulse", "group": "Pulses"},
    {"crop_id": "CROP_FIELD_PEA", "canonical_en": "Field pea", "scientific_name": "Pisum sativum", "family": "Fabaceae", "type": "pulse", "group": "Pulses"},
    {"crop_id": "CROP_COWPEA", "canonical_en": "Cowpea (Lobia)", "scientific_name": "Vigna unguiculata", "family": "Fabaceae", "type": "pulse", "group": "Pulses"},
    {"crop_id": "CROP_MOTH_BEAN", "canonical_en": "Moth bean", "scientific_name": "Vigna aconitifolia", "family": "Fabaceae", "type": "pulse", "group": "Pulses"},
    {"crop_id": "CROP_HORSE_GRAM", "canonical_en": "Horse gram", "scientific_name": "Macrotyloma uniflorum", "family": "Fabaceae", "type": "pulse", "group": "Pulses"},
    {"crop_id": "CROP_LABLAB", "canonical_en": "Lablab (Field bean)", "scientific_name": "Lablab purpureus", "family": "Fabaceae", "type": "pulse", "group": "Pulses"},
    {"crop_id": "CROP_CLUSTER_BEAN", "canonical_en": "Cluster bean (Guar)", "scientific_name": "Cyamopsis tetragonoloba", "family": "Fabaceae", "type": "pulse", "group": "Pulses"},
    # Oilseeds
    {"crop_id": "CROP_SOYBEAN", "canonical_en": "Soybean", "scientific_name": "Glycine max", "family": "Fabaceae", "type": "oilseed", "group": "Oilseeds"},
    {"crop_id": "CROP_GROUNDNUT", "canonical_en": "Groundnut", "scientific_name": "Arachis hypogaea", "family": "Fabaceae", "type": "oilseed", "group": "Oilseeds"},
    {"crop_id": "CROP_MUSTARD", "canonical_en": "Mustard (Rapeseed)", "scientific_name": "Brassica juncea", "family": "Brassicaceae", "type": "oilseed", "group": "Oilseeds"},
    {"crop_id": "CROP_SESAME", "canonical_en": "Sesame (Til)", "scientific_name": "Sesamum indicum", "family": "Pedaliaceae", "type": "oilseed", "group": "Oilseeds"},
    {"crop_id": "CROP_SUNFLOWER", "canonical_en": "Sunflower", "scientific_name": "Helianthus annuus", "family": "Asteraceae", "type": "oilseed", "group": "Oilseeds"},
    {"crop_id": "CROP_SAFFLOWER", "canonical_en": "Safflower", "scientific_name": "Carthamus tinctorius", "family": "Asteraceae", "type": "oilseed", "group": "Oilseeds"},
    {"crop_id": "CROP_LINSEED", "canonical_en": "Linseed (Flax)", "scientific_name": "Linum usitatissimum", "family": "Linaceae", "type": "oilseed", "group": "Oilseeds"},
    {"crop_id": "CROP_CASTOR", "canonical_en": "Castor", "scientific_name": "Ricinus communis", "family": "Euphorbiaceae", "type": "oilseed", "group": "Oilseeds"},
    {"crop_id": "CROP_NIGER", "canonical_en": "Niger", "scientific_name": "Guizotia abyssinica", "family": "Asteraceae", "type": "oilseed", "group": "Oilseeds"},
    # Fibre crops
    {"crop_id": "CROP_COTTON", "canonical_en": "Cotton", "scientific_name": "Gossypium hirsutum", "family": "Malvaceae", "type": "fibre", "group": "Fibre crops"},
    {"crop_id": "CROP_JUTE", "canonical_en": "Jute", "scientific_name": "Corchorus olitorius", "family": "Malvaceae", "type": "fibre", "group": "Fibre crops"},
    {"crop_id": "CROP_MESTA", "canonical_en": "Mesta (Kenaf)", "scientific_name": "Hibiscus spp.", "family": "Malvaceae", "type": "fibre", "group": "Fibre crops"},
    # Sugar crops
    {"crop_id": "CROP_SUGARCANE", "canonical_en": "Sugarcane", "scientific_name": "Saccharum officinarum", "family": "Poaceae", "type": "sugar", "group": "Sugar crops"},
    {"crop_id": "CROP_SUGARBEET", "canonical_en": "Sugar beet", "scientific_name": "Beta vulgaris", "family": "Amaranthaceae", "type": "sugar", "group": "Sugar crops"},
    # Vegetables
    {"crop_id": "CROP_ONION", "canonical_en": "Onion", "scientific_name": "Allium cepa", "family": "Amaryllidaceae", "type": "vegetable", "group": "Vegetables"},
    {"crop_id": "CROP_TOMATO", "canonical_en": "Tomato", "scientific_name": "Solanum lycopersicum", "family": "Solanaceae", "type": "vegetable", "group": "Vegetables"},
    {"crop_id": "CROP_POTATO", "canonical_en": "Potato", "scientific_name": "Solanum tuberosum", "family": "Solanaceae", "type": "vegetable", "group": "Vegetables"},
    {"crop_id": "CROP_CHILLI", "canonical_en": "Chilli", "scientific_name": "Capsicum annuum", "family": "Solanaceae", "type": "vegetable", "group": "Vegetables"},
    {"crop_id": "CROP_BRINJAL", "canonical_en": "Brinjal (Eggplant)", "scientific_name": "Solanum melongena", "family": "Solanaceae", "type": "vegetable", "group": "Vegetables"},
    {"crop_id": "CROP_OKRA", "canonical_en": "Okra (Bhindi)", "scientific_name": "Abelmoschus esculentus", "family": "Malvaceae", "type": "vegetable", "group": "Vegetables"},
    {"crop_id": "CROP_CAULIFLOWER", "canonical_en": "Cauliflower", "scientific_name": "Brassica oleracea var. botrytis", "family": "Brassicaceae", "type": "vegetable", "group": "Vegetables"},
    {"crop_id": "CROP_CABBAGE", "canonical_en": "Cabbage", "scientific_name": "Brassica oleracea var. capitata", "family": "Brassicaceae", "type": "vegetable", "group": "Vegetables"},
    {"crop_id": "CROP_CUCUMBER", "canonical_en": "Cucumber", "scientific_name": "Cucumis sativus", "family": "Cucurbitaceae", "type": "vegetable", "group": "Vegetables"},
    {"crop_id": "CROP_BITTER_GOURD", "canonical_en": "Bitter gourd", "scientific_name": "Momordica charantia", "family": "Cucurbitaceae", "type": "vegetable", "group": "Vegetables"},
    {"crop_id": "CROP_BOTTLE_GOURD", "canonical_en": "Bottle gourd", "scientific_name": "Lagenaria siceraria", "family": "Cucurbitaceae", "type": "vegetable", "group": "Vegetables"},
    {"crop_id": "CROP_RIDGE_GOURD", "canonical_en": "Ridge gourd", "scientific_name": "Luffa acutangula", "family": "Cucurbitaceae", "type": "vegetable", "group": "Vegetables"},
    {"crop_id": "CROP_PUMPKIN", "canonical_en": "Pumpkin", "scientific_name": "Cucurbita moschata", "family": "Cucurbitaceae", "type": "vegetable", "group": "Vegetables"},
    {"crop_id": "CROP_DRUMSTICK", "canonical_en": "Drumstick (Moringa)", "scientific_name": "Moringa oleifera", "family": "Moringaceae", "type": "vegetable", "group": "Vegetables"},
    # Leafy vegetables
    {"crop_id": "CROP_SPINACH", "canonical_en": "Spinach (Palak)", "scientific_name": "Spinacia oleracea", "family": "Amaranthaceae", "type": "leafy_vegetable", "group": "Leafy vegetables"},
    {"crop_id": "CROP_AMARANTH", "canonical_en": "Amaranth", "scientific_name": "Amaranthus spp.", "family": "Amaranthaceae", "type": "leafy_vegetable", "group": "Leafy vegetables"},
    {"crop_id": "CROP_FENUGREEK", "canonical_en": "Fenugreek (Methi)", "scientific_name": "Trigonella foenum-graecum", "family": "Fabaceae", "type": "leafy_vegetable", "group": "Leafy vegetables"},
    {"crop_id": "CROP_MINT", "canonical_en": "Mint (Pudina)", "scientific_name": "Mentha spicata", "family": "Lamiaceae", "type": "leafy_vegetable", "group": "Leafy vegetables"},
    # Root vegetables
    {"crop_id": "CROP_CARROT", "canonical_en": "Carrot", "scientific_name": "Daucus carota", "family": "Apiaceae", "type": "root_vegetable", "group": "Root vegetables"},
    {"crop_id": "CROP_RADISH", "canonical_en": "Radish", "scientific_name": "Raphanus sativus", "family": "Brassicaceae", "type": "root_vegetable", "group": "Root vegetables"},
    {"crop_id": "CROP_SWEET_POTATO", "canonical_en": "Sweet potato", "scientific_name": "Ipomoea batatas", "family": "Convolvulaceae", "type": "root_vegetable", "group": "Root vegetables"},
    {"crop_id": "CROP_TARO", "canonical_en": "Taro (Arbi)", "scientific_name": "Colocasia esculenta", "family": "Araceae", "type": "root_vegetable", "group": "Root vegetables"},
    {"crop_id": "CROP_CASSAVA", "canonical_en": "Cassava (Tapioca)", "scientific_name": "Manihot esculenta", "family": "Euphorbiaceae", "type": "root_vegetable", "group": "Root vegetables"},
    {"crop_id": "CROP_YAM", "canonical_en": "Yam", "scientific_name": "Dioscorea spp.", "family": "Dioscoreaceae", "type": "root_vegetable", "group": "Root vegetables"},
    # Fruits
    {"crop_id": "CROP_BANANA", "canonical_en": "Banana", "scientific_name": "Musa paradisiaca", "family": "Musaceae", "type": "fruit", "group": "Fruits"},
    {"crop_id": "CROP_MANGO", "canonical_en": "Mango", "scientific_name": "Mangifera indica", "family": "Anacardiaceae", "type": "fruit", "group": "Fruits"},
    {"crop_id": "CROP_ORANGE", "canonical_en": "Orange", "scientific_name": "Citrus sinensis", "family": "Rutaceae", "type": "fruit", "group": "Fruits"},
    {"crop_id": "CROP_LEMON", "canonical_en": "Lemon", "scientific_name": "Citrus limon", "family": "Rutaceae", "type": "fruit", "group": "Fruits"},
    {"crop_id": "CROP_POMEGRANATE", "canonical_en": "Pomegranate", "scientific_name": "Punica granatum", "family": "Lythraceae", "type": "fruit", "group": "Fruits"},
    {"crop_id": "CROP_GRAPES", "canonical_en": "Grapes", "scientific_name": "Vitis vinifera", "family": "Vitaceae", "type": "fruit", "group": "Fruits"},
    {"crop_id": "CROP_GUAVA", "canonical_en": "Guava", "scientific_name": "Psidium guajava", "family": "Myrtaceae", "type": "fruit", "group": "Fruits"},
    {"crop_id": "CROP_PAPAYA", "canonical_en": "Papaya", "scientific_name": "Carica papaya", "family": "Caricaceae", "type": "fruit", "group": "Fruits"},
    {"crop_id": "CROP_APPLE", "canonical_en": "Apple", "scientific_name": "Malus domestica", "family": "Rosaceae", "type": "fruit", "group": "Fruits"},
    {"crop_id": "CROP_SAPOTA", "canonical_en": "Sapota (Chikoo)", "scientific_name": "Manilkara zapota", "family": "Sapotaceae", "type": "fruit", "group": "Fruits"},
    {"crop_id": "CROP_CUSTARD_APPLE", "canonical_en": "Custard apple", "scientific_name": "Annona squamosa", "family": "Annonaceae", "type": "fruit", "group": "Fruits"},
    {"crop_id": "CROP_JACKFRUIT", "canonical_en": "Jackfruit", "scientific_name": "Artocarpus heterophyllus", "family": "Moraceae", "type": "fruit", "group": "Fruits"},
    {"crop_id": "CROP_PINEAPPLE", "canonical_en": "Pineapple", "scientific_name": "Ananas comosus", "family": "Bromeliaceae", "type": "fruit", "group": "Fruits"},
    {"crop_id": "CROP_BER", "canonical_en": "Ber (Indian jujube)", "scientific_name": "Ziziphus mauritiana", "family": "Rhamnaceae", "type": "fruit", "group": "Fruits"},
    {"crop_id": "CROP_AMLA", "canonical_en": "Amla (Gooseberry)", "scientific_name": "Phyllanthus emblica", "family": "Phyllanthaceae", "type": "fruit", "group": "Fruits"},
    {"crop_id": "CROP_DATE_PALM", "canonical_en": "Date palm", "scientific_name": "Phoenix dactylifera", "family": "Arecaceae", "type": "fruit", "group": "Fruits"},
    {"crop_id": "CROP_MUSKMELON", "canonical_en": "Muskmelon", "scientific_name": "Cucumis melo", "family": "Cucurbitaceae", "type": "fruit", "group": "Fruits"},
    {"crop_id": "CROP_WATERMELON", "canonical_en": "Watermelon", "scientific_name": "Citrullus lanatus", "family": "Cucurbitaceae", "type": "fruit", "group": "Fruits"},
    # Flowers
    {"crop_id": "CROP_MARIGOLD", "canonical_en": "Marigold", "scientific_name": "Tagetes erecta", "family": "Asteraceae", "type": "flower", "group": "Flowers"},
    {"crop_id": "CROP_ROSE", "canonical_en": "Rose", "scientific_name": "Rosa spp.", "family": "Rosaceae", "type": "flower", "group": "Flowers"},
    {"crop_id": "CROP_JASMINE", "canonical_en": "Jasmine", "scientific_name": "Jasminum spp.", "family": "Oleaceae", "type": "flower", "group": "Flowers"},
    # Spices
    {"crop_id": "CROP_TURMERIC", "canonical_en": "Turmeric", "scientific_name": "Curcuma longa", "family": "Zingiberaceae", "type": "spice", "group": "Spices"},
    {"crop_id": "CROP_GINGER", "canonical_en": "Ginger", "scientific_name": "Zingiber officinale", "family": "Zingiberaceae", "type": "spice", "group": "Spices"},
    {"crop_id": "CROP_GARLIC", "canonical_en": "Garlic", "scientific_name": "Allium sativum", "family": "Amaryllidaceae", "type": "spice", "group": "Spices"},
    {"crop_id": "CROP_CORIANDER", "canonical_en": "Coriander", "scientific_name": "Coriandrum sativum", "family": "Apiaceae", "type": "spice", "group": "Spices"},
    {"crop_id": "CROP_CUMIN", "canonical_en": "Cumin", "scientific_name": "Cuminum cyminum", "family": "Apiaceae", "type": "spice", "group": "Spices"},
    {"crop_id": "CROP_FENNEL", "canonical_en": "Fennel", "scientific_name": "Foeniculum vulgare", "family": "Apiaceae", "type": "spice", "group": "Spices"},
    {"crop_id": "CROP_BLACK_PEPPER", "canonical_en": "Black pepper", "scientific_name": "Piper nigrum", "family": "Piperaceae", "type": "spice", "group": "Spices"},
    {"crop_id": "CROP_CARDAMOM", "canonical_en": "Cardamom", "scientific_name": "Elettaria cardamomum", "family": "Zingiberaceae", "type": "spice", "group": "Spices"},
    {"crop_id": "CROP_NUTMEG", "canonical_en": "Nutmeg", "scientific_name": "Myristica fragrans", "family": "Myristicaceae", "type": "spice", "group": "Spices"},
    {"crop_id": "CROP_CLOVE", "canonical_en": "Clove", "scientific_name": "Syzygium aromaticum", "family": "Myrtaceae", "type": "spice", "group": "Spices"},
    {"crop_id": "CROP_CINNAMON", "canonical_en": "Cinnamon", "scientific_name": "Cinnamomum verum", "family": "Lauraceae", "type": "spice", "group": "Spices"},
    {"crop_id": "CROP_SAFFRON", "canonical_en": "Saffron", "scientific_name": "Crocus sativus", "family": "Iridaceae", "type": "spice", "group": "Spices"},
    # Plantation crops
    {"crop_id": "CROP_TEA", "canonical_en": "Tea", "scientific_name": "Camellia sinensis", "family": "Theaceae", "type": "plantation", "group": "Plantation crops"},
    {"crop_id": "CROP_COFFEE", "canonical_en": "Coffee", "scientific_name": "Coffea arabica", "family": "Rubiaceae", "type": "plantation", "group": "Plantation crops"},
    {"crop_id": "CROP_COCONUT", "canonical_en": "Coconut", "scientific_name": "Cocos nucifera", "family": "Arecaceae", "type": "plantation", "group": "Plantation crops"},
    {"crop_id": "CROP_ARECANUT", "canonical_en": "Arecanut", "scientific_name": "Areca catechu", "family": "Arecaceae", "type": "plantation", "group": "Plantation crops"},
    {"crop_id": "CROP_CASHEW", "canonical_en": "Cashew", "scientific_name": "Anacardium occidentale", "family": "Anacardiaceae", "type": "plantation", "group": "Plantation crops"},
    {"crop_id": "CROP_RUBBER", "canonical_en": "Rubber", "scientific_name": "Hevea brasiliensis", "family": "Euphorbiaceae", "type": "plantation", "group": "Plantation crops"},
    {"crop_id": "CROP_OIL_PALM", "canonical_en": "Oil palm", "scientific_name": "Elaeis guineensis", "family": "Arecaceae", "type": "plantation", "group": "Plantation crops"},
    {"crop_id": "CROP_COCOA", "canonical_en": "Cocoa", "scientific_name": "Theobroma cacao", "family": "Malvaceae", "type": "plantation", "group": "Plantation crops"},
    # Medicinal plants
    {"crop_id": "CROP_ASHWAGANDHA", "canonical_en": "Ashwagandha", "scientific_name": "Withania somnifera", "family": "Solanaceae", "type": "medicinal", "group": "Medicinal plants"},
    {"crop_id": "CROP_ALOEVERA", "canonical_en": "Aloe vera", "scientific_name": "Aloe barbadensis", "family": "Asphodelaceae", "type": "medicinal", "group": "Medicinal plants"},
    {"crop_id": "CROP_TULSI", "canonical_en": "Tulsi (Holy basil)", "scientific_name": "Ocimum sanctum", "family": "Lamiaceae", "type": "medicinal", "group": "Medicinal plants"},
    {"crop_id": "CROP_ISABGOL", "canonical_en": "Isabgol", "scientific_name": "Plantago ovata", "family": "Plantaginaceae", "type": "medicinal", "group": "Medicinal plants"},
    # Aromatic plants
    {"crop_id": "CROP_LEMONGRASS", "canonical_en": "Lemongrass", "scientific_name": "Cymbopogon citratus", "family": "Poaceae", "type": "aromatic", "group": "Aromatic plants"},
    {"crop_id": "CROP_CITRONELLA", "canonical_en": "Citronella", "scientific_name": "Cymbopogon winterianus", "family": "Poaceae", "type": "aromatic", "group": "Aromatic plants"},
    # Fodder crops
    {"crop_id": "CROP_BERSEEM", "canonical_en": "Berseem", "scientific_name": "Trifolium alexandrinum", "family": "Fabaceae", "type": "fodder", "group": "Fodder crops"},
    {"crop_id": "CROP_LUCERNE", "canonical_en": "Lucerne (Alfalfa)", "scientific_name": "Medicago sativa", "family": "Fabaceae", "type": "fodder", "group": "Fodder crops"},
    {"crop_id": "CROP_NAPIER_GRASS", "canonical_en": "Napier grass", "scientific_name": "Pennisetum purpureum", "family": "Poaceae", "type": "fodder", "group": "Fodder crops"},
    {"crop_id": "CROP_OATS", "canonical_en": "Oats", "scientific_name": "Avena sativa", "family": "Poaceae", "type": "fodder", "group": "Fodder crops"},
    # Forest / agroforestry species
    {"crop_id": "CROP_BAMBOO", "canonical_en": "Bamboo", "scientific_name": "Bambusa spp.", "family": "Poaceae", "type": "tree", "group": "Forest/Agroforestry species"},
    {"crop_id": "CROP_NEEM", "canonical_en": "Neem", "scientific_name": "Azadirachta indica", "family": "Meliaceae", "type": "tree", "group": "Forest/Agroforestry species"},
    {"crop_id": "CROP_POPLAR", "canonical_en": "Poplar", "scientific_name": "Populus spp.", "family": "Salicaceae", "type": "tree", "group": "Forest/Agroforestry species"},
    {"crop_id": "CROP_EUCALYPTUS", "canonical_en": "Eucalyptus", "scientific_name": "Eucalyptus spp.", "family": "Myrtaceae", "type": "tree", "group": "Forest/Agroforestry species"},
]

# Indian-language aliases (en + 11 Indian languages). Seed subset for the
# highest-frequency crops; extend to all crops over time.
CROP_ALIASES = {
    "CROP_RICE": {"en": "Rice", "hi": "धान", "mr": "भात", "gu": "ડાંગર", "pa": "ਝੋਨਾ", "bn": "ধান", "od": "ଧାନ", "ta": "நெல்", "te": "వరి", "kn": "ಭತ್ತ", "ml": "നെല്ല്", "as": "ধান"},
    "CROP_WHEAT": {"en": "Wheat", "hi": "गेहूं", "mr": "गहू", "gu": "ઘઉં", "pa": "ਕਣਕ", "bn": "গম", "od": "ଗହମ", "ta": "கோதுமை", "te": "గోధుమ", "kn": "ಗೋಧಿ", "ml": "ഗോതമ്പ്", "as": "ঘেঁহু"},
    "CROP_MAIZE": {"en": "Maize", "hi": "मक्का", "mr": "मका", "gu": "મકાઈ", "pa": "ਮੱਕੀ", "bn": "ভুট্টা", "od": "ମକା", "ta": "மக்காச்சோளம்", "te": "మొక్కజొన్న", "kn": "ಮೆಕ್ಕೆಜೋಳ", "ml": "ചോളം", "as": "মাকৈ"},
    "CROP_JOWAR": {"en": "Jowar", "hi": "ज्वार", "mr": "ज्वारी", "gu": "જુવાર", "pa": "ਜਵਾਰ", "bn": "জোয়ার", "od": "ଜୁଆର", "ta": "சோளம்", "te": "జొన్న", "kn": "ಜೋಳ", "ml": "ജോവർ", "as": "জোৱাৰ"},
    "CROP_BAJRA": {"en": "Bajra", "hi": "बाजरा", "mr": "बाजरी", "gu": "બાજરી", "pa": "ਬਾਜਰਾ", "bn": "বাজরা", "od": "ବାଜରା", "ta": "கம்பு", "te": "సజ్జ", "kn": "ಸಜ್ಜೆ", "ml": "ബജ്റ", "as": "বজৰা"},
    "CROP_RAGI": {"en": "Ragi", "hi": "रागी", "mr": "नाचणी", "gu": "નાગલી", "pa": "ਰਾਗੀ", "bn": "রাগি", "od": "ମାଣ୍ଡିଆ", "ta": "கேழ்வரகு", "te": "రాగి", "kn": "ರಾಗಿ", "ml": "പഞ്ഞപ്പുല്ല്", "as": "ৰাগি"},
    "CROP_PIGEONPEA": {"en": "Tur", "hi": "अरहर", "mr": "तूर", "gu": "તુવેર", "pa": "ਅਰਹਰ", "bn": "অড়হর", "od": "ହରଡ", "ta": "துவரை", "te": "కంది", "kn": "ತೊಗರಿ", "ml": "തുവര", "as": "ৰহৰ"},
    "CROP_CHICKPEA": {"en": "Gram", "hi": "चना", "mr": "हरभरा", "gu": "ચણા", "pa": "ਛੋਲੇ", "bn": "ছোলা", "od": "ବୁଟ", "ta": "கொண்டைக்கடலை", "te": "శనగలు", "kn": "ಕಡಲೆ", "ml": "കടല", "as": "বুট"},
    "CROP_GREENGRAM": {"en": "Moong", "hi": "मूंग", "mr": "मूग", "gu": "મગ", "pa": "ਮੂੰਗੀ", "bn": "মুগ", "od": "ମୁଗ", "ta": "பாசிப்பயறு", "te": "పెసలు", "kn": "ಹೆಸರು", "ml": "ചെറുപയർ", "as": "মগু"},
    "CROP_BLACKGRAM": {"en": "Urad", "hi": "उड़द", "mr": "उडीद", "gu": "અડદ", "pa": "ਮਾਹਾਂ", "bn": "মাসকলাই", "od": "ବିରି", "ta": "உளுந்து", "te": "మినుములు", "kn": "ಉದ್ದು", "ml": "ഉഴുന്ന്", "as": "মাটিমাহ"},
    "CROP_SOYBEAN": {"en": "Soybean", "hi": "सोयाबीन", "mr": "सोयाबीन", "gu": "સોયાબીન", "pa": "ਸੋਇਆਬੀਨ", "bn": "সয়াবিন", "od": "ସୋୟାବିନ", "ta": "சோயா", "te": "సోయా", "kn": "ಸೋಯಾಬೀನ್", "ml": "സോയാബീൻ", "as": "চয়াবীন"},
    "CROP_GROUNDNUT": {"en": "Groundnut", "hi": "मूंगफली", "mr": "भुईमूग", "gu": "મગફળી", "pa": "ਮੂੰਗਫਲੀ", "bn": "চিনাবাদাম", "od": "ଚିନାବାଦାମ", "ta": "நிலக்கடலை", "te": "వేరుశనగ", "kn": "ಕಡಲೆಕಾಯಿ", "ml": "കപ്പലണ്ടി", "as": "বাদাম"},
    "CROP_MUSTARD": {"en": "Mustard", "hi": "सरसों", "mr": "मोहरी", "gu": "રાઈ", "pa": "ਸਰ੍ਹੋਂ", "bn": "সরিষা", "od": "ସୋରିଷ", "ta": "கடுகு", "te": "ఆవాలు", "kn": "ಸಾಸಿವೆ", "ml": "കടുക്", "as": "সৰিয়হ"},
    "CROP_COTTON": {"en": "Cotton", "hi": "कपास", "mr": "कापूस", "gu": "કપાસ", "pa": "ਕਪਾਹ", "bn": "তুলো", "od": "କପା", "ta": "பருத்தி", "te": "పత్తి", "kn": "ಹತ್ತಿ", "ml": "പരുത്തി", "as": "কপাহ"},
    "CROP_SUGARCANE": {"en": "Sugarcane", "hi": "गन्ना", "mr": "ऊस", "gu": "શેરડી", "pa": "ਗੰਨਾ", "bn": "আখ", "od": "ଆଖୁ", "ta": "கரும்பு", "te": "చెరకు", "kn": "ಕಬ್ಬು", "ml": "കരിമ്പ്", "as": "কুঁহিয়াৰ"},
    "CROP_ONION": {"en": "Onion", "hi": "प्याज", "mr": "कांदा", "gu": "ડુંગળી", "pa": "ਪਿਆਜ਼", "bn": "পেঁয়াজ", "od": "ପିଆଜ", "ta": "வெங்காயம்", "te": "ఉల్లిపాయ", "kn": "ಈರುಳ್ಳಿ", "ml": "ഉള്ളി", "as": "পিয়াজ"},
    "CROP_TOMATO": {"en": "Tomato", "hi": "टमाटर", "mr": "टोमॅटो", "gu": "ટામેટું", "pa": "ਟਮਾਟਰ", "bn": "টমেটো", "od": "ଟମାଟୋ", "ta": "தக்காளி", "te": "టమాట", "kn": "ಟೊಮೇಟೊ", "ml": "തക്കാളി", "as": "বিলাহী"},
    "CROP_POTATO": {"en": "Potato", "hi": "आलू", "mr": "बटाटा", "gu": "બટાકા", "pa": "ਆਲੂ", "bn": "আলু", "od": "ଆଳୁ", "ta": "உருளைக்கிழங்கு", "te": "బంగాళాదుంప", "kn": "ಆಲೂಗಡ್ಡೆ", "ml": "ഉരുളക്കിഴങ്ങ്", "as": "আলু"},
    "CROP_CHILLI": {"en": "Chilli", "hi": "मिर्च", "mr": "मिरची", "gu": "મરચું", "pa": "ਮਿਰਚ", "bn": "লঙ্কা", "od": "ଲଙ୍କା", "ta": "மிளகாய்", "te": "మిరప", "kn": "ಮೆಣಸಿನಕಾಯಿ", "ml": "മുളക്", "as": "জলকীয়া"},
    "CROP_BRINJAL": {"en": "Brinjal", "hi": "बैंगन", "mr": "वांगी", "gu": "રીંગણ", "pa": "ਬੈਂਗਣ", "bn": "বেগুন", "od": "ବାଇଗଣ", "ta": "கத்தரி", "te": "వంకాయ", "kn": "ಬದನೆ", "ml": "വഴുതന", "as": "বেঙেনা"},
    "CROP_OKRA": {"en": "Okra", "hi": "भिंडी", "mr": "भेंडी", "gu": "ભીંડા", "pa": "ਭਿੰਡੀ", "bn": "ঢেঁড়স", "od": "ଭେଣ୍ଡି", "ta": "வெண்டை", "te": "బెండకాయ", "kn": "ಬೆಂಡೆಕಾಯಿ", "ml": "വെണ്ടയ്ക്ക", "as": "ভেন্দি"},
    "CROP_BANANA": {"en": "Banana", "hi": "केला", "mr": "केळ", "gu": "કેળું", "pa": "ਕੇਲਾ", "bn": "কলা", "od": "କଦଳୀ", "ta": "வாழை", "te": "అరటి", "kn": "ಬಾಳೆ", "ml": "വാഴ", "as": "কল"},
    "CROP_MANGO": {"en": "Mango", "hi": "आम", "mr": "आंबा", "gu": "કેરી", "pa": "ਅੰਬ", "bn": "আম", "od": "ଆମ୍ବ", "ta": "மாம்பழம்", "te": "మామిడి", "kn": "ಮಾವು", "ml": "മാങ്ങ", "as": "আম"},
}

# Additional romanized / common-English aliases (dataset spellings, anglicisms).
EXTRA_ALIASES = {
    "paddy": "CROP_RICE",
    "dhan": "CROP_RICE",
    "arhar": "CROP_PIGEONPEA",
    "toor": "CROP_PIGEONPEA",
    "red gram": "CROP_PIGEONPEA",
    "chana": "CROP_CHICKPEA",
    "bengal gram": "CROP_CHICKPEA",
    "sorghum": "CROP_JOWAR",
    "pearl millet": "CROP_BAJRA",
    "finger millet": "CROP_RAGI",
    "corn": "CROP_MAIZE",
    "peanut": "CROP_GROUNDNUT",
    "soya": "CROP_SOYBEAN",
    "rapeseed": "CROP_MUSTARD",
    "til": "CROP_SESAME",
    "sesamum": "CROP_SESAME",
    "bhindi": "CROP_OKRA",
    "ladyfinger": "CROP_OKRA",
    "eggplant": "CROP_BRINJAL",
    "aubergine": "CROP_BRINJAL",
}

# ─────────────────────────────────────────────────────────────────────────────
# Geography: 36 states/UTs + representative districts
# (agro-climatic zone = primary zone; agro-ecological region import = V2/NBSS&LUP)
# ─────────────────────────────────────────────────────────────────────────────
GEOGRAPHY = [
    {"state_code": "IN-AP", "name": "Andhra Pradesh", "type": "state", "agroclimatic_zone": "East Coast Plains and Hills", "agroecological_region": None, "districts": [
        {"code": "IN-AP-ANANTAPUR", "name": "Anantapur"}, {"code": "IN-AP-CHITTOOR", "name": "Chittoor"},
        {"code": "IN-AP-GUNTUR", "name": "Guntur"}, {"code": "IN-AP-KRISHNA", "name": "Krishna"},
        {"code": "IN-AP-KURNOOL", "name": "Kurnool"}, {"code": "IN-AP-WGODAVARI", "name": "West Godavari"}]},
    {"state_code": "IN-AR", "name": "Arunachal Pradesh", "type": "state", "agroclimatic_zone": "Eastern Himalayan Region", "agroecological_region": None, "districts": [
        {"code": "IN-AR-WKAMENG", "name": "West Kameng"}, {"code": "IN-AR-PAPUMPARE", "name": "Papum Pare"}]},
    {"state_code": "IN-AS", "name": "Assam", "type": "state", "agroclimatic_zone": "Eastern Himalayan Region", "agroecological_region": None, "districts": [
        {"code": "IN-AS-NAGAON", "name": "Nagaon"}, {"code": "IN-AS-JORHAT", "name": "Jorhat"},
        {"code": "IN-AS-DIBRUGARH", "name": "Dibrugarh"}, {"code": "IN-AS-BARPETA", "name": "Barpeta"}]},
    {"state_code": "IN-BR", "name": "Bihar", "type": "state", "agroclimatic_zone": "Middle Gangetic Plains", "agroecological_region": None, "districts": [
        {"code": "IN-BR-PATNA", "name": "Patna"}, {"code": "IN-BR-MUZAFFARPUR", "name": "Muzaffarpur"},
        {"code": "IN-BR-SAMASTIPUR", "name": "Samastipur"}, {"code": "IN-BR-PURNIA", "name": "Purnia"},
        {"code": "IN-BR-ROHTAS", "name": "Rohtas"}]},
    {"state_code": "IN-CT", "name": "Chhattisgarh", "type": "state", "agroclimatic_zone": "Eastern Plateau and Hills", "agroecological_region": None, "districts": [
        {"code": "IN-CT-RAIPUR", "name": "Raipur"}, {"code": "IN-CT-DURG", "name": "Durg"},
        {"code": "IN-CT-RAJNANDGAON", "name": "Rajnandgaon"}, {"code": "IN-CT-BASTAR", "name": "Bastar"}]},
    {"state_code": "IN-GA", "name": "Goa", "type": "state", "agroclimatic_zone": "West Coast Plains and Ghats", "agroecological_region": None, "districts": [
        {"code": "IN-GA-NORTH", "name": "North Goa"}, {"code": "IN-GA-SOUTH", "name": "South Goa"}]},
    {"state_code": "IN-GJ", "name": "Gujarat", "type": "state", "agroclimatic_zone": "Gujarat Plains and Hills", "agroecological_region": None, "districts": [
        {"code": "IN-GJ-AHMEDABAD", "name": "Ahmedabad"}, {"code": "IN-GJ-BANASKANTHA", "name": "Banaskantha"},
        {"code": "IN-GJ-JUNAGADH", "name": "Junagadh"}, {"code": "IN-GJ-RAJKOT", "name": "Rajkot"},
        {"code": "IN-GJ-MEHSANA", "name": "Mehsana"}, {"code": "IN-GJ-BHAVNAGAR", "name": "Bhavnagar"}]},
    {"state_code": "IN-HR", "name": "Haryana", "type": "state", "agroclimatic_zone": "Trans-Gangetic Plains", "agroecological_region": None, "districts": [
        {"code": "IN-HR-KARNAL", "name": "Karnal"}, {"code": "IN-HR-HISAR", "name": "Hisar"},
        {"code": "IN-HR-SIRSA", "name": "Sirsa"}, {"code": "IN-HR-KAITHAL", "name": "Kaithal"},
        {"code": "IN-HR-SONIPAT", "name": "Sonipat"}]},
    {"state_code": "IN-HP", "name": "Himachal Pradesh", "type": "state", "agroclimatic_zone": "Western Himalayan Region", "agroecological_region": None, "districts": [
        {"code": "IN-HP-KANGRA", "name": "Kangra"}, {"code": "IN-HP-MANDI", "name": "Mandi"},
        {"code": "IN-HP-SHIMLA", "name": "Shimla"}]},
    {"state_code": "IN-JH", "name": "Jharkhand", "type": "state", "agroclimatic_zone": "Eastern Plateau and Hills", "agroecological_region": None, "districts": [
        {"code": "IN-JH-RANCHI", "name": "Ranchi"}, {"code": "IN-JH-HAZARIBAGH", "name": "Hazaribagh"},
        {"code": "IN-JH-DUMKA", "name": "Dumka"}]},
    {"state_code": "IN-KA", "name": "Karnataka", "type": "state", "agroclimatic_zone": "Southern Plateau and Hills", "agroecological_region": None, "districts": [
        {"code": "IN-KA-BELAGAVI", "name": "Belagavi", "aliases": ["Belgaum"]}, {"code": "IN-KA-MYSURU", "name": "Mysuru", "aliases": ["Mysore"]},
        {"code": "IN-KA-HAVERI", "name": "Haveri"}, {"code": "IN-KA-VIJAYAPURA", "name": "Vijayapura", "aliases": ["Bijapur"]},
        {"code": "IN-KA-TUMAKURU", "name": "Tumakuru"}, {"code": "IN-KA-CHIKKAMAGALURU", "name": "Chikkamagaluru", "aliases": ["Chikmagalur"]}]},
    {"state_code": "IN-KL", "name": "Kerala", "type": "state", "agroclimatic_zone": "West Coast Plains and Ghats", "agroecological_region": None, "districts": [
        {"code": "IN-KL-IDUKKI", "name": "Idukki"}, {"code": "IN-KL-PALAKKAD", "name": "Palakkad"},
        {"code": "IN-KL-WAYANAD", "name": "Wayanad"}, {"code": "IN-KL-THRISSUR", "name": "Thrissur"}]},
    {"state_code": "IN-MP", "name": "Madhya Pradesh", "type": "state", "agroclimatic_zone": "Central Plateau and Hills", "agroecological_region": None, "districts": [
        {"code": "IN-MP-INDORE", "name": "Indore"}, {"code": "IN-MP-UJJAIN", "name": "Ujjain"},
        {"code": "IN-MP-SEHORE", "name": "Sehore"}, {"code": "IN-MP-CHHINDWARA", "name": "Chhindwara"},
        {"code": "IN-MP-MORENA", "name": "Morena"}, {"code": "IN-MP-HOSHANGABAD", "name": "Hoshangabad"}]},
    {"state_code": "IN-MH", "name": "Maharashtra", "type": "state", "agroclimatic_zone": "Western Plateau and Hills", "agroecological_region": None, "districts": [
        {"code": "IN-MH-PUNE", "name": "Pune"}, {"code": "IN-MH-NASHIK", "name": "Nashik"},
        {"code": "IN-MH-NAGPUR", "name": "Nagpur"}, {"code": "IN-MH-SOLAPUR", "name": "Solapur"},
        {"code": "IN-MH-AHMEDNAGAR", "name": "Ahmednagar"}, {"code": "IN-MH-JALGAON", "name": "Jalgaon"},
        {"code": "IN-MH-AURANGABAD", "name": "Aurangabad", "aliases": ["Chhatrapati Sambhajinagar"]}]},
    {"state_code": "IN-MN", "name": "Manipur", "type": "state", "agroclimatic_zone": "Eastern Himalayan Region", "agroecological_region": None, "districts": [
        {"code": "IN-MN-IMPHAL_W", "name": "Imphal West"}, {"code": "IN-MN-BISHNUPUR", "name": "Bishnupur"}]},
    {"state_code": "IN-ML", "name": "Meghalaya", "type": "state", "agroclimatic_zone": "Eastern Himalayan Region", "agroecological_region": None, "districts": [
        {"code": "IN-ML-EKH", "name": "East Khasi Hills"}, {"code": "IN-ML-WGH", "name": "West Garo Hills"}]},
    {"state_code": "IN-MZ", "name": "Mizoram", "type": "state", "agroclimatic_zone": "Eastern Himalayan Region", "agroecological_region": None, "districts": [
        {"code": "IN-MZ-AIZAWL", "name": "Aizawl"}]},
    {"state_code": "IN-NL", "name": "Nagaland", "type": "state", "agroclimatic_zone": "Eastern Himalayan Region", "agroecological_region": None, "districts": [
        {"code": "IN-NL-DIMAPUR", "name": "Dimapur"}, {"code": "IN-NL-KOHIMA", "name": "Kohima"}]},
    {"state_code": "IN-OD", "name": "Odisha", "type": "state", "agroclimatic_zone": "East Coast Plains and Hills", "agroecological_region": None, "districts": [
        {"code": "IN-OD-BARGARH", "name": "Bargarh"}, {"code": "IN-OD-CUTTACK", "name": "Cuttack"},
        {"code": "IN-OD-GANJAM", "name": "Ganjam"}, {"code": "IN-OD-MAYURBHANJ", "name": "Mayurbhanj"},
        {"code": "IN-OD-PURI", "name": "Puri"}]},
    {"state_code": "IN-PB", "name": "Punjab", "type": "state", "agroclimatic_zone": "Trans-Gangetic Plains", "agroecological_region": None, "districts": [
        {"code": "IN-PB-LUDHIANA", "name": "Ludhiana"}, {"code": "IN-PB-SANGRUR", "name": "Sangrur"},
        {"code": "IN-PB-FEROZEPUR", "name": "Ferozepur"}, {"code": "IN-PB-BATHINDA", "name": "Bathinda"},
        {"code": "IN-PB-AMRITSAR", "name": "Amritsar"}]},
    {"state_code": "IN-RJ", "name": "Rajasthan", "type": "state", "agroclimatic_zone": "Western Dry Region", "agroecological_region": None, "districts": [
        {"code": "IN-RJ-JAIPUR", "name": "Jaipur"}, {"code": "IN-RJ-JODHPUR", "name": "Jodhpur"},
        {"code": "IN-RJ-KOTA", "name": "Kota"}, {"code": "IN-RJ-GANGANAGAR", "name": "Sri Ganganagar", "aliases": ["Ganganagar"]},
        {"code": "IN-RJ-ALWAR", "name": "Alwar"}, {"code": "IN-RJ-BARMER", "name": "Barmer"}]},
    {"state_code": "IN-SK", "name": "Sikkim", "type": "state", "agroclimatic_zone": "Eastern Himalayan Region", "agroecological_region": None, "districts": [
        {"code": "IN-SK-EAST", "name": "East Sikkim"}]},
    {"state_code": "IN-TN", "name": "Tamil Nadu", "type": "state", "agroclimatic_zone": "Southern Plateau and Hills", "agroecological_region": None, "districts": [
        {"code": "IN-TN-THANJAVUR", "name": "Thanjavur", "aliases": ["Tanjore"]}, {"code": "IN-TN-COIMBATORE", "name": "Coimbatore"},
        {"code": "IN-TN-ERODE", "name": "Erode"}, {"code": "IN-TN-MADURAI", "name": "Madurai"},
        {"code": "IN-TN-VILLUPURAM", "name": "Villupuram"}, {"code": "IN-TN-SALEM", "name": "Salem"}]},
    {"state_code": "IN-TG", "name": "Telangana", "type": "state", "agroclimatic_zone": "Southern Plateau and Hills", "agroecological_region": None, "districts": [
        {"code": "IN-TG-NIZAMABAD", "name": "Nizamabad"}, {"code": "IN-TG-WARANGAL", "name": "Warangal"},
        {"code": "IN-TG-KARIMNAGAR", "name": "Karimnagar"}, {"code": "IN-TG-MAHBUBNAGAR", "name": "Mahbubnagar"}]},
    {"state_code": "IN-TR", "name": "Tripura", "type": "state", "agroclimatic_zone": "Eastern Himalayan Region", "agroecological_region": None, "districts": [
        {"code": "IN-TR-WEST", "name": "West Tripura"}]},
    {"state_code": "IN-UP", "name": "Uttar Pradesh", "type": "state", "agroclimatic_zone": "Upper Gangetic Plains", "agroecological_region": None, "districts": [
        {"code": "IN-UP-LUCKNOW", "name": "Lucknow"}, {"code": "IN-UP-VARANASI", "name": "Varanasi"},
        {"code": "IN-UP-MEERUT", "name": "Meerut"}, {"code": "IN-UP-GORAKHPUR", "name": "Gorakhpur"},
        {"code": "IN-UP-KANPUR", "name": "Kanpur Nagar", "aliases": ["Kanpur"]}, {"code": "IN-UP-AGRA", "name": "Agra"}]},
    {"state_code": "IN-UK", "name": "Uttarakhand", "type": "state", "agroclimatic_zone": "Western Himalayan Region", "agroecological_region": None, "districts": [
        {"code": "IN-UK-DEHRADUN", "name": "Dehradun"}, {"code": "IN-UK-USNAGAR", "name": "Udham Singh Nagar", "aliases": ["US Nagar"]},
        {"code": "IN-UK-HARIDWAR", "name": "Haridwar"}]},
    {"state_code": "IN-WB", "name": "West Bengal", "type": "state", "agroclimatic_zone": "Lower Gangetic Plains", "agroecological_region": None, "districts": [
        {"code": "IN-WB-PBARDHAMAN", "name": "Purba Bardhaman", "aliases": ["Bardhaman", "Burdwan"]}, {"code": "IN-WB-HOOGHLY", "name": "Hooghly"},
        {"code": "IN-WB-NADIA", "name": "Nadia"}, {"code": "IN-WB-MURSHIDABAD", "name": "Murshidabad"},
        {"code": "IN-WB-PMEDINIPUR", "name": "Paschim Medinipur", "aliases": ["West Midnapore"]}, {"code": "IN-WB-JALPAIGURI", "name": "Jalpaiguri"}]},
    # Union Territories
    {"state_code": "IN-AN", "name": "Andaman and Nicobar Islands", "type": "UT", "agroclimatic_zone": "The Islands Region", "agroecological_region": None, "districts": [
        {"code": "IN-AN-SOUTH", "name": "South Andaman"}]},
    {"state_code": "IN-CH", "name": "Chandigarh", "type": "UT", "agroclimatic_zone": "Trans-Gangetic Plains", "agroecological_region": None, "districts": [
        {"code": "IN-CH-CHANDIGARH", "name": "Chandigarh"}]},
    {"state_code": "IN-DH", "name": "Dadra and Nagar Haveli and Daman and Diu", "type": "UT", "agroclimatic_zone": "Gujarat Plains and Hills", "agroecological_region": None, "districts": [
        {"code": "IN-DH-DAMAN", "name": "Daman"}]},
    {"state_code": "IN-DL", "name": "Delhi", "type": "UT", "agroclimatic_zone": "Trans-Gangetic Plains", "agroecological_region": None, "districts": [
        {"code": "IN-DL-NEWDELHI", "name": "New Delhi"}]},
    {"state_code": "IN-JK", "name": "Jammu and Kashmir", "type": "UT", "agroclimatic_zone": "Western Himalayan Region", "agroecological_region": None, "districts": [
        {"code": "IN-JK-SRINAGAR", "name": "Srinagar"}, {"code": "IN-JK-JAMMU", "name": "Jammu"},
        {"code": "IN-JK-ANANTNAG", "name": "Anantnag"}]},
    {"state_code": "IN-LA", "name": "Ladakh", "type": "UT", "agroclimatic_zone": "Western Himalayan Region", "agroecological_region": None, "districts": [
        {"code": "IN-LA-LEH", "name": "Leh"}]},
    {"state_code": "IN-LD", "name": "Lakshadweep", "type": "UT", "agroclimatic_zone": "The Islands Region", "agroecological_region": None, "districts": [
        {"code": "IN-LD-LAKSHADWEEP", "name": "Lakshadweep"}]},
    {"state_code": "IN-PY", "name": "Puducherry", "type": "UT", "agroclimatic_zone": "East Coast Plains and Hills", "agroecological_region": None, "districts": [
        {"code": "IN-PY-PUDUCHERRY", "name": "Puducherry"}, {"code": "IN-PY-KARAIKAL", "name": "Karaikal"}]},
]

GEOGRAPHY_ALIASES = {
    "IN-OD": ["Orissa"],
    "IN-UK": ["Uttaranchal"],
    "IN-PY": ["Pondicherry"],
    "IN-DL": ["NCT of Delhi", "National Capital Territory of Delhi"],
    "IN-DH": ["Daman and Diu", "Dadra and Nagar Haveli"],
    "IN-JK": ["J&K", "Jammu & Kashmir"],
    "IN-WB": ["Bengal"],
    "IN-AN": ["Andaman", "A & N Islands"],
}

# ─────────────────────────────────────────────────────────────────────────────
# Seasons + growth stages (phenology)
# ─────────────────────────────────────────────────────────────────────────────
SEASONS = [
    {"season_id": "SEASON_KHARIF", "name": "Kharif", "months": "Jun-Oct", "description": "Monsoon / south-west monsoon crop"},
    {"season_id": "SEASON_RABI", "name": "Rabi", "months": "Oct-Mar", "description": "Winter / post-monsoon crop"},
    {"season_id": "SEASON_ZAID", "name": "Zaid", "months": "Mar-Jun", "description": "Short summer crop between rabi and kharif"},
    {"season_id": "SEASON_SUMMER", "name": "Summer", "months": "Feb-May", "description": "Irrigated summer season (horticulture emphasis)"},
    {"season_id": "SEASON_WHOLE_YEAR", "name": "Whole Year", "months": "Jan-Dec", "description": "Perennial / plantation crops"},
]

GROWTH_STAGES = [
    {"stage_id": "STAGE_NURSERY", "name": "nursery", "description": "Seedling raising in nursery"},
    {"stage_id": "STAGE_SOWING", "name": "sowing", "description": "Seed sowing / planting"},
    {"stage_id": "STAGE_GERMINATION", "name": "germination", "description": "Seed germination / emergence"},
    {"stage_id": "STAGE_TRANSPLANTING", "name": "transplanting", "description": "Transplanting seedlings to main field"},
    {"stage_id": "STAGE_ESTABLISHMENT", "name": "establishment", "description": "Early establishment / tillering"},
    {"stage_id": "STAGE_VEGETATIVE", "name": "vegetative", "description": "Vegetative growth"},
    {"stage_id": "STAGE_FLOWERING", "name": "flowering", "description": "Flowering / anthesis"},
    {"stage_id": "STAGE_FRUIT_SET", "name": "fruit_set", "description": "Fruit / pod / boll set"},
    {"stage_id": "STAGE_GRAIN_FILL", "name": "grain_fill", "description": "Grain / fruit filling"},
    {"stage_id": "STAGE_MATURITY", "name": "maturity", "description": "Physiological maturity"},
    {"stage_id": "STAGE_HARVEST", "name": "harvest", "description": "Harvesting"},
    {"stage_id": "STAGE_POST_HARVEST", "name": "post_harvest", "description": "Post-harvest handling / storage"},
]

# Crop → season mapping
CROP_SEASON = [
    {"crop_id": "CROP_RICE", "season_id": "SEASON_KHARIF"},
    {"crop_id": "CROP_RICE", "season_id": "SEASON_RABI"},
    {"crop_id": "CROP_RICE", "season_id": "SEASON_SUMMER"},
    {"crop_id": "CROP_WHEAT", "season_id": "SEASON_RABI"},
    {"crop_id": "CROP_MAIZE", "season_id": "SEASON_KHARIF"},
    {"crop_id": "CROP_MAIZE", "season_id": "SEASON_RABI"},
    {"crop_id": "CROP_MAIZE", "season_id": "SEASON_ZAID"},
    {"crop_id": "CROP_JOWAR", "season_id": "SEASON_KHARIF"},
    {"crop_id": "CROP_JOWAR", "season_id": "SEASON_RABI"},
    {"crop_id": "CROP_BAJRA", "season_id": "SEASON_KHARIF"},
    {"crop_id": "CROP_BAJRA", "season_id": "SEASON_SUMMER"},
    {"crop_id": "CROP_RAGI", "season_id": "SEASON_KHARIF"},
    {"crop_id": "CROP_RAGI", "season_id": "SEASON_RABI"},
    {"crop_id": "CROP_PIGEONPEA", "season_id": "SEASON_KHARIF"},
    {"crop_id": "CROP_CHICKPEA", "season_id": "SEASON_RABI"},
    {"crop_id": "CROP_GREENGRAM", "season_id": "SEASON_KHARIF"},
    {"crop_id": "CROP_GREENGRAM", "season_id": "SEASON_SUMMER"},
    {"crop_id": "CROP_BLACKGRAM", "season_id": "SEASON_KHARIF"},
    {"crop_id": "CROP_BLACKGRAM", "season_id": "SEASON_RABI"},
    {"crop_id": "CROP_LENTIL", "season_id": "SEASON_RABI"},
    {"crop_id": "CROP_SOYBEAN", "season_id": "SEASON_KHARIF"},
    {"crop_id": "CROP_GROUNDNUT", "season_id": "SEASON_KHARIF"},
    {"crop_id": "CROP_GROUNDNUT", "season_id": "SEASON_RABI"},
    {"crop_id": "CROP_GROUNDNUT", "season_id": "SEASON_SUMMER"},
    {"crop_id": "CROP_MUSTARD", "season_id": "SEASON_RABI"},
    {"crop_id": "CROP_SESAME", "season_id": "SEASON_KHARIF"},
    {"crop_id": "CROP_SUNFLOWER", "season_id": "SEASON_KHARIF"},
    {"crop_id": "CROP_SUNFLOWER", "season_id": "SEASON_RABI"},
    {"crop_id": "CROP_COTTON", "season_id": "SEASON_KHARIF"},
    {"crop_id": "CROP_SUGARCANE", "season_id": "SEASON_WHOLE_YEAR"},
    {"crop_id": "CROP_ONION", "season_id": "SEASON_KHARIF"},
    {"crop_id": "CROP_ONION", "season_id": "SEASON_RABI"},
    {"crop_id": "CROP_ONION", "season_id": "SEASON_SUMMER"},
    {"crop_id": "CROP_TOMATO", "season_id": "SEASON_KHARIF"},
    {"crop_id": "CROP_TOMATO", "season_id": "SEASON_RABI"},
    {"crop_id": "CROP_TOMATO", "season_id": "SEASON_SUMMER"},
    {"crop_id": "CROP_POTATO", "season_id": "SEASON_RABI"},
    {"crop_id": "CROP_CHILLI", "season_id": "SEASON_KHARIF"},
    {"crop_id": "CROP_CHILLI", "season_id": "SEASON_RABI"},
    {"crop_id": "CROP_BRINJAL", "season_id": "SEASON_KHARIF"},
    {"crop_id": "CROP_BRINJAL", "season_id": "SEASON_RABI"},
    {"crop_id": "CROP_BRINJAL", "season_id": "SEASON_SUMMER"},
    {"crop_id": "CROP_OKRA", "season_id": "SEASON_KHARIF"},
    {"crop_id": "CROP_OKRA", "season_id": "SEASON_SUMMER"},
    {"crop_id": "CROP_TURMERIC", "season_id": "SEASON_KHARIF"},
    {"crop_id": "CROP_GINGER", "season_id": "SEASON_KHARIF"},
    {"crop_id": "CROP_GARLIC", "season_id": "SEASON_RABI"},
    {"crop_id": "CROP_CORIANDER", "season_id": "SEASON_RABI"},
    {"crop_id": "CROP_CUMIN", "season_id": "SEASON_RABI"},
    {"crop_id": "CROP_BANANA", "season_id": "SEASON_WHOLE_YEAR"},
    {"crop_id": "CROP_MANGO", "season_id": "SEASON_WHOLE_YEAR"},
    {"crop_id": "CROP_GRAPES", "season_id": "SEASON_WHOLE_YEAR"},
    {"crop_id": "CROP_POMEGRANATE", "season_id": "SEASON_WHOLE_YEAR"},
    {"crop_id": "CROP_TEA", "season_id": "SEASON_WHOLE_YEAR"},
    {"crop_id": "CROP_COFFEE", "season_id": "SEASON_WHOLE_YEAR"},
    {"crop_id": "CROP_COCONUT", "season_id": "SEASON_WHOLE_YEAR"},
    {"crop_id": "CROP_CASHEW", "season_id": "SEASON_WHOLE_YEAR"},
    {"crop_id": "CROP_RUBBER", "season_id": "SEASON_WHOLE_YEAR"},
]

# Exemplar crop calendars (month windows per stage; extend per agro-climatic zone).
CROP_CALENDAR = [
    {"crop_id": "CROP_RICE", "season_id": "SEASON_KHARIF", "stage_id": "STAGE_SOWING", "month_start": 6, "month_end": 7, "note": "nursery sowing"},
    {"crop_id": "CROP_RICE", "season_id": "SEASON_KHARIF", "stage_id": "STAGE_TRANSPLANTING", "month_start": 7, "month_end": 8, "note": None},
    {"crop_id": "CROP_RICE", "season_id": "SEASON_KHARIF", "stage_id": "STAGE_VEGETATIVE", "month_start": 8, "month_end": 9, "note": None},
    {"crop_id": "CROP_RICE", "season_id": "SEASON_KHARIF", "stage_id": "STAGE_FLOWERING", "month_start": 9, "month_end": 10, "note": None},
    {"crop_id": "CROP_RICE", "season_id": "SEASON_KHARIF", "stage_id": "STAGE_HARVEST", "month_start": 10, "month_end": 11, "note": None},
    {"crop_id": "CROP_WHEAT", "season_id": "SEASON_RABI", "stage_id": "STAGE_SOWING", "month_start": 10, "month_end": 11, "note": None},
    {"crop_id": "CROP_WHEAT", "season_id": "SEASON_RABI", "stage_id": "STAGE_VEGETATIVE", "month_start": 11, "month_end": 12, "note": "tillering"},
    {"crop_id": "CROP_WHEAT", "season_id": "SEASON_RABI", "stage_id": "STAGE_FLOWERING", "month_start": 1, "month_end": 2, "note": None},
    {"crop_id": "CROP_WHEAT", "season_id": "SEASON_RABI", "stage_id": "STAGE_GRAIN_FILL", "month_start": 2, "month_end": 3, "note": None},
    {"crop_id": "CROP_WHEAT", "season_id": "SEASON_RABI", "stage_id": "STAGE_HARVEST", "month_start": 3, "month_end": 4, "note": None},
    {"crop_id": "CROP_TOMATO", "season_id": "SEASON_RABI", "stage_id": "STAGE_NURSERY", "month_start": 8, "month_end": 9, "note": None},
    {"crop_id": "CROP_TOMATO", "season_id": "SEASON_RABI", "stage_id": "STAGE_TRANSPLANTING", "month_start": 9, "month_end": 10, "note": None},
    {"crop_id": "CROP_TOMATO", "season_id": "SEASON_RABI", "stage_id": "STAGE_FLOWERING", "month_start": 11, "month_end": 12, "note": None},
    {"crop_id": "CROP_TOMATO", "season_id": "SEASON_RABI", "stage_id": "STAGE_HARVEST", "month_start": 1, "month_end": 3, "note": None},
    {"crop_id": "CROP_COTTON", "season_id": "SEASON_KHARIF", "stage_id": "STAGE_SOWING", "month_start": 6, "month_end": 7, "note": None},
    {"crop_id": "CROP_COTTON", "season_id": "SEASON_KHARIF", "stage_id": "STAGE_FLOWERING", "month_start": 9, "month_end": 10, "note": "boll formation follows"},
    {"crop_id": "CROP_COTTON", "season_id": "SEASON_KHARIF", "stage_id": "STAGE_HARVEST", "month_start": 11, "month_end": 1, "note": "picking in flushes"},
    {"crop_id": "CROP_SUGARCANE", "season_id": "SEASON_WHOLE_YEAR", "stage_id": "STAGE_SOWING", "month_start": 2, "month_end": 3, "note": "spring planting (adsali Feb-Jun)"},
    {"crop_id": "CROP_SUGARCANE", "season_id": "SEASON_WHOLE_YEAR", "stage_id": "STAGE_VEGETATIVE", "month_start": 4, "month_end": 9, "note": "grand growth"},
    {"crop_id": "CROP_SUGARCANE", "season_id": "SEASON_WHOLE_YEAR", "stage_id": "STAGE_MATURITY", "month_start": 10, "month_end": 12, "note": "ripening"},
    {"crop_id": "CROP_SUGARCANE", "season_id": "SEASON_WHOLE_YEAR", "stage_id": "STAGE_HARVEST", "month_start": 11, "month_end": 3, "note": "crushing season"},
]

# ─────────────────────────────────────────────────────────────────────────────
# Diseases (separate from vision dataset labels; diagnosis-oriented)
# ─────────────────────────────────────────────────────────────────────────────
DISEASES = [
    {"disease_id": "DIS_RICE_BLAST", "name": "Rice blast", "crop_id": "CROP_RICE", "crop": "Rice", "pathogen_type": "fungal", "causal_agent": "Magnaporthe oryzae", "symptoms": "Spindle-shaped lesions with grey centre on leaves, nodes and panicle neck", "affected_parts": "leaf|stem|panicle", "favourable_conditions": "High humidity, 25-28 C, excess nitrogen", "management": "Resistant varieties, balanced N; tricyclazole/isoprothiolane at booting"},
    {"disease_id": "DIS_RICE_BLB", "name": "Bacterial leaf blight", "crop_id": "CROP_RICE", "crop": "Rice", "pathogen_type": "bacterial", "causal_agent": "Xanthomonas oryzae pv. oryzae", "symptoms": "Water-soaked lesions, yellowing, drying from leaf tip", "affected_parts": "leaf", "favourable_conditions": "Warm, high humidity, standing water", "management": "Clean seed, avoid excess N; copper sprays"},
    {"disease_id": "DIS_RICE_BROWN_SPOT", "name": "Brown spot", "crop_id": "CROP_RICE", "crop": "Rice", "pathogen_type": "fungal", "causal_agent": "Bipolaris oryzae", "symptoms": "Brown oval spots on leaves and grains", "affected_parts": "leaf|grain", "favourable_conditions": "Nutrient-deficient soil, drought", "management": "Balanced nutrition; mancozeb/propiconazole"},
    {"disease_id": "DIS_RICE_SHEATH_BLIGHT", "name": "Sheath blight", "crop_id": "CROP_RICE", "crop": "Rice", "pathogen_type": "fungal", "causal_agent": "Rhizoctonia solani", "symptoms": "Grey-green lesions on leaf sheaths near water line", "affected_parts": "sheath|leaf", "favourable_conditions": "High humidity, dense canopy", "management": "Wider spacing; hexaconazole/validamycin"},
    {"disease_id": "DIS_WHEAT_RUST", "name": "Wheat rusts (leaf/stem/stripe)", "crop_id": "CROP_WHEAT", "crop": "Wheat", "pathogen_type": "fungal", "causal_agent": "Puccinia spp.", "symptoms": "Rust-coloured pustules on leaves/stem", "affected_parts": "leaf|stem", "favourable_conditions": "Cool moist weather", "management": "Resistant varieties; propiconazole/tebuconazole"},
    {"disease_id": "DIS_WHEAT_PM", "name": "Powdery mildew", "crop_id": "CROP_WHEAT", "crop": "Wheat", "pathogen_type": "fungal", "causal_agent": "Blumeria graminis", "symptoms": "White powdery growth on leaves", "affected_parts": "leaf", "favourable_conditions": "Cool humid, 15-20 C", "management": "Wettable sulphur"},
    {"disease_id": "DIS_MAIZE_DM", "name": "Downy mildew", "crop_id": "CROP_MAIZE", "crop": "Maize", "pathogen_type": "fungal", "causal_agent": "Peronosclerospora spp.", "symptoms": "Chlorotic stripes, white downy growth, stunting", "affected_parts": "leaf", "favourable_conditions": "Cool humid", "management": "Metalaxyl seed treatment, resistant hybrids"},
    {"disease_id": "DIS_MAIZE_BLSB", "name": "Banded leaf and sheath blight", "crop_id": "CROP_MAIZE", "crop": "Maize", "pathogen_type": "fungal", "causal_agent": "Rhizoctonia solani f. sp. sasakii", "symptoms": "Banded lesions on leaf/sheath", "affected_parts": "leaf|sheath", "favourable_conditions": "Warm humid", "management": "Carbendazim/propiconazole"},
    {"disease_id": "DIS_TOMATO_EB", "name": "Early blight", "crop_id": "CROP_TOMATO", "crop": "Tomato", "pathogen_type": "fungal", "causal_agent": "Alternaria solani", "symptoms": "Concentric ring spots on lower leaves", "affected_parts": "leaf|stem|fruit", "favourable_conditions": "Warm humid, dew", "management": "Mancozeb/chlorothalonil; mulching"},
    {"disease_id": "DIS_TOMATO_LB", "name": "Late blight", "crop_id": "CROP_TOMATO", "crop": "Tomato", "pathogen_type": "fungal", "causal_agent": "Phytophthora infestans", "symptoms": "Water-soaked greasy lesions, white growth under leaf", "affected_parts": "leaf|stem|fruit", "favourable_conditions": "Cool (10-20 C) humid", "management": "Metalaxyl+mancozeb, cymoxanil; avoid overhead irrigation"},
    {"disease_id": "DIS_TOMATO_BW", "name": "Bacterial wilt", "crop_id": "CROP_TOMATO", "crop": "Tomato", "pathogen_type": "bacterial", "causal_agent": "Ralstonia solanacearum", "symptoms": "Sudden wilting, brown vascular browning", "affected_parts": "root|stem", "favourable_conditions": "Warm wet soil", "management": "Crop rotation, resistant rootstocks, soil solarization"},
    {"disease_id": "DIS_TOMATO_LCV", "name": "Leaf curl", "crop_id": "CROP_TOMATO", "crop": "Tomato", "pathogen_type": "viral", "causal_agent": "Tomato leaf curl virus (ToLCV)", "symptoms": "Upward curling, yellowing, stunting", "affected_parts": "leaf", "favourable_conditions": "High whitefly population", "management": "Whitefly control, resistant hybrids"},
    {"disease_id": "DIS_POTATO_LB", "name": "Late blight", "crop_id": "CROP_POTATO", "crop": "Potato", "pathogen_type": "fungal", "causal_agent": "Phytophthora infestans", "symptoms": "Brown-black lesions on leaves and tubers", "affected_parts": "leaf|tuber", "favourable_conditions": "Cool humid", "management": "Metalaxyl+mancozeb, roguing"},
    {"disease_id": "DIS_CHILLI_ANTHRACNOSE", "name": "Anthracnose (die-back/fruit rot)", "crop_id": "CROP_CHILLI", "crop": "Chilli", "pathogen_type": "fungal", "causal_agent": "Colletotrichum capsici", "symptoms": "Sunken dark spots on fruit, die-back of twigs", "affected_parts": "fruit|stem", "favourable_conditions": "Warm humid", "management": "Carbendazim/chlorothalonil, clean seed"},
    {"disease_id": "DIS_CHILLI_LCV", "name": "Leaf curl", "crop_id": "CROP_CHILLI", "crop": "Chilli", "pathogen_type": "viral", "causal_agent": "Chilli leaf curl virus", "symptoms": "Curling, puckering, stunting", "affected_parts": "leaf", "favourable_conditions": "Whitefly vector", "management": "Whitefly control, resistant varieties"},
    {"disease_id": "DIS_ONION_PB", "name": "Purple blotch", "crop_id": "CROP_ONION", "crop": "Onion", "pathogen_type": "fungal", "causal_agent": "Alternaria porri", "symptoms": "Purple blotches on leaves, leaf die-back", "affected_parts": "leaf", "favourable_conditions": "Warm humid", "management": "Mancozeb/propiconazole"},
    {"disease_id": "DIS_COTTON_LCV", "name": "Leaf curl", "crop_id": "CROP_COTTON", "crop": "Cotton", "pathogen_type": "viral", "causal_agent": "Cotton leaf curl virus", "symptoms": "Upward curling, enations on veins", "affected_parts": "leaf", "favourable_conditions": "Whitefly (Bemisia tabaci)", "management": "Whitefly control, resistant varieties"},
    {"disease_id": "DIS_COTTON_WILT", "name": "Fusarium wilt", "crop_id": "CROP_COTTON", "crop": "Cotton", "pathogen_type": "fungal", "causal_agent": "Fusarium oxysporum f. sp. vasinfectum", "symptoms": "Wilting, vascular discoloration", "affected_parts": "root|stem", "favourable_conditions": "Warm dry soil", "management": "Resistant varieties, rotation"},
    {"disease_id": "DIS_SUGARCANE_RR", "name": "Red rot", "crop_id": "CROP_SUGARCANE", "crop": "Sugarcane", "pathogen_type": "fungal", "causal_agent": "Colletotrichum falcatum", "symptoms": "Reddening of internodes with white patches", "affected_parts": "stem", "favourable_conditions": "High humidity, injury", "management": "Resistant varieties, clean setts, hot water treatment"},
    {"disease_id": "DIS_SUGARCANE_SMUT", "name": "Smut", "crop_id": "CROP_SUGARCANE", "crop": "Sugarcane", "pathogen_type": "fungal", "causal_agent": "Sporisorium scitamineum", "symptoms": "Whip-like black sorus from apex", "affected_parts": "stem|flower", "favourable_conditions": "Dry warm", "management": "Roguing, resistant varieties"},
    {"disease_id": "DIS_GROUNDNUT_TIKKA", "name": "Tikka (early/late leaf spot)", "crop_id": "CROP_GROUNDNUT", "crop": "Groundnut", "pathogen_type": "fungal", "causal_agent": "Cercospora arachidicola / Phaeoisariopsis personata", "symptoms": "Circular brown spots, premature defoliation", "affected_parts": "leaf", "favourable_conditions": "Warm humid", "management": "Carbendazim/chlorothalonil, rotation"},
    {"disease_id": "DIS_GRAPE_DM", "name": "Downy mildew", "crop_id": "CROP_GRAPES", "crop": "Grapes", "pathogen_type": "fungal", "causal_agent": "Plasmopara viticola", "symptoms": "Oily yellow spots, white growth under leaf", "affected_parts": "leaf|fruit", "favourable_conditions": "Cool humid", "management": "Metalaxyl+mancozeb, Bordeaux mixture"},
    {"disease_id": "DIS_BANANA_PW", "name": "Panama wilt", "crop_id": "CROP_BANANA", "crop": "Banana", "pathogen_type": "fungal", "causal_agent": "Fusarium oxysporum f. sp. cubense", "symptoms": "Yellowing, pseudostem splitting, vascular discoloration", "affected_parts": "root|stem", "favourable_conditions": "Warm soil", "management": "Resistant varieties, clean planting material"},
    {"disease_id": "DIS_BANANA_SIGATOKA", "name": "Sigatoka leaf spot", "crop_id": "CROP_BANANA", "crop": "Banana", "pathogen_type": "fungal", "causal_agent": "Mycosphaerella musicola", "symptoms": "Brown streaks, leaf spots, reduced photosynthesis", "affected_parts": "leaf", "favourable_conditions": "Humid", "management": "Propiconazole, de-trashing"},
    {"disease_id": "DIS_MANGO_ANTH", "name": "Anthracnose", "crop_id": "CROP_MANGO", "crop": "Mango", "pathogen_type": "fungal", "causal_agent": "Colletotrichum gloeosporioides", "symptoms": "Dark sunken lesions on leaves, flowers, fruit", "affected_parts": "leaf|flower|fruit", "favourable_conditions": "Rainy humid", "management": "Carbendazim/thiophanate-methyl at flowering"},
    {"disease_id": "DIS_MANGO_PM", "name": "Powdery mildew", "crop_id": "CROP_MANGO", "crop": "Mango", "pathogen_type": "fungal", "causal_agent": "Oidium mangiferae", "symptoms": "White powdery growth on inflorescence", "affected_parts": "flower|leaf", "favourable_conditions": "Cool dry", "management": "Wettable sulphur, dinocap"},
    {"disease_id": "DIS_CITRUS_CANKER", "name": "Citrus canker", "crop_id": "CROP_ORANGE", "crop": "Citrus", "pathogen_type": "bacterial", "causal_agent": "Xanthomonas citri subsp. citri", "symptoms": "Corky raised lesions with yellow halo on leaves/fruit", "affected_parts": "leaf|fruit|stem", "favourable_conditions": "Warm humid, wind-driven rain", "management": "Copper sprays, windbreaks, clean nursery stock"},
    {"disease_id": "DIS_BRINJAL_LL", "name": "Little leaf", "crop_id": "CROP_BRINJAL", "crop": "Brinjal", "pathogen_type": "phytoplasma", "causal_agent": "Candidatus Phytoplasma", "symptoms": "Small narrow leaves, bushy stunted growth", "affected_parts": "leaf|stem", "favourable_conditions": "Leafhopper vector", "management": "Vector control, roguing, resistant varieties"},
    {"disease_id": "DIS_BRINJAL_BW", "name": "Bacterial wilt", "crop_id": "CROP_BRINJAL", "crop": "Brinjal", "pathogen_type": "bacterial", "causal_agent": "Ralstonia solanacearum", "symptoms": "Wilting, vascular browning", "affected_parts": "root|stem", "favourable_conditions": "Warm wet soil", "management": "Grafting on resistant rootstock, rotation"},
    {"disease_id": "DIS_OKRA_YVMV", "name": "Yellow vein mosaic", "crop_id": "CROP_OKRA", "crop": "Okra", "pathogen_type": "viral", "causal_agent": "Bhendi yellow vein mosaic virus (BYVMV)", "symptoms": "Yellowing of veins, stunting, few fruits", "affected_parts": "leaf", "favourable_conditions": "Whitefly vector", "management": "Whitefly control, resistant varieties"},
]

# ─────────────────────────────────────────────────────────────────────────────
# Pests (IPM-first: prevention → monitoring → threshold → cultural → mechanical
# → biological → chemical)
# ─────────────────────────────────────────────────────────────────────────────
PESTS = [
    {"pest_id": "PEST_RICE_STEMBORER", "name": "Yellow stem borer", "scientific_name": "Scirpophaga incertulas", "crop_hosts": "Rice", "damage_symptoms": "Dead hearts, white ears", "cultural_control": "Clipping seedling tips, pheromone traps", "biological_control": "Trichogramma egg parasitoids", "chemical_control": "Cartap hydrochloride, chlorantraniliprole at ETL"},
    {"pest_id": "PEST_RICE_BPH", "name": "Brown planthopper", "scientific_name": "Nilaparvata lugens", "crop_hosts": "Rice", "damage_symptoms": "Hopper burn, sooty mould", "cultural_control": "Avoid excess N, field draining", "biological_control": "Encourage natural enemies", "chemical_control": "Buprofezin, pymetrozine"},
    {"pest_id": "PEST_MAIZE_FAW", "name": "Fall armyworm", "scientific_name": "Spodoptera frugiperda", "crop_hosts": "Maize", "damage_symptoms": "Window panes, whorl damage, frass", "cultural_control": "Early sowing, clean cultivation", "biological_control": "Metarhizium, NPV, Trichogramma", "chemical_control": "Emamectin benzoate, spinetoram"},
    {"pest_id": "PEST_COTTON_PBW", "name": "Pink bollworm", "scientific_name": "Pectinophora gossypiella", "crop_hosts": "Cotton", "damage_symptoms": "Rosetted flowers, boll damage, lint staining", "cultural_control": "Crop residue destruction, mating disruption", "biological_control": "Trichogramma bactrae", "chemical_control": "Lambda-cyhalothrin, chlorantraniliprole"},
    {"pest_id": "PEST_COTTON_ABW", "name": "American bollworm", "scientific_name": "Helicoverpa armigera", "crop_hosts": "Cotton|Pulses|Vegetables", "damage_symptoms": "Bore holes in bolls/fruits", "cultural_control": "Pheromone traps, trap crops (marigold)", "biological_control": "HaNPV, Trichogramma, Bt", "chemical_control": "Emamectin, indoxacarb, spinosad"},
    {"pest_id": "PEST_WHITEFLY", "name": "Whitefly", "scientific_name": "Bemisia tabaci", "crop_hosts": "Cotton|Vegetables|Pulses", "damage_symptoms": "Sucking sap, sooty mould, virus vector", "cultural_control": "Yellow sticky traps, reflective mulch", "biological_control": "Encarsia, Chrysoperla", "chemical_control": "Imidacloprid, thiamethoxam (judicious)"},
    {"pest_id": "PEST_APHID", "name": "Aphids", "scientific_name": "Aphis gossypii", "crop_hosts": "Vegetables|Cotton", "damage_symptoms": "Curling, honeydew, sooty mould", "cultural_control": "Neem oil, balanced N", "biological_control": "Coccinellids, Chrysoperla", "chemical_control": "Dimethoate, imidacloprid"},
    {"pest_id": "PEST_THRIPS", "name": "Thrips", "scientific_name": "Thrips tabaci", "crop_hosts": "Onion|Chilli|Cotton", "damage_symptoms": "Silvery streaks, leaf curling", "cultural_control": "Mulching, clean cultivation", "biological_control": "Predatory mites", "chemical_control": "Spinosad, fipronil"},
    {"pest_id": "PEST_BRINJAL_FB", "name": "Fruit and shoot borer", "scientific_name": "Leucinodes orbonalis", "crop_hosts": "Brinjal", "damage_symptoms": "Wilted shoots, bore holes in fruit", "cultural_control": "Sanitation, trap crops", "biological_control": "Pheromone traps, Bt", "chemical_control": "Spinosad, emamectin"},
    {"pest_id": "PEST_DBM", "name": "Diamondback moth", "scientific_name": "Plutella xylostella", "crop_hosts": "Cabbage|Cauliflower", "damage_symptoms": "Shot holes, leaf skeletonization", "cultural_control": "Rotation, clean fields", "biological_control": "Bt, Trichogramma", "chemical_control": "Spinosad, indoxacarb, chlorantraniliprole"},
    {"pest_id": "PEST_OKRA_FB", "name": "Shoot and fruit borer", "scientific_name": "Earias vittella", "crop_hosts": "Okra", "damage_symptoms": "Bored shoots and fruits", "cultural_control": "Trap crops, sanitation", "biological_control": "Bt", "chemical_control": "Spinosad, emamectin"},
    {"pest_id": "PEST_MITE", "name": "Red spider mite", "scientific_name": "Tetranychus urticae", "crop_hosts": "Vegetables|Fruits", "damage_symptoms": "Yellow speckling, webbing", "cultural_control": "Water spray, avoid dusty conditions", "biological_control": "Predatory mite Phytoseiulus", "chemical_control": "Propargite, spiromesifen, wettable sulphur"},
    {"pest_id": "PEST_MEALYBUG", "name": "Mealybug", "scientific_name": "Phenacoccus solenopsis", "crop_hosts": "Cotton", "damage_symptoms": "Stunted growth, sooty mould", "cultural_control": "Remove infested plants", "biological_control": "Cryptolaemus montrouzieri", "chemical_control": "Buprofezin, imidacloprid"},
    {"pest_id": "PEST_TERMITE", "name": "Termites", "scientific_name": "Odontotermes obesus", "crop_hosts": "Sugarcane|Wheat", "damage_symptoms": "Root/stem damage, wilting", "cultural_control": "Deep ploughing, avoid undecomposed manure", "biological_control": "Entomopathogenic fungi", "chemical_control": "Chlorpyrifos soil treatment"},
    {"pest_id": "PEST_LOCUST", "name": "Desert locust", "scientific_name": "Schistocerca gregaria", "crop_hosts": "All crops", "damage_symptoms": "Defoliation, crop loss", "cultural_control": "Egg surveillance, community action", "biological_control": "Metarhizium acridum", "chemical_control": "Malathion, chlorpyrifos (coordinated)"},
    {"pest_id": "PEST_WHITEGRUB", "name": "White grub", "scientific_name": "Holotrichia consanguinea", "crop_hosts": "Groundnut|Sugarcane", "damage_symptoms": "Root damage, wilting, patchy growth", "cultural_control": "Summer ploughing, light traps", "biological_control": "Metarhizium anisopliae", "chemical_control": "Chlorpyrifos seed/soil treatment"},
    {"pest_id": "PEST_SUGARCANE_ESB", "name": "Early shoot borer", "scientific_name": "Chilo infuscatellus", "crop_hosts": "Sugarcane", "damage_symptoms": "Dead hearts in young crop", "cultural_control": "Trash mulching, early planting", "biological_control": "Trichogramma chilonis", "chemical_control": "Chlorantraniliprole"},
    {"pest_id": "PEST_GRAM_PB", "name": "Gram pod borer", "scientific_name": "Helicoverpa armigera", "crop_hosts": "Chickpea|Pigeonpea", "damage_symptoms": "Pod boring, seed loss", "cultural_control": "Pheromone traps, early sowing", "biological_control": "HaNPV, Bt", "chemical_control": "Emamectin, indoxacarb"},
    {"pest_id": "PEST_MANGO_HOPPER", "name": "Mango hopper", "scientific_name": "Idioscopus spp.", "crop_hosts": "Mango", "damage_symptoms": "Sucking sap, honeydew, sooty mould, flower drop", "cultural_control": "Pruning, orchard sanitation", "biological_control": "Predators, Beauveria", "chemical_control": "Imidacloprid at flowering"},
    {"pest_id": "PEST_BANANA_WEEVIL", "name": "Banana rhizome weevil", "scientific_name": "Cosmopolites sordidus", "crop_hosts": "Banana", "damage_symptoms": "Tunnels in rhizome, reduced bunch", "cultural_control": "Clean suckers, traps", "biological_control": "Entomopathogenic nematodes", "chemical_control": "Chlorpyrifos (judicious)"},
    {"pest_id": "PEST_JASSID", "name": "Jassids", "scientific_name": "Amrasca biguttula biguttula", "crop_hosts": "Cotton|Okra", "damage_symptoms": "Marginal yellowing (hopper burn), curling", "cultural_control": "Early sowing, balanced N", "biological_control": "Chrysoperla", "chemical_control": "Imidacloprid, thiamethoxam"},
]

# ─────────────────────────────────────────────────────────────────────────────
# Weeds
# ─────────────────────────────────────────────────────────────────────────────
WEEDS = [
    {"weed_id": "WEED_PARTHENIUM", "name": "Parthenium (Congress grass)", "scientific_name": "Parthenium hysterophorus", "hosts": "Upland, wastelands", "management": "Manual uprooting before flowering, competitive crops, biocontrol (Zygogramma)"},
    {"weed_id": "WEED_ECHINOCHLOA", "name": "Jungle rice", "scientific_name": "Echinochloa colona", "hosts": "Rice", "management": "Puddling, stale seedbed, pre-emergence herbicides"},
    {"weed_id": "WEED_CYPERUS", "name": "Purple nutsedge (Motha)", "scientific_name": "Cyperus rotundus", "hosts": "All crops", "management": "Deep ploughing, clean seed, sulfonylurea herbicides"},
    {"weed_id": "WEED_PHALARIS", "name": "Littleseed canarygrass", "scientific_name": "Phalaris minor", "hosts": "Wheat", "management": "Early sowing, clodinafop/sulfosulfuron (rotate modes of action)"},
    {"weed_id": "WEED_AVENA", "name": "Wild oats", "scientific_name": "Avena fatua", "hosts": "Wheat", "management": "Clean seed, crop rotation, post-emergence graminicides"},
    {"weed_id": "WEED_CYNODON", "name": "Bermuda grass (Doob)", "scientific_name": "Cynodon dactylon", "hosts": "All crops", "management": "Repeated cultivation, mulch, glyphosate on fallow"},
    {"weed_id": "WEED_CONVOLVULUS", "name": "Field bindweed", "scientific_name": "Convolvulus arvensis", "hosts": "Cereals|Vegetables", "management": "Deep tillage, cover crops, 2,4-D + glyphosate"},
    {"weed_id": "WEED_STRIGA", "name": "Witchweed", "scientific_name": "Striga spp.", "hosts": "Sorghum|Maize|Sugarcane", "management": "Trap crops, resistant varieties, avoid contaminated seed"},
]

# ─────────────────────────────────────────────────────────────────────────────
# Nutrients
# ─────────────────────────────────────────────────────────────────────────────
NUTRIENTS = [
    {"nutrient_id": "NUT_N", "symbol": "N", "name": "Nitrogen", "role": "Protein, chlorophyll, vegetative growth", "deficiency_symptoms": "Stunted growth, pale yellow older leaves"},
    {"nutrient_id": "NUT_P", "symbol": "P", "name": "Phosphorus", "role": "Energy (ATP), root development, flowering", "deficiency_symptoms": "Purple leaves, poor tillering, delayed maturity"},
    {"nutrient_id": "NUT_K", "symbol": "K", "name": "Potassium", "role": "Water regulation, stomata, disease resistance", "deficiency_symptoms": "Scorched leaf margins, weak stem, lodging"},
    {"nutrient_id": "NUT_S", "symbol": "S", "name": "Sulphur", "role": "Amino acids, oil synthesis", "deficiency_symptoms": "Uniform yellowing of young leaves"},
    {"nutrient_id": "NUT_ZN", "symbol": "Zn", "name": "Zinc", "role": "Enzyme co-factor, auxin", "deficiency_symptoms": "Khaira in rice (white bud), small leaves, interveinal chlorosis"},
    {"nutrient_id": "NUT_FE", "symbol": "Fe", "name": "Iron", "role": "Chlorophyll synthesis", "deficiency_symptoms": "Interveinal chlorosis of young leaves"},
    {"nutrient_id": "NUT_CU", "symbol": "Cu", "name": "Copper", "role": "Enzyme co-factor, lignin", "deficiency_symptoms": "Die-back of shoots, leaf tip necrosis"},
    {"nutrient_id": "NUT_MN", "symbol": "Mn", "name": "Manganese", "role": "Photosynthesis (O2 evolution)", "deficiency_symptoms": "Interveinal chlorosis with grey specks"},
    {"nutrient_id": "NUT_B", "symbol": "B", "name": "Boron", "role": "Cell wall, pollen tube growth", "deficiency_symptoms": "Distorted growth, hollow stem, fruit cracking"},
    {"nutrient_id": "NUT_MO", "symbol": "Mo", "name": "Molybdenum", "role": "N fixation, nitrate reduction", "deficiency_symptoms": "Whiptail in cauliflower, N-deficiency symptoms"},
    {"nutrient_id": "NUT_CA", "symbol": "Ca", "name": "Calcium", "role": "Cell wall, membrane", "deficiency_symptoms": "Blossom-end rot (tomato), tip burn"},
    {"nutrient_id": "NUT_MG", "symbol": "Mg", "name": "Magnesium", "role": "Chlorophyll core", "deficiency_symptoms": "Interveinal chlorosis of older leaves"},
]

# ─────────────────────────────────────────────────────────────────────────────
# Fertilizers (product) + nutrient composition (concept kept separate)
# ─────────────────────────────────────────────────────────────────────────────
FERTILIZERS = [
    {"fertilizer_id": "FERT_UREA", "name": "Urea", "category": "chemical", "composition": "N 46%", "notes": "Broadcast + immediate incorporation; avoid excess (lodging/pests)"},
    {"fertilizer_id": "FERT_DAP", "name": "DAP", "category": "chemical", "composition": "N 18%, P2O5 46%", "notes": "Basal phosphorus source"},
    {"fertilizer_id": "FERT_MOP", "name": "MOP (Muriate of potash)", "category": "chemical", "composition": "K2O 60%", "notes": "Chloride form; avoid in chloride-sensitive crops"},
    {"fertilizer_id": "FERT_SSP", "name": "SSP (Single super phosphate)", "category": "chemical", "composition": "P2O5 16%, Ca, S 11%", "notes": "Good in sulphur-deficient soils"},
    {"fertilizer_id": "FERT_AS", "name": "Ammonium sulphate", "category": "chemical", "composition": "N 21%, S 24%", "notes": "Acidifying; N+S source"},
    {"fertilizer_id": "FERT_NPK_102626", "name": "NPK 10:26:26", "category": "chemical", "composition": "N 10%, P2O5 26%, K2O 26%", "notes": "Complex fertilizer"},
    {"fertilizer_id": "FERT_NPK_123216", "name": "NPK 12:32:16", "category": "chemical", "composition": "N 12%, P2O5 32%, K2O 16%", "notes": "Complex fertilizer"},
    {"fertilizer_id": "FERT_NPK_171717", "name": "NPK 17:17:17", "category": "chemical", "composition": "N 17%, P2O5 17%, K2O 17%", "notes": "Balanced complex"},
    {"fertilizer_id": "FERT_NPK_202000", "name": "NPK 20:20:0", "category": "chemical", "composition": "N 20%, P2O5 20%", "notes": "No K"},
    {"fertilizer_id": "FERT_ZNSO4", "name": "Zinc sulphate", "category": "chemical", "composition": "Zn 21%, S 10%", "notes": "Micronutrient (soil/foliar)"},
    {"fertilizer_id": "FERT_BORAX", "name": "Borax", "category": "chemical", "composition": "B 10.5%", "notes": "Boron source"},
    {"fertilizer_id": "FERT_FESO4", "name": "Ferrous sulphate", "category": "chemical", "composition": "Fe 19%, S 11%", "notes": "Iron source"},
    {"fertilizer_id": "FERT_CAN", "name": "Calcium ammonium nitrate", "category": "chemical", "composition": "N 25%, Ca", "notes": "Nitrate N, less volatilization"},
    {"fertilizer_id": "FERT_GYPSUM", "name": "Gypsum", "category": "chemical", "composition": "Ca 23%, S 18%", "notes": "Sodic soil reclamation + S source"},
    {"fertilizer_id": "FERT_FYM", "name": "Farm yard manure (FYM)", "category": "organic", "composition": "Organic matter + NPK (low)", "notes": "Soil structure + slow nutrient release"},
    {"fertilizer_id": "FERT_COMPOST", "name": "Compost", "category": "organic", "composition": "Organic matter + nutrients", "notes": "Well-rotted before use"},
    {"fertilizer_id": "FERT_VERMI", "name": "Vermicompost", "category": "organic", "composition": "Organic matter + nutrients + humus", "notes": "Earthworm-processed compost"},
    {"fertilizer_id": "FERT_GREEN_MANURE", "name": "Green manure", "category": "organic", "composition": "N fixation + biomass (e.g. dhaincha, sunn hemp)", "notes": "Incorporate at flowering"},
]

BIOFERTILIZERS = [
    {"biofertilizer_id": "BIO_RHIZOBIUM", "name": "Rhizobium", "target": "Legumes (pulses, groundnut, soybean)", "function": "Symbiotic N fixation in nodules"},
    {"biofertilizer_id": "BIO_AZOTOBACTER", "name": "Azotobacter", "target": "Cereals, vegetables", "function": "Free-living N fixation"},
    {"biofertilizer_id": "BIO_AZOSPIRILLUM", "name": "Azospirillum", "target": "Cereals, millets", "function": "Associative N fixation"},
    {"biofertilizer_id": "BIO_PSB", "name": "PSB (Phosphate solubilizing bacteria)", "target": "All crops", "function": "Solubilizes fixed soil P"},
    {"biofertilizer_id": "BIO_KSB", "name": "KSB (Potash mobilizing bacteria)", "target": "All crops", "function": "Mobilizes soil K"},
    {"biofertilizer_id": "BIO_VAM", "name": "Mycorrhiza (VAM)", "target": "All crops", "function": "P/Zn uptake via fungal association"},
]

BIOCONTROLS = [
    {"biocontrol_id": "BC_TRICHODERMA", "name": "Trichoderma viride", "type": "fungus", "target": "Soil-borne fungi (wilt, damping-off, root rot)"},
    {"biocontrol_id": "BC_PSEUDOMONAS", "name": "Pseudomonas fluorescens", "type": "bacterium", "target": "Soil-borne + foliar pathogens, growth promotion"},
    {"biocontrol_id": "BC_BT", "name": "Bacillus thuringiensis (Bt)", "type": "bacterium", "target": "Lepidopteran larvae (bollworms, DBM, FAW)"},
    {"biocontrol_id": "BC_METARHIZIUM", "name": "Metarhizium anisopliae", "type": "fungus", "target": "White grub, locust, termites"},
    {"biocontrol_id": "BC_BEAUVERIA", "name": "Beauveria bassiana", "type": "fungus", "target": "Whitefly, hoppers, beetles"},
    {"biocontrol_id": "BC_NPV", "name": "NPV (Nuclear Polyhedrosis Virus)", "type": "virus", "target": "Helicoverpa, Spodoptera"},
    {"biocontrol_id": "BC_TRICHOGRAMMA", "name": "Trichogramma spp.", "type": "parasitoid", "target": "Eggs of stem borers, bollworms"},
    {"biocontrol_id": "BC_CHRYSOPERLA", "name": "Chrysoperla (green lacewing)", "type": "predator", "target": "Aphids, whitefly, eggs, small larvae"},
    {"biocontrol_id": "BC_CRYPTOLAEMUS", "name": "Cryptolaemus montrouzieri", "type": "predator", "target": "Mealybugs"},
]

# ─────────────────────────────────────────────────────────────────────────────
# Pesticides (CIB&RC label validity applies to every recommendation)
# ─────────────────────────────────────────────────────────────────────────────
PESTICIDES = [
    {"pesticide_id": "PESTC_CARBENDAZIM", "name": "Carbendazim", "type": "fungicide", "target": "Broad-spectrum (anthracnose, rusts)", "class": "FRAC 1 (benzimidazole)"},
    {"pesticide_id": "PESTC_MANCOZEB", "name": "Mancozeb", "type": "fungicide", "target": "Broad-spectrum protectant", "class": "FRAC M3 (dithiocarbamate)"},
    {"pesticide_id": "PESTC_COC", "name": "Copper oxychloride", "type": "fungicide", "target": "Bacterial + fungal", "class": "FRAC M1 (inorganic)"},
    {"pesticide_id": "PESTC_HEXACONAZOLE", "name": "Hexaconazole", "type": "fungicide", "target": "Powdery mildew, sheath blight, rust", "class": "FRAC 3 (triazole)"},
    {"pesticide_id": "PESTC_METALAXYL_MZ", "name": "Metalaxyl + Mancozeb", "type": "fungicide", "target": "Oomycetes (downy mildew, late blight)", "class": "FRAC 4 + M3"},
    {"pesticide_id": "PESTC_CHLOROTHALONIL", "name": "Chlorothalonil", "type": "fungicide", "target": "Broad-spectrum protectant", "class": "FRAC M5"},
    {"pesticide_id": "PESTC_SULPHUR", "name": "Wettable sulphur", "type": "fungicide/acaricide", "target": "Powdery mildew, mites", "class": "FRAC M2"},
    {"pesticide_id": "PESTC_IMIDACLOPRID", "name": "Imidacloprid", "type": "insecticide", "target": "Sucking pests (whitefly, jassid, aphid)", "class": "IRAC 4A (neonicotinoid)"},
    {"pesticide_id": "PESTC_THIAMETHOXAM", "name": "Thiamethoxam", "type": "insecticide", "target": "Sucking pests", "class": "IRAC 4A (neonicotinoid)"},
    {"pesticide_id": "PESTC_ACEPHATE", "name": "Acephate", "type": "insecticide", "target": "Broad-spectrum", "class": "IRAC 1B (organophosphate)"},
    {"pesticide_id": "PESTC_CHLORPYRIFOS", "name": "Chlorpyrifos", "type": "insecticide", "target": "Soil pests, termites, broad", "class": "IRAC 1B (organophosphate)"},
    {"pesticide_id": "PESTC_EMAMECTIN", "name": "Emamectin benzoate", "type": "insecticide", "target": "Lepidoptera (FAW, bollworms, borers)", "class": "IRAC 6 (avermectin)"},
    {"pesticide_id": "PESTC_SPINOSAD", "name": "Spinosad", "type": "insecticide", "target": "Lepidoptera, thrips", "class": "IRAC 5 (spinosyn)"},
    {"pesticide_id": "PESTC_CHLORANTRANILIPROLE", "name": "Chlorantraniliprole", "type": "insecticide", "target": "Lepidoptera", "class": "IRAC 28 (diamide)"},
    {"pesticide_id": "PESTC_FLUBENDIAMIDE", "name": "Flubendiamide", "type": "insecticide", "target": "Lepidoptera", "class": "IRAC 28 (diamide)"},
    {"pesticide_id": "PESTC_FIPRONIL", "name": "Fipronil", "type": "insecticide", "target": "Broad (termite, stem borer)", "class": "IRAC 2B (phenylpyrazole)"},
    {"pesticide_id": "PESTC_CARTAP", "name": "Cartap hydrochloride", "type": "insecticide", "target": "Stem borers", "class": "IRAC 14 (nereistoxin)"},
    {"pesticide_id": "PESTC_DIMETHOATE", "name": "Dimethoate", "type": "insecticide", "target": "Sucking pests", "class": "IRAC 1B (organophosphate)"},
]

# ─────────────────────────────────────────────────────────────────────────────
# Soils
# ─────────────────────────────────────────────────────────────────────────────
SOILS = [
    {"soil_id": "SOIL_ALLUVIAL", "name": "Alluvial", "characteristics": "Fertile, loamy, river-deposited; N/P low to medium, K high", "crops": "Rice, wheat, sugarcane, oilseeds"},
    {"soil_id": "SOIL_BLACK", "name": "Black (Regur)", "characteristics": "Clayey, moisture-retentive, cracks on drying; high Ca/Mg, low N/P", "crops": "Cotton, sorghum, soybean, pulses, sugarcane"},
    {"soil_id": "SOIL_RED", "name": "Red", "characteristics": "Acidic, well-drained, low N/P/humus; Fe-rich", "crops": "Millets, groundnut, pulses, horticulture"},
    {"soil_id": "SOIL_LATERITE", "name": "Laterite", "characteristics": "Highly weathered, acidic, low fertility, high Fe/Al", "crops": "Cashew, coconut, tea, rubber, coffee"},
    {"soil_id": "SOIL_DESERT", "name": "Desert", "characteristics": "Sandy, low organic matter, low water holding", "crops": "Bajra, guar, moth bean, pulses (irrigated)"},
    {"soil_id": "SOIL_SALINE", "name": "Saline & Alkaline", "characteristics": "High salts / high pH, poor structure, low infiltration", "crops": "Reclaim with gypsum; tolerant crops (barley, date palm)"},
    {"soil_id": "SOIL_FOREST", "name": "Forest & Mountain", "characteristics": "Variable, often acidic, high organic matter in upper layer", "crops": "Tea, spices, horticulture, apple"},
    {"soil_id": "SOIL_PEATY", "name": "Peaty & Marshy", "characteristics": "High organic matter, waterlogged, acidic", "crops": "Rice (after drainage), jute"},
]

# ─────────────────────────────────────────────────────────────────────────────
# Authority hierarchy (data-quality scoring)
# ─────────────────────────────────────────────────────────────────────────────
AUTHORITY_LEVELS = [
    {"key": "government", "name": "Government / ICAR / SAU", "score": 1.00},
    {"key": "research", "name": "Peer-reviewed research", "score": 0.95},
    {"key": "government_extension", "name": "KVK / government extension", "score": 0.90},
    {"key": "institution", "name": "Recognised agriculture institution", "score": 0.80},
    {"key": "specialist", "name": "Verified domain specialist", "score": 0.65},
    {"key": "blog", "name": "Agriculture blog", "score": 0.50},
    {"key": "farmer", "name": "Farmer anecdote", "score": 0.35},
    {"key": "social", "name": "Anonymous social-media claim", "score": 0.20},
]


