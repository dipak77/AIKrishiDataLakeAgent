"""Seed ontologies for the Agri Intelligence Lake (V1).

Curated, canonical content — never raw dataset names. This file is the source
of truth; `scripts/seed_lake.py` emits `data/seeds/*.csv` + the DuckDB/Parquet
lakehouse from it, and `domain/catalog.py` builds lookup indexes from it.

NOTE: agro-climatic zones / agro-ecological regions are representative
approximations (primary zone per state) and should be refined with official
ICAR/NBSS&LUP boundaries in a later milestone.
"""

from __future__ import annotations

import re

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
# ─────────────────────────────────────────────────────────────────────────────
# Geography: 36 states/UTs + full district coverage (~764 districts).
#
# District codes are deterministic slugs (IN-XX-NAME) generated from names —
# NOT official LGD/census codes. Names should be re-validated against the
# official Local Government Directory in a later import milestone.
# agroecological_region is an approximate primary NBSS&LUP AESR (descriptive).
# Latitude/longitude = state capital or district HQ (curated subset; the rest
# are pending geocoding — do not fabricate).
# ─────────────────────────────────────────────────────────────────────────────

def _slug(value):
    return re.sub(r"[^A-Za-z0-9]+", "", value).upper()


def _mk_districts(state_code, names, aliases=None, hq=None):
    out = []
    for name in names:
        d = {"code": f"{state_code}-{_slug(name)}", "name": name}
        if aliases and name in aliases:
            d["aliases"] = aliases[name]
        if hq and name in hq:
            d.update(hq[name])
        out.append(d)
    return out


# Curated district-HQ coordinates (major agri districts; ~0.1° precision).
# The remainder are left NULL (pending geocoding) — deliberately not fabricated.
DISTRICT_HQ = {
    "Pune": {"latitude": 18.52, "longitude": 73.86}, "Nagpur": {"latitude": 21.15, "longitude": 79.09},
    "Nashik": {"latitude": 20.00, "longitude": 73.79}, "Solapur": {"latitude": 17.66, "longitude": 75.91},
    "Jalgaon": {"latitude": 21.00, "longitude": 75.56}, "Ahmednagar": {"latitude": 19.10, "longitude": 74.75},
    "Aurangabad": {"latitude": 19.88, "longitude": 75.34}, "Kolhapur": {"latitude": 16.70, "longitude": 74.24},
    "Sangli": {"latitude": 16.85, "longitude": 74.58}, "Satara": {"latitude": 17.69, "longitude": 74.00},
    "Wardha": {"latitude": 20.74, "longitude": 78.60}, "Yavatmal": {"latitude": 20.39, "longitude": 78.13},
    "Akola": {"latitude": 20.70, "longitude": 77.00}, "Amravati": {"latitude": 20.93, "longitude": 77.76},
    "Latur": {"latitude": 18.40, "longitude": 76.58}, "Nanded": {"latitude": 19.14, "longitude": 77.32},
    "Parbhani": {"latitude": 19.27, "longitude": 76.77}, "Beed": {"latitude": 18.99, "longitude": 75.76},
    "Buldhana": {"latitude": 20.53, "longitude": 76.18}, "Chandrapur": {"latitude": 19.97, "longitude": 79.30},
    "Dhule": {"latitude": 20.90, "longitude": 74.77}, "Jalna": {"latitude": 19.84, "longitude": 75.89},
    "Nandurbar": {"latitude": 21.37, "longitude": 74.24}, "Ratnagiri": {"latitude": 16.99, "longitude": 73.30},
    "Sindhudurg": {"latitude": 16.13, "longitude": 73.69}, "Thane": {"latitude": 19.20, "longitude": 72.97},
    "Palghar": {"latitude": 19.70, "longitude": 72.77}, "Raigad": {"latitude": 18.52, "longitude": 73.18},
    "Belagavi": {"latitude": 15.85, "longitude": 74.50}, "Mysuru": {"latitude": 12.30, "longitude": 76.64},
    "Vijayapura": {"latitude": 16.83, "longitude": 75.71}, "Dharwad": {"latitude": 15.46, "longitude": 75.01},
    "Haveri": {"latitude": 14.79, "longitude": 75.40}, "Tumakuru": {"latitude": 13.34, "longitude": 77.10},
    "Kalaburagi": {"latitude": 17.33, "longitude": 76.83}, "Raichur": {"latitude": 16.21, "longitude": 77.36},
    "Ballari": {"latitude": 15.14, "longitude": 76.92}, "Chitradurga": {"latitude": 14.23, "longitude": 76.40},
    "Davanagere": {"latitude": 14.47, "longitude": 75.92}, "Shivamogga": {"latitude": 13.93, "longitude": 75.57},
    "Mandya": {"latitude": 12.52, "longitude": 76.90}, "Chikkamagaluru": {"latitude": 13.32, "longitude": 75.77},
    "Kodagu": {"latitude": 12.42, "longitude": 75.74}, "Gadag": {"latitude": 15.43, "longitude": 75.63},
    "Bagalkot": {"latitude": 16.18, "longitude": 75.70}, "Bidar": {"latitude": 17.91, "longitude": 77.52},
    "Yadgir": {"latitude": 16.77, "longitude": 77.14}, "Kolar": {"latitude": 13.13, "longitude": 78.13},
    "Hassan": {"latitude": 13.00, "longitude": 76.10},
    "Ludhiana": {"latitude": 30.90, "longitude": 75.86}, "Amritsar": {"latitude": 31.63, "longitude": 74.87},
    "Bathinda": {"latitude": 30.21, "longitude": 74.94}, "Sangrur": {"latitude": 30.25, "longitude": 75.84},
    "Patiala": {"latitude": 30.34, "longitude": 76.39}, "Ferozepur": {"latitude": 30.93, "longitude": 74.61},
    "Mansa": {"latitude": 29.99, "longitude": 75.40}, "Moga": {"latitude": 30.82, "longitude": 75.17},
    "Barnala": {"latitude": 30.37, "longitude": 75.55}, "Faridkot": {"latitude": 30.67, "longitude": 74.76},
    "Karnal": {"latitude": 29.69, "longitude": 76.99}, "Hisar": {"latitude": 29.15, "longitude": 75.72},
    "Sirsa": {"latitude": 29.53, "longitude": 75.03}, "Kaithal": {"latitude": 29.80, "longitude": 76.40},
    "Kurukshetra": {"latitude": 29.97, "longitude": 76.88}, "Sonipat": {"latitude": 28.99, "longitude": 77.02},
    "Rohtak": {"latitude": 28.90, "longitude": 76.59}, "Jind": {"latitude": 29.32, "longitude": 76.31},
    "Fatehabad": {"latitude": 29.51, "longitude": 75.45}, "Bhiwani": {"latitude": 28.80, "longitude": 76.13},
    "Panipat": {"latitude": 29.39, "longitude": 76.96}, "Ambala": {"latitude": 30.38, "longitude": 76.78},
    "Lucknow": {"latitude": 26.85, "longitude": 80.95}, "Varanasi": {"latitude": 25.32, "longitude": 83.01},
    "Kanpur Nagar": {"latitude": 26.45, "longitude": 80.33}, "Agra": {"latitude": 27.18, "longitude": 78.01},
    "Meerut": {"latitude": 28.98, "longitude": 77.71}, "Gorakhpur": {"latitude": 26.76, "longitude": 83.37},
    "Prayagraj": {"latitude": 25.44, "longitude": 81.85}, "Bareilly": {"latitude": 28.37, "longitude": 79.43},
    "Moradabad": {"latitude": 28.84, "longitude": 78.78}, "Saharanpur": {"latitude": 29.97, "longitude": 77.55},
    "Muzaffarnagar": {"latitude": 29.47, "longitude": 77.70}, "Aligarh": {"latitude": 27.88, "longitude": 78.08},
    "Jhansi": {"latitude": 25.45, "longitude": 78.57}, "Ayodhya": {"latitude": 26.80, "longitude": 82.20},
    "Mathura": {"latitude": 27.49, "longitude": 77.67},
    "Jaipur": {"latitude": 26.91, "longitude": 75.79}, "Jodhpur": {"latitude": 26.28, "longitude": 73.02},
    "Kota": {"latitude": 25.21, "longitude": 75.86}, "Sri Ganganagar": {"latitude": 29.90, "longitude": 73.88},
    "Hanumangarh": {"latitude": 29.58, "longitude": 74.32}, "Alwar": {"latitude": 27.55, "longitude": 76.63},
    "Barmer": {"latitude": 25.75, "longitude": 71.40}, "Bikaner": {"latitude": 28.02, "longitude": 73.31},
    "Udaipur": {"latitude": 24.58, "longitude": 73.69}, "Chittorgarh": {"latitude": 24.88, "longitude": 74.63},
    "Bhilwara": {"latitude": 25.35, "longitude": 74.64}, "Nagaur": {"latitude": 27.20, "longitude": 73.73},
    "Sikar": {"latitude": 27.61, "longitude": 75.14}, "Bharatpur": {"latitude": 27.22, "longitude": 77.49},
    "Indore": {"latitude": 22.72, "longitude": 75.86}, "Ujjain": {"latitude": 23.18, "longitude": 75.79},
    "Bhopal": {"latitude": 23.26, "longitude": 77.41}, "Jabalpur": {"latitude": 23.16, "longitude": 79.99},
    "Gwalior": {"latitude": 26.22, "longitude": 78.18}, "Sehore": {"latitude": 23.20, "longitude": 77.08},
    "Chhindwara": {"latitude": 22.06, "longitude": 78.94}, "Hoshangabad": {"latitude": 22.75, "longitude": 77.72},
    "Morena": {"latitude": 26.50, "longitude": 78.00}, "Sagar": {"latitude": 23.84, "longitude": 78.74},
    "Rewa": {"latitude": 24.54, "longitude": 81.30}, "Satna": {"latitude": 24.58, "longitude": 80.83},
    "Vidisha": {"latitude": 23.52, "longitude": 77.81}, "Ratlam": {"latitude": 23.33, "longitude": 75.04},
    "Mandsaur": {"latitude": 24.07, "longitude": 75.07}, "Khandwa": {"latitude": 21.83, "longitude": 76.35},
    "Khargone": {"latitude": 21.82, "longitude": 75.61}, "Dhar": {"latitude": 22.60, "longitude": 75.30},
    "Dewas": {"latitude": 22.96, "longitude": 76.06}, "Guna": {"latitude": 24.65, "longitude": 77.31},
    "Shivpuri": {"latitude": 25.42, "longitude": 77.66}, "Damoh": {"latitude": 23.84, "longitude": 79.44},
    "Balaghat": {"latitude": 21.81, "longitude": 80.18}, "Betul": {"latitude": 21.90, "longitude": 77.90},
    "Raisen": {"latitude": 23.33, "longitude": 77.78}, "Chhatarpur": {"latitude": 24.92, "longitude": 79.59},
    "Tikamgarh": {"latitude": 24.74, "longitude": 78.83}, "Panna": {"latitude": 24.72, "longitude": 80.19},
    "Sidhi": {"latitude": 24.40, "longitude": 81.88}, "Singrauli": {"latitude": 24.20, "longitude": 82.67},
    "Shahdol": {"latitude": 23.29, "longitude": 81.35}, "Anuppur": {"latitude": 23.10, "longitude": 81.68},
    "Katni": {"latitude": 23.83, "longitude": 80.39}, "Mandla": {"latitude": 22.60, "longitude": 80.37},
    "Seoni": {"latitude": 22.09, "longitude": 79.54}, "Bhind": {"latitude": 26.56, "longitude": 78.79},
    "Datia": {"latitude": 25.67, "longitude": 78.46}, "Ashoknagar": {"latitude": 24.58, "longitude": 77.73},
    "Rajgarh": {"latitude": 24.01, "longitude": 76.73}, "Neemuch": {"latitude": 24.48, "longitude": 74.87},
    "Jhabua": {"latitude": 22.77, "longitude": 74.59}, "Barwani": {"latitude": 22.03, "longitude": 74.90},
    "Burhanpur": {"latitude": 21.31, "longitude": 76.23}, "Harda": {"latitude": 22.34, "longitude": 77.10},
    "Agar Malwa": {"latitude": 23.71, "longitude": 76.02},
    "Guntur": {"latitude": 16.30, "longitude": 80.44}, "Kurnool": {"latitude": 15.83, "longitude": 78.04},
    "Anantapur": {"latitude": 14.68, "longitude": 77.60}, "Chittoor": {"latitude": 13.22, "longitude": 79.10},
    "Krishna": {"latitude": 16.50, "longitude": 80.64}, "West Godavari": {"latitude": 16.70, "longitude": 81.10},
    "Nizamabad": {"latitude": 18.67, "longitude": 78.10}, "Warangal": {"latitude": 17.97, "longitude": 79.59},
    "Karimnagar": {"latitude": 18.44, "longitude": 79.13}, "Mahbubnagar": {"latitude": 16.74, "longitude": 77.98},
    "Coimbatore": {"latitude": 11.02, "longitude": 76.96}, "Thanjavur": {"latitude": 10.79, "longitude": 79.14},
    "Erode": {"latitude": 11.34, "longitude": 77.72}, "Madurai": {"latitude": 9.93, "longitude": 78.12},
    "Villupuram": {"latitude": 11.94, "longitude": 79.49}, "Salem": {"latitude": 11.66, "longitude": 78.15},
    "Tiruchirappalli": {"latitude": 10.79, "longitude": 78.70}, "Cuddalore": {"latitude": 11.74, "longitude": 79.77},
    "Patna": {"latitude": 25.59, "longitude": 85.14}, "Muzaffarpur": {"latitude": 26.12, "longitude": 85.39},
    "Samastipur": {"latitude": 25.86, "longitude": 85.78}, "Purnia": {"latitude": 25.78, "longitude": 87.47},
    "Rohtas": {"latitude": 24.92, "longitude": 84.02}, "Bhagalpur": {"latitude": 25.24, "longitude": 86.98},
    "Bargarh": {"latitude": 21.33, "longitude": 83.62}, "Cuttack": {"latitude": 20.46, "longitude": 85.88},
    "Ganjam": {"latitude": 19.39, "longitude": 85.05}, "Mayurbhanj": {"latitude": 21.93, "longitude": 86.73},
    "Kendrapara": {"latitude": 20.50, "longitude": 86.42},
}

GEOGRAPHY = [
    {"state_code": "IN-AP", "name": "Andhra Pradesh", "type": "state", "agroclimatic_zone": "East Coast Plains and Hills",
     "agroecological_region": "Deccan Plateau (Hot Semi-arid)", "latitude": 16.51, "longitude": 80.52,
     "districts": _mk_districts("IN-AP", [
        "Alluri Sitharama Raju", "Anakapalli", "Anantapur", "Annamayya", "Bapatla", "Chittoor",
        "East Godavari", "Eluru", "Guntur", "Kadapa", "Kakinada", "Konaseema", "Krishna", "Kurnool",
        "Nandyal", "Nellore", "NTR", "Palnadu", "Parvathipuram Manyam", "Prakasam", "Sri Sathya Sai",
        "Srikakulam", "Tirupati", "Visakhapatnam", "Vizianagaram", "West Godavari"],
        aliases={"Kadapa": ["YSR Kadapa", "Cuddapah"], "Nellore": ["Sri Potti Sriramulu Nellore", "SPSR Nellore"]},
        hq=DISTRICT_HQ)},
    {"state_code": "IN-AR", "name": "Arunachal Pradesh", "type": "state", "agroclimatic_zone": "Eastern Himalayan Region",
     "agroecological_region": "Eastern Himalayas (Warm Perhumid)", "latitude": 27.08, "longitude": 93.61,
     "districts": _mk_districts("IN-AR", [
        "Anjaw", "Changlang", "Dibang Valley", "East Kameng", "East Siang", "Kamle", "Kra Daadi",
        "Kurung Kumey", "Lepa Rada", "Lohit", "Longding", "Lower Dibang Valley", "Lower Siang",
        "Lower Subansiri", "Namsai", "Pakke-Kessang", "Papum Pare", "Shi Yomi", "Siang", "Tawang",
        "Tirap", "Upper Dibang Valley", "Upper Siang", "Upper Subansiri", "West Kameng", "West Siang"], hq=DISTRICT_HQ)},
    {"state_code": "IN-AS", "name": "Assam", "type": "state", "agroclimatic_zone": "Eastern Himalayan Region",
     "agroecological_region": "Assam & Bengal Plains (Hot Subhumid)", "latitude": 26.14, "longitude": 91.79,
     "districts": _mk_districts("IN-AS", [
        "Baksa", "Barpeta", "Biswanath", "Bongaigaon", "Cachar", "Charaideo", "Chirang", "Darrang",
        "Dhemaji", "Dhubri", "Dibrugarh", "Dima Hasao", "Goalpara", "Golaghat", "Hailakandi", "Hojai",
        "Jorhat", "Kamrup", "Kamrup Metropolitan", "Karbi Anglong", "Karimganj", "Kokrajhar",
        "Lakhimpur", "Majuli", "Morigaon", "Nagaon", "Nalbari", "Sivasagar", "Sonitpur",
        "South Salmara-Mankachar", "Tinsukia", "Udalguri", "West Karbi Anglong"], hq=DISTRICT_HQ)},
    {"state_code": "IN-BR", "name": "Bihar", "type": "state", "agroclimatic_zone": "Middle Gangetic Plains",
     "agroecological_region": "Eastern Plain (Hot Subhumid)", "latitude": 25.59, "longitude": 85.14,
     "districts": _mk_districts("IN-BR", [
        "Araria", "Arwal", "Aurangabad", "Banka", "Begusarai", "Bhagalpur", "Bhojpur", "Buxar",
        "Darbhanga", "East Champaran", "Gaya", "Gopalganj", "Jamui", "Jehanabad", "Kaimur", "Katihar",
        "Khagaria", "Kishanganj", "Lakhisarai", "Madhepura", "Madhubani", "Munger", "Muzaffarpur",
        "Nalanda", "Nawada", "Patna", "Purnia", "Rohtas", "Saharsa", "Samastipur", "Saran", "Sheikhpura",
        "Sheohar", "Sitamarhi", "Siwan", "Supaul", "Vaishali", "West Champaran"], hq=DISTRICT_HQ)},
    {"state_code": "IN-CT", "name": "Chhattisgarh", "type": "state", "agroclimatic_zone": "Eastern Plateau and Hills",
     "agroecological_region": "Eastern Plateau (Hot Subhumid)", "latitude": 21.25, "longitude": 81.63,
     "districts": _mk_districts("IN-CT", [
        "Balod", "Baloda Bazar", "Balrampur", "Bastar", "Bemetara", "Bijapur", "Bilaspur", "Dantewada",
        "Dhamtari", "Durg", "Gariaband", "Gaurela-Pendra-Marwahi", "Janjgir-Champa", "Jashpur",
        "Kabirdham", "Kanker", "Khairagarh", "Kondagaon", "Korba", "Koriya", "Mahasamund",
        "Manendragarh", "Mohla-Manpur", "Mungeli", "Narayanpur", "Raigarh", "Raipur", "Rajnandgaon",
        "Sarangarh-Bilaigarh", "Sukma", "Surajpur", "Surguja"], hq=DISTRICT_HQ)},
    {"state_code": "IN-GA", "name": "Goa", "type": "state", "agroclimatic_zone": "West Coast Plains and Ghats",
     "agroecological_region": "Western Ghats & Coastal Plain (Hot Humid)", "latitude": 15.49, "longitude": 73.83,
     "districts": _mk_districts("IN-GA", ["North Goa", "South Goa"], hq=DISTRICT_HQ)},
    {"state_code": "IN-GJ", "name": "Gujarat", "type": "state", "agroclimatic_zone": "Gujarat Plains and Hills",
     "agroecological_region": "Gujarat Plains (Hot Semiarid)", "latitude": 23.22, "longitude": 72.65,
     "districts": _mk_districts("IN-GJ", [
        "Ahmedabad", "Amreli", "Anand", "Aravalli", "Banaskantha", "Bharuch", "Bhavnagar", "Botad",
        "Chhota Udaipur", "Dahod", "Dang", "Devbhoomi Dwarka", "Gandhinagar", "Gir Somnath", "Jamnagar",
        "Junagadh", "Kheda", "Kutch", "Mahisagar", "Mehsana", "Morbi", "Narmada", "Navsari",
        "Panchmahal", "Patan", "Porbandar", "Rajkot", "Sabarkantha", "Surat", "Surendranagar", "Tapi",
        "Vadodara", "Valsad"], hq=DISTRICT_HQ)},
    {"state_code": "IN-HR", "name": "Haryana", "type": "state", "agroclimatic_zone": "Trans-Gangetic Plains",
     "agroecological_region": "Northern Plain (Hot Subhumid)", "latitude": 30.73, "longitude": 76.78,
     "districts": _mk_districts("IN-HR", [
        "Ambala", "Bhiwani", "Charkhi Dadri", "Faridabad", "Fatehabad", "Gurugram", "Hisar", "Jhajjar",
        "Jind", "Kaithal", "Karnal", "Kurukshetra", "Mahendragarh", "Nuh", "Palwal", "Panchkula",
        "Panipat", "Rewari", "Rohtak", "Sirsa", "Sonipat", "Yamunanagar"], hq=DISTRICT_HQ)},
    {"state_code": "IN-HP", "name": "Himachal Pradesh", "type": "state", "agroclimatic_zone": "Western Himalayan Region",
     "agroecological_region": "Western Himalayas (Warm Subhumid)", "latitude": 31.10, "longitude": 77.17,
     "districts": _mk_districts("IN-HP", [
        "Bilaspur", "Chamba", "Hamirpur", "Kangra", "Kinnaur", "Kullu", "Lahaul and Spiti", "Mandi",
        "Shimla", "Sirmaur", "Solan", "Una"], hq=DISTRICT_HQ)},
    {"state_code": "IN-JH", "name": "Jharkhand", "type": "state", "agroclimatic_zone": "Eastern Plateau and Hills",
     "agroecological_region": "Eastern Plateau (Hot Subhumid)", "latitude": 23.34, "longitude": 85.31,
     "districts": _mk_districts("IN-JH", [
        "Bokaro", "Chatra", "Deoghar", "Dhanbad", "Dumka", "East Singhbhum", "Garhwa", "Giridih",
        "Godda", "Gumla", "Hazaribagh", "Jamtara", "Khunti", "Koderma", "Latehar", "Lohardaga",
        "Pakur", "Palamu", "Ramgarh", "Ranchi", "Sahebganj", "Seraikela-Kharsawan", "Simdega",
        "West Singhbhum"], hq=DISTRICT_HQ)},
    {"state_code": "IN-KA", "name": "Karnataka", "type": "state", "agroclimatic_zone": "Southern Plateau and Hills",
     "agroecological_region": "Deccan Plateau (Hot Semi-arid)", "latitude": 12.97, "longitude": 77.59,
     "districts": _mk_districts("IN-KA", [
        "Bagalkot", "Ballari", "Belagavi", "Bengaluru Rural", "Bengaluru Urban", "Bidar",
        "Chamarajanagar", "Chikkaballapur", "Chikkamagaluru", "Chitradurga", "Dakshina Kannada",
        "Davanagere", "Dharwad", "Gadag", "Hassan", "Haveri", "Kalaburagi", "Kodagu", "Kolar",
        "Koppal", "Mandya", "Mysuru", "Raichur", "Ramanagara", "Shivamogga", "Tumakuru", "Udupi",
        "Uttara Kannada", "Vijayanagara", "Vijayapura", "Yadgir"],
        aliases={"Belagavi": ["Belgaum"], "Mysuru": ["Mysore"], "Vijayapura": ["Bijapur"],
                 "Chikkamagaluru": ["Chikmagalur"], "Shivamogga": ["Shimoga"], "Ballari": ["Bellary"],
                 "Kalaburagi": ["Gulbarga"]}, hq=DISTRICT_HQ)},
    {"state_code": "IN-KL", "name": "Kerala", "type": "state", "agroclimatic_zone": "West Coast Plains and Ghats",
     "agroecological_region": "Western Ghats & Coastal Plain (Hot Humid)", "latitude": 8.52, "longitude": 76.94,
     "districts": _mk_districts("IN-KL", [
        "Alappuzha", "Ernakulam", "Idukki", "Kannur", "Kasaragod", "Kollam", "Kottayam", "Kozhikode",
        "Malappuram", "Palakkad", "Pathanamthitta", "Thiruvananthapuram", "Thrissur", "Wayanad"], hq=DISTRICT_HQ)},
    {"state_code": "IN-MP", "name": "Madhya Pradesh", "type": "state", "agroclimatic_zone": "Central Plateau and Hills",
     "agroecological_region": "Central Highlands (Hot Semiarid)", "latitude": 23.26, "longitude": 77.41,
     "districts": _mk_districts("IN-MP", [
        "Agar Malwa", "Alirajpur", "Anuppur", "Ashoknagar", "Balaghat", "Barwani", "Betul", "Bhind",
        "Bhopal", "Burhanpur", "Chhatarpur", "Chhindwara", "Damoh", "Datia", "Dewas", "Dhar", "Dindori",
        "Guna", "Gwalior", "Harda", "Hoshangabad", "Indore", "Jabalpur", "Jhabua", "Katni", "Khandwa",
        "Khargone", "Maihar", "Mandla", "Mandsaur", "Morena", "Narsinghpur", "Neemuch", "Niwari",
        "Panna", "Raisen", "Rajgarh", "Ratlam", "Rewa", "Sagar", "Satna", "Sehore", "Seoni", "Shahdol",
        "Shajapur", "Sheopur", "Shivpuri", "Sidhi", "Singrauli", "Tikamgarh", "Ujjain", "Umaria",
        "Vidisha"], aliases={"Hoshangabad": ["Narmadapuram"]}, hq=DISTRICT_HQ)},
    {"state_code": "IN-MH", "name": "Maharashtra", "type": "state", "agroclimatic_zone": "Western Plateau and Hills",
     "agroecological_region": "Deccan Plateau (Hot Semi-arid)", "latitude": 19.08, "longitude": 72.88,
     "districts": _mk_districts("IN-MH", [
        "Ahmednagar", "Akola", "Amravati", "Aurangabad", "Beed", "Bhandara", "Buldhana", "Chandrapur",
        "Dhule", "Gadchiroli", "Gondia", "Hingoli", "Jalgaon", "Jalna", "Kolhapur", "Latur",
        "Mumbai City", "Mumbai Suburban", "Nagpur", "Nanded", "Nandurbar", "Nashik", "Osmanabad",
        "Palghar", "Parbhani", "Pune", "Raigad", "Ratnagiri", "Sangli", "Satara", "Sindhudurg",
        "Solapur", "Thane", "Wardha", "Washim", "Yavatmal"],
        aliases={"Aurangabad": ["Chhatrapati Sambhajinagar"], "Osmanabad": ["Dharashiv"]}, hq=DISTRICT_HQ)},
    {"state_code": "IN-MN", "name": "Manipur", "type": "state", "agroclimatic_zone": "Eastern Himalayan Region",
     "agroecological_region": "North-Eastern Hills (Warm Perhumid)", "latitude": 24.82, "longitude": 93.94,
     "districts": _mk_districts("IN-MN", [
        "Bishnupur", "Chandel", "Churachandpur", "Imphal East", "Imphal West", "Jiribam", "Kakching",
        "Kamjong", "Kangpokpi", "Noney", "Pherzawl", "Senapati", "Tamenglong", "Tengnoupal", "Thoubal",
        "Ukhrul"], hq=DISTRICT_HQ)},
    {"state_code": "IN-ML", "name": "Meghalaya", "type": "state", "agroclimatic_zone": "Eastern Himalayan Region",
     "agroecological_region": "Eastern Himalayas (Warm Perhumid)", "latitude": 25.58, "longitude": 91.89,
     "districts": _mk_districts("IN-ML", [
        "East Garo Hills", "East Jaintia Hills", "East Khasi Hills", "Eastern West Khasi Hills",
        "North Garo Hills", "Ri Bhoi", "South Garo Hills", "South West Garo Hills",
        "South West Khasi Hills", "West Garo Hills", "West Jaintia Hills", "West Khasi Hills"], hq=DISTRICT_HQ)},
    {"state_code": "IN-MZ", "name": "Mizoram", "type": "state", "agroclimatic_zone": "Eastern Himalayan Region",
     "agroecological_region": "North-Eastern Hills (Warm Perhumid)", "latitude": 23.73, "longitude": 92.72,
     "districts": _mk_districts("IN-MZ", [
        "Aizawl", "Champhai", "Hnahthial", "Khawzawl", "Kolasib", "Lawngtlai", "Lunglei", "Mamit",
        "Saiha", "Saitual", "Serchhip"], hq=DISTRICT_HQ)},
    {"state_code": "IN-NL", "name": "Nagaland", "type": "state", "agroclimatic_zone": "Eastern Himalayan Region",
     "agroecological_region": "North-Eastern Hills (Warm Perhumid)", "latitude": 25.67, "longitude": 94.11,
     "districts": _mk_districts("IN-NL", [
        "Chumoukedima", "Dimapur", "Kiphire", "Kohima", "Longleng", "Mokokchung", "Mon", "Niuland",
        "Noklak", "Peren", "Phek", "Shamator", "Tseminyu", "Tuensang", "Wokha", "Zunheboto"], hq=DISTRICT_HQ)},
    {"state_code": "IN-OD", "name": "Odisha", "type": "state", "agroclimatic_zone": "East Coast Plains and Hills",
     "agroecological_region": "Eastern Coastal Plain (Hot Humid)", "latitude": 20.30, "longitude": 85.82,
     "districts": _mk_districts("IN-OD", [
        "Angul", "Balangir", "Balasore", "Bargarh", "Bhadrak", "Boudh", "Cuttack", "Deogarh",
        "Dhenkanal", "Gajapati", "Ganjam", "Jagatsinghpur", "Jajpur", "Jharsuguda", "Kalahandi",
        "Kandhamal", "Kendrapara", "Kendujhar", "Khordha", "Koraput", "Malkangiri", "Mayurbhanj",
        "Nabarangpur", "Nayagarh", "Nuapada", "Puri", "Rayagada", "Sambalpur", "Subarnapur",
        "Sundargarh"], hq=DISTRICT_HQ)},
    {"state_code": "IN-PB", "name": "Punjab", "type": "state", "agroclimatic_zone": "Trans-Gangetic Plains",
     "agroecological_region": "Northern Plain (Hot Subhumid)", "latitude": 30.73, "longitude": 76.78,
     "districts": _mk_districts("IN-PB", [
        "Amritsar", "Barnala", "Bathinda", "Faridkot", "Fatehgarh Sahib", "Fazilka", "Ferozepur",
        "Gurdaspur", "Hoshiarpur", "Jalandhar", "Kapurthala", "Ludhiana", "Malerkotla", "Mansa",
        "Moga", "Pathankot", "Patiala", "Rupnagar", "Sahibzada Ajit Singh Nagar", "Sangrur",
        "Shahid Bhagat Singh Nagar", "Sri Muktsar Sahib", "Tarn Taran"],
        aliases={"Sahibzada Ajit Singh Nagar": ["Mohali", "SAS Nagar"],
                 "Shahid Bhagat Singh Nagar": ["Nawanshahr"], "Sri Muktsar Sahib": ["Muktsar"]},
        hq=DISTRICT_HQ)},
    {"state_code": "IN-RJ", "name": "Rajasthan", "type": "state", "agroclimatic_zone": "Western Dry Region",
     "agroecological_region": "Western Dry Region (Hot Arid)", "latitude": 26.91, "longitude": 75.79,
     "districts": _mk_districts("IN-RJ", [
        "Ajmer", "Alwar", "Banswara", "Baran", "Barmer", "Bharatpur", "Bhilwara", "Bikaner", "Bundi",
        "Chittorgarh", "Churu", "Dausa", "Dholpur", "Dungarpur", "Hanumangarh", "Jaipur", "Jaisalmer",
        "Jalore", "Jhalawar", "Jhunjhunu", "Jodhpur", "Karauli", "Kota", "Nagaur", "Pali",
        "Pratapgarh", "Rajsamand", "Sawai Madhopur", "Sikar", "Sirohi", "Sri Ganganagar", "Tonk",
        "Udaipur"], aliases={"Sri Ganganagar": ["Ganganagar"]}, hq=DISTRICT_HQ)},
    {"state_code": "IN-SK", "name": "Sikkim", "type": "state", "agroclimatic_zone": "Eastern Himalayan Region",
     "agroecological_region": "Eastern Himalayas (Warm Perhumid)", "latitude": 27.33, "longitude": 88.61,
     "districts": _mk_districts("IN-SK", [
        "East Sikkim", "North Sikkim", "Pakyong", "Soreng", "South Sikkim", "West Sikkim"], hq=DISTRICT_HQ)},
    {"state_code": "IN-TN", "name": "Tamil Nadu", "type": "state", "agroclimatic_zone": "Southern Plateau and Hills",
     "agroecological_region": "Eastern Coastal Plain (Hot Humid)", "latitude": 13.08, "longitude": 80.27,
     "districts": _mk_districts("IN-TN", [
        "Ariyalur", "Chengalpattu", "Chennai", "Coimbatore", "Cuddalore", "Dharmapuri", "Dindigul",
        "Erode", "Kallakurichi", "Kancheepuram", "Kanyakumari", "Karur", "Krishnagiri", "Madurai",
        "Mayiladuthurai", "Nagapattinam", "Namakkal", "Nilgiris", "Perambalur", "Pudukkottai",
        "Ramanathapuram", "Ranipet", "Salem", "Sivaganga", "Tenkasi", "Thanjavur", "Theni",
        "Thoothukudi", "Tiruchirappalli", "Tirunelveli", "Tirupathur", "Tiruppur", "Tiruvallur",
        "Tiruvannamalai", "Tiruvarur", "Vellore", "Viluppuram", "Virudhunagar"],
        aliases={"Thanjavur": ["Tanjore"], "Viluppuram": ["Villupuram"], "Thoothukudi": ["Tuticorin"],
                 "Tiruchirappalli": ["Trichy", "Tiruchirapalli"], "Kancheepuram": ["Kanchipuram"],
                 "Nilgiris": ["The Nilgiris"]}, hq=DISTRICT_HQ)},
    {"state_code": "IN-TG", "name": "Telangana", "type": "state", "agroclimatic_zone": "Southern Plateau and Hills",
     "agroecological_region": "Deccan Plateau (Hot Semi-arid)", "latitude": 17.38, "longitude": 78.49,
     "districts": _mk_districts("IN-TG", [
        "Adilabad", "Bhadradri Kothagudem", "Hanamkonda", "Hyderabad", "Jagtial", "Jangaon",
        "Jayashankar Bhupalpally", "Jogulamba Gadwal", "Kamareddy", "Karimnagar", "Khammam",
        "Komaram Bheem", "Mahabubabad", "Mahbubnagar", "Mancherial", "Medak", "Medchal-Malkajgiri",
        "Mulugu", "Nagarkurnool", "Nalgonda", "Narayanpet", "Nirmal", "Nizamabad", "Peddapalli",
        "Rajanna Sircilla", "Rangareddy", "Sangareddy", "Siddipet", "Suryapet", "Vikarabad",
        "Wanaparthy", "Warangal", "Yadadri Bhuvanagiri"], hq=DISTRICT_HQ)},
    {"state_code": "IN-TR", "name": "Tripura", "type": "state", "agroclimatic_zone": "Eastern Himalayan Region",
     "agroecological_region": "North-Eastern Hills (Warm Perhumid)", "latitude": 23.83, "longitude": 91.29,
     "districts": _mk_districts("IN-TR", [
        "Dhalai", "Gomati", "Khowai", "North Tripura", "Sepahijala", "South Tripura", "Unakoti",
        "West Tripura"], hq=DISTRICT_HQ)},
    {"state_code": "IN-UP", "name": "Uttar Pradesh", "type": "state", "agroclimatic_zone": "Upper Gangetic Plains",
     "agroecological_region": "Upper Gangetic Plains (Hot Subhumid)", "latitude": 26.85, "longitude": 80.95,
     "districts": _mk_districts("IN-UP", [
        "Agra", "Aligarh", "Ambedkar Nagar", "Amethi", "Amroha", "Auraiya", "Ayodhya", "Azamgarh",
        "Baghpat", "Bahraich", "Ballia", "Balrampur", "Banda", "Barabanki", "Bareilly", "Basti",
        "Bhadohi", "Bijnor", "Budaun", "Bulandshahr", "Chandauli", "Chitrakoot", "Deoria", "Etah",
        "Etawah", "Farrukhabad", "Fatehpur", "Firozabad", "Gautam Buddha Nagar", "Ghaziabad",
        "Ghazipur", "Gonda", "Gorakhpur", "Hamirpur", "Hapur", "Hardoi", "Hathras", "Jalaun",
        "Jaunpur", "Jhansi", "Kannauj", "Kanpur Dehat", "Kanpur Nagar", "Kasganj", "Kaushambi",
        "Kheri", "Kushinagar", "Lalitpur", "Lucknow", "Maharajganj", "Mahoba", "Mainpuri", "Mathura",
        "Mau", "Meerut", "Mirzapur", "Moradabad", "Muzaffarnagar", "Pilibhit", "Pratapgarh",
        "Prayagraj", "Raebareli", "Rampur", "Saharanpur", "Sambhal", "Sant Kabir Nagar",
        "Shahjahanpur", "Shamli", "Shravasti", "Siddharthnagar", "Sitapur", "Sonbhadra", "Sultanpur",
        "Unnao", "Varanasi"],
        aliases={"Kanpur Nagar": ["Kanpur"], "Gautam Buddha Nagar": ["Noida", "GB Nagar"],
                 "Prayagraj": ["Allahabad"], "Ayodhya": ["Faizabad"], "Bhadohi": ["Sant Ravidas Nagar"],
                 "Kheri": ["Lakhimpur Kheri"]}, hq=DISTRICT_HQ)},
    {"state_code": "IN-UK", "name": "Uttarakhand", "type": "state", "agroclimatic_zone": "Western Himalayan Region",
     "agroecological_region": "Western Himalayas (Warm Subhumid)", "latitude": 30.32, "longitude": 78.03,
     "districts": _mk_districts("IN-UK", [
        "Almora", "Bageshwar", "Chamoli", "Champawat", "Dehradun", "Haridwar", "Nainital",
        "Pauri Garhwal", "Pithoragarh", "Rudraprayag", "Tehri Garhwal", "Udham Singh Nagar",
        "Uttarkashi"], aliases={"Udham Singh Nagar": ["US Nagar"]}, hq=DISTRICT_HQ)},
    {"state_code": "IN-WB", "name": "West Bengal", "type": "state", "agroclimatic_zone": "Lower Gangetic Plains",
     "agroecological_region": "Lower Gangetic Plain (Hot Subhumid)", "latitude": 22.57, "longitude": 88.36,
     "districts": _mk_districts("IN-WB", [
        "Alipurduar", "Bankura", "Birbhum", "Cooch Behar", "Dakshin Dinajpur", "Darjeeling", "Hooghly",
        "Howrah", "Jalpaiguri", "Jhargram", "Kalimpong", "Kolkata", "Malda", "Murshidabad", "Nadia",
        "North 24 Parganas", "Paschim Bardhaman", "Paschim Medinipur", "Purba Bardhaman",
        "Purba Medinipur", "Purulia", "South 24 Parganas", "Uttar Dinajpur"],
        aliases={"Purba Bardhaman": ["Bardhaman", "Burdwan"], "Paschim Medinipur": ["West Midnapore"],
                 "Purba Medinipur": ["East Midnapore"]}, hq=DISTRICT_HQ)},
    {"state_code": "IN-AN", "name": "Andaman and Nicobar Islands", "type": "UT", "agroclimatic_zone": "The Islands Region",
     "agroecological_region": "Islands (Hot Humid)", "latitude": 11.62, "longitude": 92.73,
     "districts": _mk_districts("IN-AN", ["Nicobar", "North and Middle Andaman", "South Andaman"], hq=DISTRICT_HQ)},
    {"state_code": "IN-CH", "name": "Chandigarh", "type": "UT", "agroclimatic_zone": "Trans-Gangetic Plains",
     "agroecological_region": "Northern Plain (Hot Subhumid)", "latitude": 30.73, "longitude": 76.78,
     "districts": _mk_districts("IN-CH", ["Chandigarh"], hq=DISTRICT_HQ)},
    {"state_code": "IN-DH", "name": "Dadra and Nagar Haveli and Daman and Diu", "type": "UT", "agroclimatic_zone": "Gujarat Plains and Hills",
     "agroecological_region": "Western Coastal Plain (Hot Humid)", "latitude": 20.40, "longitude": 72.83,
     "districts": _mk_districts("IN-DH", ["Dadra and Nagar Haveli", "Daman", "Diu"], hq=DISTRICT_HQ)},
    {"state_code": "IN-DL", "name": "Delhi", "type": "UT", "agroclimatic_zone": "Trans-Gangetic Plains",
     "agroecological_region": "Northern Plain (Hot Subhumid)", "latitude": 28.61, "longitude": 77.21,
     "districts": _mk_districts("IN-DL", [
        "Central Delhi", "East Delhi", "New Delhi", "North Delhi", "North East Delhi", "North West Delhi",
        "Shahdara", "South Delhi", "South East Delhi", "South West Delhi", "West Delhi"], hq=DISTRICT_HQ)},
    {"state_code": "IN-JK", "name": "Jammu and Kashmir", "type": "UT", "agroclimatic_zone": "Western Himalayan Region",
     "agroecological_region": "Western Himalayas (Warm Subhumid)", "latitude": 34.08, "longitude": 74.80,
     "districts": _mk_districts("IN-JK", [
        "Anantnag", "Bandipora", "Baramulla", "Budgam", "Doda", "Ganderbal", "Jammu", "Kathua",
        "Kishtwar", "Kulgam", "Kupwara", "Poonch", "Pulwama", "Rajouri", "Ramban", "Reasi", "Samba",
        "Shopian", "Srinagar", "Udhampur"], hq=DISTRICT_HQ)},
    {"state_code": "IN-LA", "name": "Ladakh", "type": "UT", "agroclimatic_zone": "Western Himalayan Region",
     "agroecological_region": "Western Himalayas (Cold Arid)", "latitude": 34.15, "longitude": 77.58,
     "districts": _mk_districts("IN-LA", ["Kargil", "Leh"], hq=DISTRICT_HQ)},
    {"state_code": "IN-LD", "name": "Lakshadweep", "type": "UT", "agroclimatic_zone": "The Islands Region",
     "agroecological_region": "Islands (Hot Humid)", "latitude": 10.57, "longitude": 72.64,
     "districts": _mk_districts("IN-LD", ["Lakshadweep"], hq=DISTRICT_HQ)},
    {"state_code": "IN-PY", "name": "Puducherry", "type": "UT", "agroclimatic_zone": "East Coast Plains and Hills",
     "agroecological_region": "Eastern Coastal Plain (Hot Humid)", "latitude": 11.94, "longitude": 79.83,
     "districts": _mk_districts("IN-PY", ["Karaikal", "Mahe", "Puducherry", "Yanam"], hq=DISTRICT_HQ)},
]

GEOGRAPHY_ALIASES = {
    "IN-OD": ["Orissa"],
    "IN-UK": ["Uttaranchal"],
    "IN-CT": ["CG"],
    "IN-PY": ["Pondicherry"],
    "IN-DL": ["NCT of Delhi", "National Capital Territory of Delhi"],
    "IN-DH": ["Daman and Diu", "Dadra and Nagar Haveli"],
    "IN-JK": ["J&K", "Jammu & Kashmir"],
    "IN-WB": ["Bengal"],
    "IN-AN": ["Andaman", "A & N Islands"],
}

# Representative subdistrict / tehsil / block / village hierarchy (full
# ~6000-block + ~6.6 lakh village import is a later LGD milestone).
SUBDISTRICT_EXAMPLES = [
    {"state_code": "IN-MH", "district_code": "IN-MH-PUNE",
     "subdistricts": [
        {"name": "Haveli", "type": "tehsil"}, {"name": "Baramati", "type": "tehsil"},
        {"name": "Purandar", "type": "tehsil"}, {"name": "Indapur", "type": "tehsil"},
        {"name": "Daund", "type": "tehsil"}, {"name": "Shirur", "type": "tehsil"},
        {"name": "Junnar", "type": "tehsil"}, {"name": "Khed", "type": "tehsil"},
        {"name": "Maval", "type": "tehsil"}, {"name": "Mulshi", "type": "tehsil"}],
     "villages": ["Uruli Kanchan", "Manchar", "Saswad", "Indapur"]},
    {"state_code": "IN-MH", "district_code": "IN-MH-NAGPUR",
     "subdistricts": [
        {"name": "Nagpur Rural", "type": "tehsil"}, {"name": "Kamptee", "type": "tehsil"},
        {"name": "Umred", "type": "tehsil"}, {"name": "Hingna", "type": "tehsil"},
        {"name": "Kalmeshwar", "type": "tehsil"}, {"name": "Katol", "type": "tehsil"},
        {"name": "Narkhed", "type": "tehsil"}, {"name": "Ramtek", "type": "tehsil"},
        {"name": "Savner", "type": "tehsil"}, {"name": "Mauda", "type": "tehsil"}],
     "villages": ["Khapri", "Bori", "Butibori", "Katol"]},
    {"state_code": "IN-MH", "district_code": "IN-MH-NASHIK",
     "subdistricts": [
        {"name": "Nashik", "type": "tehsil"}, {"name": "Igatpuri", "type": "tehsil"},
        {"name": "Sinnar", "type": "tehsil"}, {"name": "Niphad", "type": "tehsil"},
        {"name": "Yeola", "type": "tehsil"}, {"name": "Nandgaon", "type": "tehsil"},
        {"name": "Malegaon", "type": "tehsil"}, {"name": "Kalwan", "type": "tehsil"},
        {"name": "Baglan", "type": "tehsil"}, {"name": "Dindori", "type": "tehsil"}],
     "villages": ["Lasalgaon", "Pimpalgaon Baswant", "Ozar", "Saykheda"]},
    {"state_code": "IN-PB", "district_code": "IN-PB-LUDHIANA",
     "subdistricts": [
        {"name": "Ludhiana East", "type": "tehsil"}, {"name": "Ludhiana West", "type": "tehsil"},
        {"name": "Jagraon", "type": "tehsil"}, {"name": "Khanna", "type": "tehsil"},
        {"name": "Raikot", "type": "tehsil"}, {"name": "Samrala", "type": "tehsil"},
        {"name": "Payal", "type": "tehsil"}, {"name": "Machhiwara", "type": "tehsil"},
        {"name": "Dehlon", "type": "tehsil"}, {"name": "Sidhwan Bet", "type": "tehsil"}],
     "villages": ["Jagraon", "Khanna", "Raikot", "Machhiwara"]},
    {"state_code": "IN-TN", "district_code": "IN-TN-THANJAVUR",
     "subdistricts": [
        {"name": "Thanjavur", "type": "taluk"}, {"name": "Kumbakonam", "type": "taluk"},
        {"name": "Papanasam", "type": "taluk"}, {"name": "Pattukkottai", "type": "taluk"},
        {"name": "Peravurani", "type": "taluk"}, {"name": "Orathanadu", "type": "taluk"},
        {"name": "Thiruvidaimarudur", "type": "taluk"}, {"name": "Thiruvaiyaru", "type": "taluk"},
        {"name": "Budalur", "type": "taluk"}],
     "villages": ["Papanasam", "Thiruvaiyaru", "Pattukkottai", "Orathanadu"]},
]
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

# ═════════════════════════════════════════════════════════════════════════════
# Phase 2 (V1.5) — structured agronomy / reasoning substrate
# ═════════════════════════════════════════════════════════════════════════════

# Fertilizer → nutrient composition (numeric, oxide form explicit).
# This unlocks the nutrient math required by the fertilizer-advisory engine:
#   crop + variety + stage + soil test + target yield → nutrient requirement
#   → fertilizer recommendation.
FERTILIZER_NUTRIENTS = [
    {"fertilizer_id": "FERT_UREA", "nutrient_id": "NUT_N", "form": "N", "percent": 46.0},
    {"fertilizer_id": "FERT_DAP", "nutrient_id": "NUT_N", "form": "N", "percent": 18.0},
    {"fertilizer_id": "FERT_DAP", "nutrient_id": "NUT_P", "form": "P2O5", "percent": 46.0},
    {"fertilizer_id": "FERT_MOP", "nutrient_id": "NUT_K", "form": "K2O", "percent": 60.0},
    {"fertilizer_id": "FERT_SSP", "nutrient_id": "NUT_P", "form": "P2O5", "percent": 16.0},
    {"fertilizer_id": "FERT_SSP", "nutrient_id": "NUT_S", "form": "S", "percent": 11.0},
    {"fertilizer_id": "FERT_SSP", "nutrient_id": "NUT_CA", "form": "Ca", "percent": 20.0},
    {"fertilizer_id": "FERT_AS", "nutrient_id": "NUT_N", "form": "N", "percent": 21.0},
    {"fertilizer_id": "FERT_AS", "nutrient_id": "NUT_S", "form": "S", "percent": 24.0},
    {"fertilizer_id": "FERT_NPK_102626", "nutrient_id": "NUT_N", "form": "N", "percent": 10.0},
    {"fertilizer_id": "FERT_NPK_102626", "nutrient_id": "NUT_P", "form": "P2O5", "percent": 26.0},
    {"fertilizer_id": "FERT_NPK_102626", "nutrient_id": "NUT_K", "form": "K2O", "percent": 26.0},
    {"fertilizer_id": "FERT_NPK_123216", "nutrient_id": "NUT_N", "form": "N", "percent": 12.0},
    {"fertilizer_id": "FERT_NPK_123216", "nutrient_id": "NUT_P", "form": "P2O5", "percent": 32.0},
    {"fertilizer_id": "FERT_NPK_123216", "nutrient_id": "NUT_K", "form": "K2O", "percent": 16.0},
    {"fertilizer_id": "FERT_NPK_171717", "nutrient_id": "NUT_N", "form": "N", "percent": 17.0},
    {"fertilizer_id": "FERT_NPK_171717", "nutrient_id": "NUT_P", "form": "P2O5", "percent": 17.0},
    {"fertilizer_id": "FERT_NPK_171717", "nutrient_id": "NUT_K", "form": "K2O", "percent": 17.0},
    {"fertilizer_id": "FERT_NPK_202000", "nutrient_id": "NUT_N", "form": "N", "percent": 20.0},
    {"fertilizer_id": "FERT_NPK_202000", "nutrient_id": "NUT_P", "form": "P2O5", "percent": 20.0},
    {"fertilizer_id": "FERT_ZNSO4", "nutrient_id": "NUT_ZN", "form": "Zn", "percent": 21.0},
    {"fertilizer_id": "FERT_ZNSO4", "nutrient_id": "NUT_S", "form": "S", "percent": 10.0},
    {"fertilizer_id": "FERT_BORAX", "nutrient_id": "NUT_B", "form": "B", "percent": 10.5},
    {"fertilizer_id": "FERT_FESO4", "nutrient_id": "NUT_FE", "form": "Fe", "percent": 19.0},
    {"fertilizer_id": "FERT_FESO4", "nutrient_id": "NUT_S", "form": "S", "percent": 11.0},
    {"fertilizer_id": "FERT_CAN", "nutrient_id": "NUT_N", "form": "N", "percent": 25.0},
    {"fertilizer_id": "FERT_CAN", "nutrient_id": "NUT_CA", "form": "Ca", "percent": 8.0},
    {"fertilizer_id": "FERT_GYPSUM", "nutrient_id": "NUT_CA", "form": "Ca", "percent": 23.0},
    {"fertilizer_id": "FERT_GYPSUM", "nutrient_id": "NUT_S", "form": "S", "percent": 18.0},
]

# Nutrient deficiency disorders (nutrient × crop × symptoms × correction).
NUTRIENT_DEFICIENCIES = [
    {"deficiency_id": "DEF_ZN_RICE", "nutrient_id": "NUT_ZN", "crop_id": "CROP_RICE", "crop": "Rice",
     "symptoms": "Khaira disease: dusty brown spots on leaves, white bud, stunted growth, uneven crop",
     "correction": "ZnSO4 25 kg/ha in soil or 0.5% foliar spray (5 g/L + lime); root-dip of seedlings in 1% ZnO"},
    {"deficiency_id": "DEF_N_MAIZE", "nutrient_id": "NUT_N", "crop_id": "CROP_MAIZE", "crop": "Maize",
     "symptoms": "V-shaped yellowing from leaf tip along midrib, stunted plants, pale green older leaves",
     "correction": "Top-dress urea in splits (knee-high and tasseling stages); ~120 kg N/ha"},
    {"deficiency_id": "DEF_N_WHEAT", "nutrient_id": "NUT_N", "crop_id": "CROP_WHEAT", "crop": "Wheat",
     "symptoms": "Pale yellow older leaves, reduced tillering, stunted growth",
     "correction": "Split urea application at crown-root initiation and jointing"},
    {"deficiency_id": "DEF_FE_SUGARCANE", "nutrient_id": "NUT_FE", "crop_id": "CROP_SUGARCANE", "crop": "Sugarcane",
     "symptoms": "Interveinal chlorosis of young leaves (calcareous soils), white stripes",
     "correction": "FeSO4 0.5% foliar spray + soil application; avoid waterlogging"},
    {"deficiency_id": "DEF_FE_GROUNDNUT", "nutrient_id": "NUT_FE", "crop_id": "CROP_GROUNDNUT", "crop": "Groundnut",
     "symptoms": "Interveinal chlorosis of younger leaves (calcareous/alkaline soils)",
     "correction": "FeSO4 0.5-1.0% foliar spray + organic matter; avoid excess irrigation"},
    {"deficiency_id": "DEF_B_TOMATO", "nutrient_id": "NUT_B", "crop_id": "CROP_TOMATO", "crop": "Tomato",
     "symptoms": "Distorted growth, hollow fruit, fruit cracking, reduced fruit set",
     "correction": "Borax 0.2-0.25% foliar spray at flowering/fruit set; soil application 10 kg/ha on deficient soils"},
    {"deficiency_id": "DEF_B_CAULIFLOWER", "nutrient_id": "NUT_B", "crop_id": "CROP_CAULIFLOWER", "crop": "Cauliflower",
     "symptoms": "Brown hollow stem, water-soaked curd, whiptail-like leaf distortion",
     "correction": "Borax 0.2% foliar spray before curd initiation"},
    {"deficiency_id": "DEF_MO_CAULIFLOWER", "nutrient_id": "NUT_MO", "crop_id": "CROP_CAULIFLOWER", "crop": "Cauliflower",
     "symptoms": "Whiptail: narrow strap-like leaves, no curd formation",
     "correction": "Sodium molybdate 0.01-0.02% foliar or ammonium molybdate soil application; liming acid soils"},
    {"deficiency_id": "DEF_CA_TOMATO", "nutrient_id": "NUT_CA", "crop_id": "CROP_TOMATO", "crop": "Tomato",
     "symptoms": "Blossom-end rot: dark water-soaked spot at fruit blossom end",
     "correction": "Calcium nitrate 0.5% foliar spray at fruit set; uniform irrigation; avoid excess N/K"},
    {"deficiency_id": "DEF_K_POTATO", "nutrient_id": "NUT_K", "crop_id": "CROP_POTATO", "crop": "Potato",
     "symptoms": "Scorched leaf margins, bronzing, weak stems, small tubers",
     "correction": "MOP 80-100 kg/ha at planting (split); avoid chloride-sensitive varieties"},
    {"deficiency_id": "DEF_MG_COTTON", "nutrient_id": "NUT_MG", "crop_id": "CROP_COTTON", "crop": "Cotton",
     "symptoms": "Purplish-red interveinal chlorosis of older leaves (leaf reddening)",
     "correction": "MgSO4 0.5% foliar spray; dolomite on acid soils"},
    {"deficiency_id": "DEF_S_OILSEED", "nutrient_id": "NUT_S", "crop_id": "CROP_MUSTARD", "crop": "Mustard",
     "symptoms": "Uniform yellowing of young leaves, reduced oil content, cupped leaves",
     "correction": "Ammonium sulphate or SSP (sulphur-bearing) at sowing; gypsum 50 kg/ha"},
    {"deficiency_id": "DEF_P_PULSES", "nutrient_id": "NUT_P", "crop_id": "CROP_CHICKPEA", "crop": "Chickpea",
     "symptoms": "Dull green/purple leaves, poor root nodules, delayed maturity",
     "correction": "DAP or SSP basal + phospho-bacteria (PSB) seed treatment"},
]

# Deeper clinical fields for high-priority diseases (merged into dim_disease).
DISEASE_CLINICAL = {
    "DIS_TOMATO_EB": {"growth_stage": "vegetative|fruiting",
                      "differential_diagnosis": "Late blight (water-soaked greasy lesions, cool humid) vs Septoria (small spots with dark margin and pycnidia) vs Bacterial speck (pinhead spots, no rings)"},
    "DIS_TOMATO_LB": {"growth_stage": "vegetative|flowering|fruiting",
                      "differential_diagnosis": "Early blight (concentric rings, warm) vs Grey mould (fluffy grey growth) vs Bacterial spot"},
    "DIS_TOMATO_BW": {"growth_stage": "vegetative|fruiting",
                      "differential_diagnosis": "Fusarium wilt (one-sided yellowing, cooler) vs Verticillium wilt vs Root-knot nematode damage"},
    "DIS_TOMATO_LCV": {"growth_stage": "seedling|vegetative",
                       "differential_diagnosis": "Herbicide damage (no whitefly, not contagious) vs Water stress vs Nutrient deficiency"},
    "DIS_RICE_BLAST": {"growth_stage": "vegetative|flowering",
                       "differential_diagnosis": "Brown spot (no spindle shape, nutrient stress) vs Bacterial leaf blight (water-soaked, no grey centre)"},
    "DIS_RICE_BLB": {"growth_stage": "vegetative|flowering",
                     "differential_diagnosis": "Bacterial leaf streak (narrow streaks, no ooze droplets) vs Rice blast"},
    "DIS_RICE_SHEATH_BLIGHT": {"growth_stage": "vegetative|flowering",
                               "differential_diagnosis": "Sheath rot (panicle, dark) vs Stem rot (sclerotia at base)"},
    "DIS_WHEAT_RUST": {"growth_stage": "vegetative|flowering|grain_fill",
                       "differential_diagnosis": "Leaf rust (scattered orange pustules) vs Stem rust (elongated on stem) vs Stripe rust (yellow stripes along veins)"},
    "DIS_WHEAT_PM": {"growth_stage": "vegetative|flowering",
                     "differential_diagnosis": "Downy mildew (yellow patches, cool wet) vs Rusts"},
    "DIS_MAIZE_DM": {"growth_stage": "seedling|vegetative",
                     "differential_diagnosis": "Crazy top (distorted tassel) vs Nutrient deficiency"},
    "DIS_CHILLI_ANTHRACNOSE": {"growth_stage": "fruiting|maturity",
                               "differential_diagnosis": "Sunscald (no pathogen, white papery) vs Bacterial soft rot"},
    "DIS_CHILLI_LCV": {"growth_stage": "seedling|vegetative",
                       "differential_diagnosis": "Thrips damage (silvery streaks) vs Herbicide injury vs Nutrient deficiency"},
    "DIS_POTATO_LB": {"growth_stage": "vegetative|tuber_bulking",
                      "differential_diagnosis": "Early blight (concentric rings) vs Black scurf"},
    "DIS_ONION_PB": {"growth_stage": "vegetative",
                     "differential_diagnosis": "Downy mildew (grey-violet growth) vs Stemphylium blight (yellow spots, no purple)"},
    "DIS_COTTON_LCV": {"growth_stage": "seedling|vegetative",
                       "differential_diagnosis": "Nutritional disorder vs Whitefly injury vs Herbicide drift"},
    "DIS_COTTON_WILT": {"growth_stage": "vegetative|flowering",
                        "differential_diagnosis": "Verticillium wilt (V-shaped lesions) vs Root rot"},
    "DIS_SUGARCANE_RR": {"growth_stage": "vegetative|maturity",
                         "differential_diagnosis": "Smut (whip) vs Mosaic (viral, chlorotic patterns)"},
    "DIS_SUGARCANE_SMUT": {"growth_stage": "vegetative|flowering",
                           "differential_diagnosis": "Grassy shoot (phytoplasma, grassy tillers) vs Red rot"},
    "DIS_GROUNDNUT_TIKKA": {"growth_stage": "vegetative|fruiting",
                            "differential_diagnosis": "Rust (orange pustules on underside) vs Leaf miner damage"},
    "DIS_GRAPE_DM": {"growth_stage": "vegetative|fruiting",
                     "differential_diagnosis": "Powdery mildew (white powder on upper surface, dry) vs Anthracnose"},
    "DIS_BANANA_PW": {"growth_stage": "vegetative|fruiting",
                      "differential_diagnosis": "Waterlogging/root rot vs Moko (bacterial, fruit rot) vs Nematode damage"},
    "DIS_MANGO_ANTH": {"growth_stage": "flowering|fruiting",
                       "differential_diagnosis": "Bacterial black spot (angular, raised) vs Powdery mildew"},
    "DIS_MANGO_PM": {"growth_stage": "flowering",
                     "differential_diagnosis": "Anthracnose (dark lesions, humid) vs Malformation (vegetative/floral distortion)"},
    "DIS_BRINJAL_LL": {"growth_stage": "vegetative",
                       "differential_diagnosis": "Viral mosaic (mottling) vs Nutrient deficiency"},
    "DIS_OKRA_YVMV": {"growth_stage": "vegetative",
                      "differential_diagnosis": "Leaf curl (thrips/whitefly) vs Iron chlorosis (no yellow veins)"},
}

# IPM depth for high-priority pests (ETL = economic threshold level; monitoring).
PEST_IPM = {
    "PEST_RICE_STEMBORER": {"growth_stage": "vegetative|flowering", "economic_threshold": "1 moth/trap/night or 5% dead hearts", "monitoring": "Pheromone traps @ 8/ha"},
    "PEST_RICE_BPH": {"growth_stage": "vegetative|flowering", "economic_threshold": "5-10 hoppers/hill", "monitoring": "Visual counting, avoid resurgence"},
    "PEST_MAIZE_FAW": {"growth_stage": "seedling|vegetative", "economic_threshold": "10% plants infested (whorl)", "monitoring": "Pheromone traps, whorl scouting"},
    "PEST_COTTON_PBW": {"growth_stage": "flowering|fruiting", "economic_threshold": "8 moths/trap/3 days", "monitoring": "PBKnot pheromone traps @ 5/ha"},
    "PEST_COTTON_ABW": {"growth_stage": "flowering|fruiting", "economic_threshold": "1 larva/plant or 5% damaged fruiting bodies", "monitoring": "Pheromone traps, egg scouting"},
    "PEST_WHITEFLY": {"growth_stage": "vegetative|flowering", "economic_threshold": "10 adults/leaf", "monitoring": "Yellow sticky traps @ 10/ha"},
    "PEST_APHID": {"growth_stage": "vegetative|flowering", "economic_threshold": "10-15% infested plants", "monitoring": "Visual + natural enemy presence"},
    "PEST_THRIPS": {"growth_stage": "vegetative|flowering", "economic_threshold": "10 thrips/leaf or silvery patches on 10% leaves", "monitoring": "Blue sticky traps"},
    "PEST_BRINJAL_FB": {"growth_stage": "vegetative|fruiting", "economic_threshold": "5% damaged shoots/fruits", "monitoring": "Pheromone traps"},
    "PEST_DBM": {"growth_stage": "vegetative|curd", "economic_threshold": "10% leaf damage or 10 larvae/plant", "monitoring": "Pheromone traps"},
    "PEST_MITE": {"growth_stage": "vegetative|fruiting", "economic_threshold": "5-10 mites/leaf with webbing", "monitoring": "Leaf undersurface loupe"},
    "PEST_MEALYBUG": {"growth_stage": "vegetative|fruiting", "economic_threshold": "1-2 colonies/plant", "monitoring": "Visual, ant association"},
    "PEST_TERMITE": {"growth_stage": "all", "economic_threshold": "Presence in seedbed/setts", "monitoring": "Soil inspection"},
    "PEST_GRAM_PB": {"growth_stage": "flowering|fruiting", "economic_threshold": "1 larva/m row or 5% pod damage", "monitoring": "Pheromone traps @ 4/ha"},
    "PEST_MANGO_HOPPER": {"growth_stage": "flowering", "economic_threshold": "5-10 hoppers/panicle", "monitoring": "Sweep net on inflorescence"},
    "PEST_JASSID": {"growth_stage": "seedling|vegetative", "economic_threshold": "2 jassids/leaf or marginal yellowing on 10% plants", "monitoring": "Visual undersurface"},
}

# Crop calendar for top-20 crops (national default), extending the 5-crop exemplar above.
CROP_CALENDAR_TOP20 = [
    {"crop_id": "CROP_RICE", "season_id": "SEASON_RABI", "stage_id": "STAGE_SOWING", "month_start": 11, "month_end": 12, "note": "boro/rabi rice nursery"},
    {"crop_id": "CROP_RICE", "season_id": "SEASON_RABI", "stage_id": "STAGE_HARVEST", "month_start": 4, "month_end": 5, "note": None},
    {"crop_id": "CROP_MAIZE", "season_id": "SEASON_KHARIF", "stage_id": "STAGE_SOWING", "month_start": 6, "month_end": 7, "note": "with monsoon onset"},
    {"crop_id": "CROP_MAIZE", "season_id": "SEASON_KHARIF", "stage_id": "STAGE_FLOWERING", "month_start": 8, "month_end": 9, "note": "tasseling/silking"},
    {"crop_id": "CROP_MAIZE", "season_id": "SEASON_KHARIF", "stage_id": "STAGE_HARVEST", "month_start": 10, "month_end": 11, "note": None},
    {"crop_id": "CROP_JOWAR", "season_id": "SEASON_KHARIF", "stage_id": "STAGE_SOWING", "month_start": 6, "month_end": 7, "note": None},
    {"crop_id": "CROP_JOWAR", "season_id": "SEASON_KHARIF", "stage_id": "STAGE_HARVEST", "month_start": 10, "month_end": 11, "note": None},
    {"crop_id": "CROP_BAJRA", "season_id": "SEASON_KHARIF", "stage_id": "STAGE_SOWING", "month_start": 7, "month_end": 8, "note": None},
    {"crop_id": "CROP_BAJRA", "season_id": "SEASON_KHARIF", "stage_id": "STAGE_HARVEST", "month_start": 10, "month_end": 11, "note": None},
    {"crop_id": "CROP_CHICKPEA", "season_id": "SEASON_RABI", "stage_id": "STAGE_SOWING", "month_start": 10, "month_end": 11, "note": None},
    {"crop_id": "CROP_CHICKPEA", "season_id": "SEASON_RABI", "stage_id": "STAGE_FLOWERING", "month_start": 1, "month_end": 2, "note": None},
    {"crop_id": "CROP_CHICKPEA", "season_id": "SEASON_RABI", "stage_id": "STAGE_HARVEST", "month_start": 3, "month_end": 4, "note": None},
    {"crop_id": "CROP_PIGEONPEA", "season_id": "SEASON_KHARIF", "stage_id": "STAGE_SOWING", "month_start": 6, "month_end": 7, "note": "long duration"},
    {"crop_id": "CROP_PIGEONPEA", "season_id": "SEASON_KHARIF", "stage_id": "STAGE_HARVEST", "month_start": 1, "month_end": 3, "note": None},
    {"crop_id": "CROP_SOYBEAN", "season_id": "SEASON_KHARIF", "stage_id": "STAGE_SOWING", "month_start": 6, "month_end": 7, "note": None},
    {"crop_id": "CROP_SOYBEAN", "season_id": "SEASON_KHARIF", "stage_id": "STAGE_FLOWERING", "month_start": 8, "month_end": 9, "note": None},
    {"crop_id": "CROP_SOYBEAN", "season_id": "SEASON_KHARIF", "stage_id": "STAGE_HARVEST", "month_start": 10, "month_end": 11, "note": None},
    {"crop_id": "CROP_GROUNDNUT", "season_id": "SEASON_KHARIF", "stage_id": "STAGE_SOWING", "month_start": 6, "month_end": 7, "note": None},
    {"crop_id": "CROP_GROUNDNUT", "season_id": "SEASON_KHARIF", "stage_id": "STAGE_HARVEST", "month_start": 10, "month_end": 11, "note": None},
    {"crop_id": "CROP_MUSTARD", "season_id": "SEASON_RABI", "stage_id": "STAGE_SOWING", "month_start": 10, "month_end": 11, "note": None},
    {"crop_id": "CROP_MUSTARD", "season_id": "SEASON_RABI", "stage_id": "STAGE_FLOWERING", "month_start": 1, "month_end": 2, "note": None},
    {"crop_id": "CROP_MUSTARD", "season_id": "SEASON_RABI", "stage_id": "STAGE_HARVEST", "month_start": 3, "month_end": 4, "note": None},
    {"crop_id": "CROP_ONION", "season_id": "SEASON_RABI", "stage_id": "STAGE_NURSERY", "month_start": 8, "month_end": 9, "note": None},
    {"crop_id": "CROP_ONION", "season_id": "SEASON_RABI", "stage_id": "STAGE_TRANSPLANTING", "month_start": 10, "month_end": 11, "note": None},
    {"crop_id": "CROP_ONION", "season_id": "SEASON_RABI", "stage_id": "STAGE_HARVEST", "month_start": 3, "month_end": 5, "note": None},
    {"crop_id": "CROP_POTATO", "season_id": "SEASON_RABI", "stage_id": "STAGE_SOWING", "month_start": 10, "month_end": 11, "note": "tuber planting"},
    {"crop_id": "CROP_POTATO", "season_id": "SEASON_RABI", "stage_id": "STAGE_HARVEST", "month_start": 2, "month_end": 3, "note": None},
    {"crop_id": "CROP_CHILLI", "season_id": "SEASON_KHARIF", "stage_id": "STAGE_NURSERY", "month_start": 6, "month_end": 7, "note": None},
    {"crop_id": "CROP_CHILLI", "season_id": "SEASON_KHARIF", "stage_id": "STAGE_TRANSPLANTING", "month_start": 7, "month_end": 8, "note": None},
    {"crop_id": "CROP_CHILLI", "season_id": "SEASON_KHARIF", "stage_id": "STAGE_HARVEST", "month_start": 11, "month_end": 1, "note": "picking in flushes"},
    {"crop_id": "CROP_BRINJAL", "season_id": "SEASON_KHARIF", "stage_id": "STAGE_SOWING", "month_start": 6, "month_end": 7, "note": None},
    {"crop_id": "CROP_BRINJAL", "season_id": "SEASON_KHARIF", "stage_id": "STAGE_HARVEST", "month_start": 10, "month_end": 12, "note": None},
    {"crop_id": "CROP_OKRA", "season_id": "SEASON_SUMMER", "stage_id": "STAGE_SOWING", "month_start": 2, "month_end": 3, "note": "summer crop"},
    {"crop_id": "CROP_OKRA", "season_id": "SEASON_SUMMER", "stage_id": "STAGE_HARVEST", "month_start": 4, "month_end": 6, "note": None},
    {"crop_id": "CROP_BANANA", "season_id": "SEASON_WHOLE_YEAR", "stage_id": "STAGE_SOWING", "month_start": 2, "month_end": 3, "note": "spring planting"},
    {"crop_id": "CROP_BANANA", "season_id": "SEASON_WHOLE_YEAR", "stage_id": "STAGE_HARVEST", "month_start": 12, "month_end": 4, "note": "12-15 months after planting"},
    {"crop_id": "CROP_MANGO", "season_id": "SEASON_WHOLE_YEAR", "stage_id": "STAGE_FLOWERING", "month_start": 12, "month_end": 2, "note": "blossoming"},
    {"crop_id": "CROP_MANGO", "season_id": "SEASON_WHOLE_YEAR", "stage_id": "STAGE_HARVEST", "month_start": 4, "month_end": 7, "note": "fruit maturity"},
    {"crop_id": "CROP_GRAPES", "season_id": "SEASON_WHOLE_YEAR", "stage_id": "STAGE_HARVEST", "month_start": 1, "month_end": 4, "note": "main pruning/harvest cycle"},
]

# Location overrides on the calendar (the India → State → District → Crop model).
# location_scope ∈ {state, district}; state_code/district_code identify the override.
CROP_CALENDAR_OVERRIDES = [
    {"crop_id": "CROP_TOMATO", "season_id": "SEASON_RABI", "stage_id": "STAGE_NURSERY",
     "location_scope": "district", "state_code": "IN-MH", "district_code": "IN-MH-PUNE",
     "month_start": 9, "month_end": 10, "note": "Pune rabi tomato nursery"},
    {"crop_id": "CROP_RICE", "season_id": "SEASON_KHARIF", "stage_id": "STAGE_TRANSPLANTING",
     "location_scope": "district", "state_code": "IN-TN", "district_code": "IN-TN-THANJAVUR",
     "month_start": 8, "month_end": 9, "note": "samba transplant (Cauvery delta)"},
    {"crop_id": "CROP_WHEAT", "season_id": "SEASON_RABI", "stage_id": "STAGE_SOWING",
     "location_scope": "state", "state_code": "IN-PB", "district_code": None,
     "month_start": 10, "month_end": 11, "note": "early sowing to escape terminal heat"},
]




# ═════════════════════════════════════════════════════════════════════════════
# Multilingual symptom lexicon (Devanagari → canonical English symptom tokens).
#
# Lets the diagnosis retriever match Hindi/Marathi symptom text directly.
# Telugu/Tamil/Kannada/… lexicons land with the per-script transliterators.
# ═════════════════════════════════════════════════════════════════════════════
SYMPTOM_LEXICON = {
    "hi": {
        "काला": "black", "काली": "black", "काले": "black",
        "धब्बे": "spots", "दाग": "spots", "चित्तियाँ": "spots", "चित्ती": "spots",
        "पत्ता": "leaf", "पत्ते": "leaves", "पत्तियाँ": "leaves", "पत्तियों": "leaves", "पत्ती": "leaf",
        "पीला": "yellowing", "पीले": "yellowing", "पीली": "yellowing", "पीलापन": "yellowing",
        "सफेद": "white", "सफ़ेद": "white", "श्वेत": "white",
        "मुरझा": "wilting", "मुरझाना": "wilting", "मुरझाई": "wilting", "मुरझाया": "wilting",
        "मुड़ना": "curling", "मुड़": "curling", "मरोड़": "curling", "कुंडलित": "curling",
        "बौना": "stunted", "ठिगना": "stunted", "छोटा": "stunted",
        "भूरा": "brown", "भूरे": "brown",
        "कली": "bud", "कलियाँ": "bud", "कोंपल": "bud", "कोंपलें": "bud",
        "फल": "fruit", "फलों": "fruit",
        "फूल": "flower", "फूलों": "flower",
        "जड़": "root", "जड़ें": "root",
        "तना": "stem", "डंठल": "stem",
        "वृद्धि": "growth", "बढ़वार": "growth",
        "भभूतिया": "powdery", "चूर्ण": "powdery", "पाउडर": "powdery",
        "रतुआ": "rust", "किट्ट": "rust",
        "लाल": "red",
        "गीला": "soaked", "भीगा": "soaked",
        "फफूंदी": "mildew", "बुरशी": "mildew",
        "सड़न": "rot", "गलन": "rot", "सड़": "rot", "गल": "rot",
        "छेद": "hole", "छिद्र": "hole",
        "जाला": "webbing", "जाले": "webbing",
        "चिपचिपा": "honeydew", "मधुरस": "honeydew",
        "रोग": "disease", "बीमारी": "disease",
        "कीड़ा": "pest", "कीट": "pest", "कीड़े": "pest", "इल्ली": "larva", "लट": "larva",
        "सूख": "drying", "सूखना": "drying", "सूखा": "drying",
        "गिर": "falling", "गिरना": "falling", "झड़": "falling", "झड़ना": "falling",
    },
    "mr": {
        "काळा": "black", "काळी": "black", "काळे": "black",
        "डाग": "spots", "ठिपके": "spots", "ठिपका": "spots",
        "पान": "leaf", "पाने": "leaves", "पानांवर": "leaves", "पानावर": "leaf", "पर्ण": "leaf",
        "पिवळा": "yellowing", "पिवळी": "yellowing", "पिवळे": "yellowing", "पिवळसर": "yellowing",
        "पांढरा": "white", "पांढरे": "white", "पांढरी": "white", "सफेद": "white",
        "वाळणे": "wilting", "वाळलेली": "wilting", "वाळलेले": "wilting", "कोमेजणे": "wilting", "कोमेजलेली": "wilting",
        "मुरडणे": "curling", "मुरगळलेली": "curling", "मुरगळलेले": "curling", "कुरळे": "curling",
        "खुजे": "stunted", "खुरटलेली": "stunted", "खुरटलेले": "stunted", "थेंबट": "stunted",
        "तपकिरी": "brown",
        "कळी": "bud", "कळ्या": "bud", "कोंब": "bud", "कोंबावर": "bud",
        "फळ": "fruit", "फळे": "fruit", "फळांवर": "fruit",
        "फूल": "flower", "फुले": "flower", "फुलांवर": "flower",
        "मूळ": "root", "मुळे": "root", "मुळांवर": "root",
        "खोड": "stem", "देठ": "stem",
        "भुरी": "powdery", "पावडर": "powdery", "पिठासारखे": "powdery",
        "गंज": "rust", "तांबेरा": "rust",
        "लाल": "red",
        "ओले": "soaked", "भिजलेले": "soaked",
        "बुरशी": "mildew", "फफूंदी": "mildew",
        "कुजणे": "rot", "कुजलेली": "rot", "कुजलेले": "rot", "सडणे": "rot", "सडलेली": "rot", "कुजवा": "rot",
        "भोक": "hole", "छिद्र": "hole",
        "जाळे": "webbing", "जाळी": "webbing",
        "चिकट": "honeydew",
        "रोग": "disease",
        "किडा": "pest", "कीड": "pest", "किडे": "pest", "अळी": "larva",
        "वाळ": "drying", "वाळून": "drying",
        "गळणे": "falling", "गळ": "falling", "गळून": "falling",
    },
}


# ═════════════════════════════════════════════════════════════════════════════
# Fertilizer-advisory substrate (Track 5).
#
# CROP_NUTRIENT_REQUIREMENT — representative ICAR/SAU "blanket" seasonal
# recommendations (kg/ha of N, P2O5, K2O) for a target yield, split across the
# three application timings the advisory engine reasons over:
#   basal (sowing/transplanting/establishment)
#   vegetative
#   reproductive (flowering → fruit/grain fill → maturity)
# Fractions per nutrient must sum to ~1.0.
#
# SOIL_TEST_INTERPRETATION — thresholds used to re-classify a farmer's soil
# test into low / optimal / high (or acidic / saline / deficient) and adjust the
# recommendation accordingly. Representative ranges; refine with STCR/lab data.
# ═════════════════════════════════════════════════════════════════════════════
FERTILIZER_ADVISORY_VERSION = "2026.08"


def _split(n_basal: float, n_veg: float, n_rep: float,
           p_basal: float = 1.0, k_basal: float = 0.5, k_rep: float = 0.5) -> dict:
    """Build a {timing: {N/P2O5/K2O fraction}} schedule from the N split + defaults."""
    return {
        "basal": {"N": n_basal, "P2O5": p_basal, "K2O": k_basal},
        "vegetative": {"N": n_veg, "P2O5": 0.0, "K2O": 0.0},
        "reproductive": {"N": n_rep, "P2O5": 0.0, "K2O": k_rep},
    }


CROP_NUTRIENT_REQUIREMENT = [
    {"crop_id": "CROP_RICE", "crop": "Rice", "target_yield_tha": 5.0,
     "total_kg_ha": {"N": 120, "P2O5": 60, "K2O": 40},
     "stage_split": _split(0.33, 0.34, 0.33, p_basal=1.0, k_basal=0.5, k_rep=0.5)},
    {"crop_id": "CROP_WHEAT", "crop": "Wheat", "target_yield_tha": 4.5,
     "total_kg_ha": {"N": 120, "P2O5": 60, "K2O": 40},
     "stage_split": _split(0.5, 0.25, 0.25)},
    {"crop_id": "CROP_MAIZE", "crop": "Maize", "target_yield_tha": 5.5,
     "total_kg_ha": {"N": 120, "P2O5": 60, "K2O": 40},
     "stage_split": _split(0.25, 0.5, 0.25)},
    {"crop_id": "CROP_SUGARCANE", "crop": "Sugarcane", "target_yield_tha": 100.0,
     "total_kg_ha": {"N": 250, "P2O5": 75, "K2O": 125},
     "stage_split": _split(0.1, 0.4, 0.5, k_basal=0.25, k_rep=0.75)},
    {"crop_id": "CROP_COTTON", "crop": "Cotton", "target_yield_tha": 2.0,
     "total_kg_ha": {"N": 80, "P2O5": 40, "K2O": 40},
     "stage_split": _split(0.2, 0.4, 0.4)},
    {"crop_id": "CROP_TOMATO", "crop": "Tomato", "target_yield_tha": 40.0,
     "total_kg_ha": {"N": 150, "P2O5": 100, "K2O": 150},
     "stage_split": _split(0.2, 0.4, 0.4, k_basal=0.33, k_rep=0.67)},
    {"crop_id": "CROP_ONION", "crop": "Onion", "target_yield_tha": 25.0,
     "total_kg_ha": {"N": 100, "P2O5": 50, "K2O": 50},
     "stage_split": _split(0.5, 0.25, 0.25)},
    {"crop_id": "CROP_POTATO", "crop": "Potato", "target_yield_tha": 25.0,
     "total_kg_ha": {"N": 120, "P2O5": 80, "K2O": 100},
     "stage_split": _split(0.5, 0.25, 0.25)},
    {"crop_id": "CROP_CHILLI", "crop": "Chilli", "target_yield_tha": 15.0,
     "total_kg_ha": {"N": 100, "P2O5": 50, "K2O": 80},
     "stage_split": _split(0.25, 0.25, 0.5, k_basal=0.25, k_rep=0.75)},
    {"crop_id": "CROP_BRINJAL", "crop": "Brinjal", "target_yield_tha": 30.0,
     "total_kg_ha": {"N": 100, "P2O5": 50, "K2O": 50},
     "stage_split": _split(0.25, 0.25, 0.5, k_basal=0.25, k_rep=0.75)},
    {"crop_id": "CROP_GROUNDNUT", "crop": "Groundnut", "target_yield_tha": 2.0,
     "total_kg_ha": {"N": 25, "P2O5": 50, "K2O": 50},
     "stage_split": _split(0.5, 0.0, 0.5, p_basal=1.0)},
    {"crop_id": "CROP_SOYBEAN", "crop": "Soybean", "target_yield_tha": 2.0,
     "total_kg_ha": {"N": 30, "P2O5": 60, "K2O": 40},
     "stage_split": _split(0.5, 0.0, 0.5)},
    {"crop_id": "CROP_BANANA", "crop": "Banana", "target_yield_tha": 60.0,
     "total_kg_ha": {"N": 200, "P2O5": 60, "K2O": 400},
     "stage_split": _split(0.1, 0.45, 0.45, k_basal=0.1, k_rep=0.9)},
    {"crop_id": "CROP_MANGO", "crop": "Mango", "target_yield_tha": 10.0,
     "total_kg_ha": {"N": 100, "P2O5": 50, "K2O": 100},
     "stage_split": _split(0.4, 0.3, 0.3, k_basal=0.5, k_rep=0.5)},
    {"crop_id": "CROP_CABBAGE", "crop": "Cabbage", "target_yield_tha": 30.0,
     "total_kg_ha": {"N": 150, "P2O5": 80, "K2O": 80},
     "stage_split": _split(0.33, 0.34, 0.33)},
]


SOIL_TEST_INTERPRETATION = [
    # NPK (kg/ha) + OC (%): low / optimal / high classification.
    {"parameter": "available_n", "label": "Available N (KMnO4)", "unit": "kg/ha",
     "kind": "nutrient", "nutrient_form": "N", "low_max": 280.0, "high_min": 560.0,
     "adjustment": 0.25, "low_note": "Increase N by {pct:.0%}; consider split application.",
     "high_note": "Reduce N by {pct:.0%} to avoid lodging/pest build-up."},
    {"parameter": "available_p", "label": "Available P (Olsen)", "unit": "kg/ha",
     "kind": "nutrient", "nutrient_form": "P2O5", "low_max": 10.0, "high_min": 25.0,
     "adjustment": 0.25, "low_note": "Increase P2O5 by {pct:.0%}; band-place at sowing.",
     "high_note": "Reduce P2O5 by {pct:.0%}."},
    {"parameter": "available_k", "label": "Available K (NH4OAc)", "unit": "kg/ha",
     "kind": "nutrient", "nutrient_form": "K2O", "low_max": 110.0, "high_min": 280.0,
     "adjustment": 0.25, "low_note": "Increase K2O by {pct:.0%}; split basal + reproductive.",
     "high_note": "Reduce K2O by {pct:.0%}."},
    {"parameter": "oc", "label": "Organic carbon", "unit": "%",
     "kind": "organic", "low_max": 0.5, "high_min": 0.75, "adjustment": 0.0,
     "low_note": "Low OC: incorporate FYM/compost ~10 t/ha; N use-efficiency improves.",
     "high_note": "Good organic matter status."},
    # Soil condition (pH / EC).
    {"parameter": "ph", "label": "Soil pH", "unit": "", "kind": "condition",
     "low_max": 6.5, "high_min": 7.5, "adjustment": 0.0,
     "low_note": "Acidic soil: apply lime as per lime requirement; prefer SSP over DAP on very acid soils.",
     "high_note": "Alkaline soil: apply gypsum; avoid acidifying fertilizers."},
    {"parameter": "ec", "label": "EC", "unit": "dS/m", "kind": "condition",
     "low_max": 1.0, "high_min": 2.0, "adjustment": 0.0,
     "low_note": None, "high_note": "Saline: leach with good water; prefer SOP over MOP (avoid Cl)."},
    # Micronutrients (ppm, DTPA-extractable): sufficient / deficient.
    {"parameter": "zn", "label": "Available Zn (DTPA)", "unit": "ppm",
     "kind": "micro", "low_max": 0.6, "high_min": 1.5, "adjustment": 0.0,
     "low_note": "Zn deficient: apply ZnSO4 25 kg/ha soil or 0.5% foliar spray.",
     "high_note": None},
    {"parameter": "fe", "label": "Available Fe (DTPA)", "unit": "ppm",
     "kind": "micro", "low_max": 4.5, "high_min": 10.0, "adjustment": 0.0,
     "low_note": "Fe deficient: 0.5% FeSO4 foliar spray (repeat 2–3 times).",
     "high_note": None},
    {"parameter": "b", "label": "Available B (hot water)", "unit": "ppm",
     "kind": "micro", "low_max": 0.5, "high_min": 1.0, "adjustment": 0.0,
     "low_note": "B deficient: borax 10 kg/ha soil or 0.2% foliar at flowering.",
     "high_note": None},
    {"parameter": "mn", "label": "Available Mn (DTPA)", "unit": "ppm",
     "kind": "micro", "low_max": 2.0, "high_min": 5.0, "adjustment": 0.0,
     "low_note": "Mn deficient: 0.5% MnSO4 foliar spray.",
     "high_note": None},
    {"parameter": "cu", "label": "Available Cu (DTPA)", "unit": "ppm",
     "kind": "micro", "low_max": 0.2, "high_min": 0.5, "adjustment": 0.0,
     "low_note": "Cu deficient: CuSO4 5 kg/ha soil application.",
     "high_note": None},
    {"parameter": "s", "label": "Available S", "unit": "ppm",
     "kind": "micro", "low_max": 10.0, "high_min": 20.0, "adjustment": 0.0,
     "low_note": "S deficient: prefer SSP/gypsum (S carriers) over DAP.",
     "high_note": None},
]


# ═════════════════════════════════════════════════════════════════════════════
# Mandi intelligence (Track 6): representative major APMC mandis with curated
# coordinates and their headline commodities. State/district codes are resolved
# from the geography ontology at seed time.
# ═════════════════════════════════════════════════════════════════════════════
MARKETS = [
    {"market_id": "MKT_LASALGAON", "name": "Lasalgaon", "state": "Maharashtra", "district": "Nashik",
     "latitude": 20.15, "longitude": 74.24, "key_commodities": "Onion"},
    {"market_id": "MKT_AZADPUR", "name": "Azadpur", "state": "Delhi", "district": "North Delhi",
     "latitude": 28.71, "longitude": 77.17, "key_commodities": "Tomato, Potato, Onion"},
    {"market_id": "MKT_VASHI", "name": "Vashi", "state": "Maharashtra", "district": "Thane",
     "latitude": 19.06, "longitude": 73.00, "key_commodities": "Fruits, Vegetables"},
    {"market_id": "MKT_GUNTUR", "name": "Guntur", "state": "Andhra Pradesh", "district": "Guntur",
     "latitude": 16.29, "longitude": 80.45, "key_commodities": "Chilli"},
    {"market_id": "MKT_INDORE", "name": "Indore", "state": "Madhya Pradesh", "district": "Indore",
     "latitude": 22.72, "longitude": 75.86, "key_commodities": "Soybean"},
    {"market_id": "MKT_KOTA", "name": "Kota", "state": "Rajasthan", "district": "Kota",
     "latitude": 25.18, "longitude": 75.84, "key_commodities": "Coriander"},
    {"market_id": "MKT_ERODE", "name": "Erode", "state": "Tamil Nadu", "district": "Erode",
     "latitude": 11.34, "longitude": 77.72, "key_commodities": "Turmeric"},
    {"market_id": "MKT_UNJHA", "name": "Unjha", "state": "Gujarat", "district": "Mahesana",
     "latitude": 23.80, "longitude": 72.39, "key_commodities": "Cumin (Jeera)"},
    {"market_id": "MKT_SIRSA", "name": "Sirsa", "state": "Haryana", "district": "Sirsa",
     "latitude": 29.53, "longitude": 75.03, "key_commodities": "Cotton"},
    {"market_id": "MKT_RAJKOT", "name": "Rajkot", "state": "Gujarat", "district": "Rajkot",
     "latitude": 22.30, "longitude": 70.80, "key_commodities": "Groundnut"},
    {"market_id": "MKT_SANGLI", "name": "Sangli", "state": "Maharashtra", "district": "Sangli",
     "latitude": 16.85, "longitude": 74.56, "key_commodities": "Turmeric"},
    {"market_id": "MKT_MANDSAUR", "name": "Mandsaur", "state": "Madhya Pradesh", "district": "Mandsaur",
     "latitude": 24.07, "longitude": 75.07, "key_commodities": "Garlic"},
]


# ═════════════════════════════════════════════════════════════════════════════
# Weather advisory (Track 7): risk thresholds + crop water need (mm/week at
# peak demand) + a text→mm rainfall proxy for IMD bulletins. Representative
# ranges; refine with IMD gridded data / district agromet units later.
# ═════════════════════════════════════════════════════════════════════════════
WEATHER_RISK_THRESHOLDS = [
    {"flag": "heat_stress", "metric": "temp_max", "operator": ">=", "threshold": 35.0,
     "severity": "high", "note": "Heat stress — risk to flowering/pollination; irrigate in evening, mulch."},
    {"flag": "frost_risk", "metric": "temp_min", "operator": "<=", "threshold": 4.0,
     "severity": "high", "note": "Frost risk — light irrigation / smudging; protect tender crops."},
    {"flag": "cold_night", "metric": "temp_min", "operator": "<=", "threshold": 10.0,
     "severity": "medium", "note": "Low night temperature — slow germination/growth."},
    {"flag": "high_humidity", "metric": "humidity", "operator": ">=", "threshold": 80.0,
     "severity": "medium", "note": "High humidity — fungal disease pressure; prefer preventive sprays, open canopy."},
    {"flag": "strong_wind", "metric": "wind", "operator": ">=", "threshold": 25.0,
     "severity": "medium", "note": "Strong wind — lodging / spray drift; avoid spraying."},
    {"flag": "waterlogging", "metric": "rainfall_mm", "operator": ">=", "threshold": 60.0,
     "severity": "high", "note": "Heavy rain — waterlogging risk; ensure drainage."},
    {"flag": "dry_spell", "metric": "rainfall_mm", "operator": "<", "threshold": 10.0,
     "severity": "high", "note": "Rainfall deficit — irrigate if possible; conserve soil moisture."},
]

# Rainfall text (IMD bulletins) → approximate mm/day, used for deficit/flood flags.
RAINFALL_TEXT_PROXY = [
    ("very heavy", 120.0), ("heavy", 80.0), ("moderate", 25.0), ("scattered", 8.0),
    ("light", 5.0), ("drizzle", 2.0), ("dry", 0.0), ("no rain", 0.0),
]

# Peak crop water need, mm/week (representative, at critical growth stages).
CROP_WATER_NEED_MM_WEEK = [
    {"crop_id": "CROP_RICE", "mm_week": 50.0},
    {"crop_id": "CROP_WHEAT", "mm_week": 35.0},
    {"crop_id": "CROP_MAIZE", "mm_week": 40.0},
    {"crop_id": "CROP_SUGARCANE", "mm_week": 60.0},
    {"crop_id": "CROP_COTTON", "mm_week": 45.0},
    {"crop_id": "CROP_TOMATO", "mm_week": 40.0},
    {"crop_id": "CROP_ONION", "mm_week": 30.0},
    {"crop_id": "CROP_POTATO", "mm_week": 35.0},
    {"crop_id": "CROP_SOYBEAN", "mm_week": 40.0},
    {"crop_id": "CROP_GROUNDNUT", "mm_week": 35.0},
]


# Tamil + Telugu symptom lexicons (Track 11) — appended to SYMPTOM_LEXICON so
# diagnosis works for Dravidian-script symptom text (crop aliases already cover
# all 12 languages). Gujarati/Bengali/Odia/… lexicons land the same way later.
SYMPTOM_LEXICON["ta"] = {
    "கருப்பு": "black", "கறுப்பு": "black", "கரும்": "black",
    "புள்ளிகள்": "spots", "புள்ளி": "spots", "கரும்புள்ளிகள்": "spots",
    "இலை": "leaf", "இலைகள்": "leaves", "இலைகளில்": "leaves",
    "மஞ்சள்": "yellowing", "மஞ்சளாக": "yellowing", "மஞ்சலான": "yellowing",
    "வெள்ளை": "white", "வெண்மை": "white",
    "வாடல்": "wilting", "வாடிய": "wilting", "வாடுதல்": "wilting",
    "சுருள்": "curling", "சுருண்ட": "curling", "சுருண்டு": "curling",
    "குட்டை": "stunted", "வளர்ச்சி குன்றிய": "stunted", "குன்றிய": "stunted",
    "பழுப்பு": "brown",
    "அரும்பு": "bud", "மொட்டு": "bud", "மொட்டுக்கள்": "bud",
    "பழம்": "fruit", "பழங்கள்": "fruit", "காய்": "fruit",
    "பூ": "flower", "பூக்கள்": "flower",
    "வேர்": "root", "வேர்கள்": "root", "வேரில்": "root",
    "தண்டு": "stem", "தண்டில்": "stem",
    "பூஞ்சை": "mildew", "பூசணம்": "mildew", "பூஞ்சாணம்": "mildew",
    "துரு": "rust", "துருப்பிடித்த": "rust",
    "சிவப்பு": "red",
    "அழுகல்": "rot", "அழுகிய": "rot", "சொத்தை": "rot",
    "துளை": "hole", "ஓட்டை": "hole", "துளைகள்": "hole",
    "வலை": "webbing", "வலைப்பின்னல்": "webbing",
    "நோய்": "disease", "நோய்கள்": "disease",
    "பூச்சி": "pest", "பூச்சிகள்": "pest", "புழு": "larva", "புழுக்கள்": "larva", "கம்பளிப்பூச்சி": "larva",
    "காய்ந்த": "drying", "உலர்ந்த": "drying", "உலர்வு": "drying",
    "உதிர்தல்": "falling", "உதிரும்": "falling", "உதிர்கிறது": "falling",
}
SYMPTOM_LEXICON["te"] = {
    "నలుపు": "black", "నల్ల": "black", "నల్లని": "black",
    "మచ్చలు": "spots", "మచ్చ": "spots",
    "ఆకు": "leaf", "ఆకులు": "leaves", "ఆకులపై": "leaves",
    "పసుపు": "yellowing", "పచ్చ": "yellowing", "పసుపురంగు": "yellowing",
    "తెలుపు": "white", "తెల్లని": "white",
    "వాడిపోవడం": "wilting", "వాడిపోయిన": "wilting", "వడలిపోవడం": "wilting",
    "ముడత": "curling", "ముడుచుకుపోవడం": "curling", "ముడుచుకున్న": "curling",
    "కురచ": "stunted", "పొట్టి": "stunted", "ఎదుగుదల లేని": "stunted",
    "గోధుమ": "brown",
    "మొగ్గ": "bud", "మొగ్గలు": "bud",
    "పండు": "fruit", "పండ్లు": "fruit", "కాయ": "fruit",
    "పువ్వు": "flower", "పూలు": "flower", "పుష్పం": "flower",
    "వేరు": "root", "వేళ్లు": "root", "వేళ్లపై": "root",
    "కాండం": "stem", "కాండంపై": "stem",
    "బూజు": "mildew", "బూజు తెగులు": "mildew",
    "తుప్పు": "rust", "తుప్పుపట్టిన": "rust",
    "ఎరుపు": "red",
    "కుళ్ళు": "rot", "కుళ్లిన": "rot", "కుళ్లుతెగులు": "rot",
    "రంధ్రం": "hole", "రంధ్రాలు": "hole",
    "వల": "webbing",
    "వ్యాధి": "disease", "తెగులు": "disease",
    "చీడ": "pest", "పురుగు": "pest", "పురుగులు": "pest", "లార్వా": "larva",
    "ఎండిపోవడం": "drying", "ఎండిన": "drying", "ఎండుతున్న": "drying",
    "రాలడం": "falling", "రాలుతున్న": "falling", "రాలిపోవడం": "falling",
}
