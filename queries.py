MULTI_SEASON_QUERY_FMT = '''
SELECT ?episodeLabel ?episode ?series ?seriesLabel ?season ?numberInSeason
       ?seasonNumber ?seasonLabel ?episodeNumber ?productionCode
       ?previousEpisode ?nextEpisode ?episodesInSeason ?totalSeasons WHERE {{
  BIND(wd:{item} as ?series) .
  ?episode wdt:P361 ?season .
  ?episode wdt:P31/wdt:P279* wd:Q21191270 .
  ?episode p:P179 ?episodePartOfSeriesStatement .
  ?episodePartOfSeriesStatement ps:P179 ?series .
  ?season wdt:P31 wd:Q3464665 .
  ?season p:P179 ?seriesStatement .
  ?seriesStatement ps:P179 ?series .
  OPTIONAL {{
    ?episode p:P179 ?episodeSeriesToSeason .
    ?episodeSeriesToSeason ps:P179 ?season .
    ?episodeSeriesToSeason pq:P1545 ?numberInSeason
  }}
  OPTIONAL {{
    ?seriesStatement pq:P1545 ?seasonNumber .
  }}
  OPTIONAL {{
    ?episodePartOfSeriesStatement pq:P1545 ?episodeNumber
  }}
  OPTIONAL {{
    ?episode wdt:P2364 ?productionCode
  }}
  OPTIONAL {{
    ?episode wdt:P155 ?previousEpisode .
  }}
  OPTIONAL {{
    ?episode wdt:P156 ?nextEpisode .
  }}
  OPTIONAL {{
    ?series wdt:P2437 ?totalSeasons
  }}
  OPTIONAL {{
    ?season wdt:P1113 ?episodesInSeason
  }}
  SERVICE wikibase:label {{
     bd:serviceParam wikibase:language "en" .
  }}
}}
    ORDER BY xsd:integer(?seasonNumber) xsd:integer(?episodeNumber) ?productionCode'''

SINGLE_SEASON_QUERY_FMT = '''
SELECT ?episodeLabel ?episode ?series ?seriesLabel ?episodeNumber
       ?productionCode ?previousEpisode ?nextEpisode ?episodesInSeason
       ?totalSeasons WHERE {{
  BIND(wd:{item} as ?series) .
  ?episode p:P179 ?episodeSeriesStatement .
  ?episode wdt:P31/wdt:P279* wd:Q21191270 .
  ?episodeSeriesStatement ps:P179 ?series .
  OPTIONAL {{
    ?episodeSeriesStatement pq:P1545 ?episodeNumber
  }}
  OPTIONAL {{
    ?episode wdt:P2364 ?productionCode
  }}
  OPTIONAL {{
    ?episode wdt:P155 ?previousEpisode .
  }}
  OPTIONAL {{
    ?episode wdt:P156 ?nextEpisode .
  }}
  OPTIONAL {{
    ?series wdt:P1113 ?episodesInSeason
  }}
  OPTIONAL {{
    ?series wdt:P2437 ?totalSeasons
  }}
  SERVICE wikibase:label {{
     bd:serviceParam wikibase:language "en" .
  }}
}} ORDER BY xsd:integer(?episodeNumber) ?productionCode'''

NUMBER_OF_SEASONS_FMT = '''
SELECT ?numberOfSeasons WHERE {{
  wd:{item} wdt:P2437 ?numberOfSeasons
}}'''

SEASONS_WITH_EPISODES_TOTALS_FMT = '''
SELECT ?season ?seasonNumber ?episodesInSeason WHERE {{
  ?season wdt:P31 wd:Q3464665 .
  ?season p:P179 ?seriesStatement .
  ?seriesStatement ps:P179 wd:{item}
  OPTIONAL {{
    ?seriesStatement pq:P1545 ?seasonNumber .
  }}
  OPTIONAL {{
    ?season wdt:P1113 ?episodesInSeason
  }}
}}
ORDER BY xsd:integer(?seasonNumber)'''

EPISODES_FROM_SEASON_AND_SERIES_FMT = '''
SELECT ?episode ?season ?seasonNumber ?episodeNumber ?seriesStatement WHERE {{
  ?episode wdt:P361 ?season
  OPTIONAL {{
    ?episode p:P179 ?seriesStatement .
    ?seriesStatement ps:P179 wd:{item}
    OPTIONAL {{
      ?seriesStatement pq:P1545 ?episodeNumber
    }}
  }}

  VALUES ?season {{ {seasons} }}
}}
ORDER BY ?seasonNumber ?episodeNumber'''

IS_ITEM_A_TV_SERIES_FMT = 'ASK WHERE {{ wd:{item} wdt:P31/wdt:P279* wd:Q5398426 }}'

LABEL_FOR_ITEM_FMT = '''SELECT ?seriesLabel WHERE {{
  BIND(wd:{item} as ?series)
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "[AUTO_LANGUAGE],en". }}
}}'''

ALL_TV_SERIES = '''SELECT DISTINCT ?series ?seriesLabel WHERE {
  ?series wdt:P31/wdt:P279* wd:Q5398426
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" } }
  # ORDER BY ?seriesLabel
'''

NAME_SUBSTRING_SEARCH = '''
SELECT DISTINCT ?series ?nameWithoutLang (group_concat(?lang;separator=",") as ?langs) WHERE {{
  ?series wdt:P31/wdt:P279* wd:Q5398426 .
  ?series rdfs:label ?name .
  FILTER regex(?name, "{re_quoted_substring}", "i") .
  BIND(LANG(?name) AS ?lang)
  BIND(STR(?name) AS ?nameWithoutLang)
}} GROUP BY ?series ?nameWithoutLang ORDER BY ?nameWithoutLang
'''
