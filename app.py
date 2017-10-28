#!/usr/bin/env python

from itertools import groupby
import cgi
import json
from os import environ
import random
import redis
import re

from flask import Flask, render_template, request
from jinja2 import Markup
from SPARQLWrapper import SPARQLWrapper, JSON


REDIS_PREFIX = environ.get('REDIS_PREFIX', None)
REDIS_URL = environ.get('REDIS_URL', 'redis://localhost')

QUERY_CACHE_EXPIRY = 3 * 60 # 3 minutes
ALL_SERIES_CACHE_EXPIRY = 24 * 60 * 60 # 1 day

GOOGLE_ANALYTICS_PROPERTY_ID = environ.get('GOOGLE_ANALYTICS_PROPERTY_ID', '')

def redis_key(key):
    if not REDIS_PREFIX:
        raise Exception('REDIS_PREFIX was not set in the environment')
    return '{}:{}'.format(REDIS_PREFIX, key)


def redis_set(redis_api, key, value, expires=None):
    redis_api.set(redis_key(key), value, ex=expires)


def redis_get(redis_api, key):
    return redis_api.get(redis_key(key))


redis_api = redis.StrictRedis.from_url(REDIS_URL, db=0)


app = Flask(__name__)


def wikidata_linkify(s):
    return re.sub(
        r'(Q\d+)',
        '<a href="https://www.wikidata.org/wiki/\\1">\\1</a>',
        cgi.escape(s)
    )


def linkify_report(report_items):
    return [
        (success, Markup(wikidata_linkify(description)))
        for success, description in report_items
    ]


def id_from_item_url(url):
    return re.sub(r'^http://www.wikidata.org/entity/', '', url)


def int_if_present(binding, key):
    if key in binding:
        return int(binding[key]['value'])
    return None


def str_if_present(binding, key):
    if key in binding:
        return binding[key]['value']
    return None


def id_if_present(binding, key):
    if key in binding:
        return id_from_item_url(binding[key]['value'])
    return None


class Episode(object):
    def __init__(self, binding):
        self.name = binding['episodeLabel']['value']
        self.series_name = binding['seriesLabel']['value']
        self.item = id_from_item_url(binding['episode']['value'])
        self.series_item = id_from_item_url(binding['series']['value'])
        self.season_item = id_from_item_url(binding['season']['value'])
        self.season_number = int_if_present(binding, 'seasonNumber')
        self.season_label = binding['seasonLabel']['value']
        self.episode_number = int_if_present(binding, 'episodeNumber')
        self.production_code = str_if_present(binding,'productionCode')
        self.previous_episode_item = id_if_present(binding, 'previousEpisode')
        self.next_episode_item = id_if_present(binding, 'nextEpisode')
        self.episodes_in_season = int_if_present(binding, 'episodesInSeason')
        self.total_seasons = int_if_present(binding, 'totalSeasons')


def parse_episodes(result_bindings):
    all_episodes = [Episode(b) for b in result_bindings]
    return all_episodes


def group_and_order_episodes(episodes):
    return groupby(episodes, lambda e: (e.season_item, e.season_number, e.season_label))


def problem_report(episodes):
    report_items = []
    # Just make this non-lazy to avoid confusion when items are
    # consumed and you can't get them back:
    grouped = [
        (season_tuple, list(episodes_group))
        for season_tuple, episodes_group in group_and_order_episodes(episodes)
    ]
    for season_tuple, episodes_group in grouped:
        season_item, season_number, season_label = season_tuple
        if episodes_group:
            # Then there are some episodes in that season:
            arbitrary_episode = episodes_group[0]
            if arbitrary_episode.episodes_in_season:
                # Then we can check the numbers match:
                n_episodes_found = len(episodes_group)
                if arbitrary_episode.episodes_in_season != n_episodes_found:
                    report_items.append(
                        (
                            False,
                            "The number of episodes actually found in season {season_item} ({n_found}) was different from the number of episodes suggested by the 'number of episodes' (P1113) statement ({n_expected})".format(
                                season_item=season_item,
                                n_found=n_episodes_found,
                                n_expected=arbitrary_episode.episodes_in_season)
                        )
                    )
            else:
                report_items.append(
                    (
                        False,
                        "Season {season_item} was missing the 'number of episodes' (P1113) statement".format(season_item=season_item)
                    )
                )
        else:
            report_items.append(
                (
                    False,
                    'There were no episodes at all found in season {season_item}!'.format(season_item=season_item)
                )
            )
    episodes_without_an_episode_number = [
        episode for episode in episodes
        if not episode.episode_number
    ]
    if len(episodes_without_an_episode_number):
        report_items.append(
            (
                False,
                "{n} episodes were missing an episode number, which should be specified as a 'series ordinal' (P1545) qualifier to the 'series' (P179) statement linking the episode to the series".format(n=len(episodes_without_an_episode_number))
            )
        )
    return report_items

def problem_report_extra_queries(series_item, purge_cache):
    report_items = []
    # First check if it has a number of seasons property:
    results = cached_run_query('''
SELECT ?numberOfSeasons WHERE {{
  wd:{0} wdt:P2437 ?numberOfSeasons
}}
    '''.format(series_item), purge_cache)
    values = [
        b['numberOfSeasons']['value'] for b in
        results['results']['bindings']
    ]
    values_len = len(values)
    if values_len > 1:
        report_items.append(
            (
                False,
                "Multiple equally truthy statements for 'number of seasons' (P2437): {0}".format(
                    ', '.join(values))
            )
        )
        number_of_seasons = None
    elif values_len == 1:
        report_items.append(
            (
                True,
                "Found the 'number of seasons' (P2437): {0}".format(values[0])
            )
        )
        number_of_seasons = int(values[0])
    else:
         report_items.append(
             (
                 False,
                 "No 'number of seasons' (P2347) property found"
             )
         )
         number_of_seasons = None
    # Now find all the seasons, with option extra properties:
    results = cached_run_query('''
SELECT ?season ?seasonNumber ?episodesInSeason WHERE {{
  ?season wdt:P31 wd:Q3464665 .
  ?season p:P179 ?seriesStatement .
  ?seriesStatement ps:P179 wd:{0}
  OPTIONAL {{
    ?seriesStatement pq:P1545 ?seasonNumber .
  }}
  OPTIONAL {{
    ?season wdt:P1113 ?episodesInSeason
  }}
}}
ORDER BY xsd:integer(?seasonNumber)
    '''.format(series_item), purge_cache)

    values = [
        {k: v['value'] for k, v in b.items()}
        for b in results['results']['bindings']
    ]
    if number_of_seasons is not None:
        if number_of_seasons == len(values):
            report_items.append(
                (
                    True,
                    "The number of seasons actually found matched the 'number of seasons' (P2437)"
                )
            )
        else:
            report_items.append(
                (
                    False,
                    "The number of seasons actually found ({found}) didn't match the 'number of seasons' (P2437) value {expected}".format(found=len(values), expected=number_of_seasons)
                )
            )
    if not values:
        report_items.append(
            (
                False,
                "No seasons were found at all - they should have a 'series' (P179) relationship to {0}".format(series_item)
            )
        )
    season_to_number_of_episodes = {}
    for season in values:
        season_item = id_from_item_url(season['season'])
        if 'seasonNumber' not in season:
            report_items.append(
                (
                    False,
                    "No 'season ordinal' (P1545) qualifier was found for the 'series' (P179) statement for season {0}".format(season_item)
                )
            )
        if 'episodesInSeason' in season:
            season_to_number_of_episodes[season_item] = int(season['episodesInSeason'])
        else:
            report_items.append(
                (
                    False,
                    "No 'number of episodes' (P1113) statement for season {0}".format(season_item)
                )
            )
    all_seasons = ['wd:' + id_from_item_url(season['season']) for season in values]
    results = cached_run_query('''
SELECT ?episode ?season ?seasonNumber ?episodeNumber WHERE {{
  ?episode wdt:P361 ?season
  OPTIONAL {{
    ?episode p:P179 ?seriesStatement .
    ?seriesStatement ps:P179 wd:{series_item}
    OPTIONAL {{
      ?seriesStatement pq:P1545 ?episodeNumber
    }}
  }}

  VALUES ?season {{ {seasons} }}
}}
ORDER BY ?seasonNumber ?episodeNumber
    '''.format(
        series_item=series_item,
        seasons=' '.join(all_seasons)
    ), purge_cache)
    values = [
        {k: v['value'] for k, v in b.items()}
        for b in results['results']['bindings']
    ]
    if values:
        # Group these episodes by season so we can compare the counts:
        grouped_by_season = {
            season: results
            for season, results
            in groupby(values, lambda v: id_from_item_url(v['season']))
        }
        for season_item, expected_number_of_episodes in season_to_number_of_episodes.items():
            if season_item in grouped_by_season:
                n_episodes_from_part_of = len(grouped_by_season[season_item])
                if n_episodes_from_part_of == expected_number_of_episodes:
                    report_items.append(
                        (
                            True,
                            "The number of episodes that were 'part of' (P361) season {season_item} matched the number of episodes expected from the 'number of episodes' (P1113) for the season: {n}".format(season_item=season_item, n=expected_number_of_episodes)
                        )
                    )
                else:
                    report_items.append(
                        (
                            False,
                            "The number of episodes that were 'part of' (P361) season {season_item} ({n_part_of}) didn't match the number of episodes expected from the 'number of episodes' (P1113) for the season ({expected})".format(season_item=season_item, n_part_of=n_episodes_from_part_of, expected=expected_number_of_episodes)
                        )
                    )
        for value in values:
            if value['seriesStatement']:
                if not value['episodeNumber']:
                    report_items.append(
                        (
                            False,
                            "The episode {episode}'s 'series' (P179) statement linking it to {series_item} lacked a 'series ordinal' (P1545) qualifier".format(episode=id_from_item_url(value['episode']), series_item=series_item)
                        )
                    )
            else:
                report_items.append(
                    (
                        False,
                        "The episode {episode} was missing a 'series' (P179) statement linking it to {series_item}".format(episode=id_from_item_url(value['episode']), series_item=series_item)
                    )
                )
    else:
        report_items.append(
            (
                False,
                "Found no episodes with a 'part of' (P361) relationship to any season of the series"
            )
        )
    return report_items


@app.route('/')
def homepage():
    return render_template(
        'homepage.html',
        google_analytics_property_id=GOOGLE_ANALYTICS_PROPERTY_ID,
        examples_of_various_quality=[
            ('Generally high quality data',
             [
                 ('Q3577037', 'The West Wing'),
                 ('Q189350', '30 Rock'),
                 ('Q16290', 'Star Trek: TNG'),
                 ('Q2744', 'The X-Files'),
             ]),
            ('Data that could be improved',
             [
                 ('Q2085', 'Twin Peaks'),
             ]),
            ('Low quality data - lots to do',
             [
                 ('Q13417244', 'Brooklyn Nine-Nine'),
                 ('Q4380', "Don't Trust the B---- in Apartment 23"),
                 ('Q11598', 'Arrested Development'),
                 ('Q5902', 'Red Dwarf'),
             ]),
        ]
    )

@app.route('/about')
def about():
    return render_template(
        'about.html',
        google_analytics_property_id=GOOGLE_ANALYTICS_PROPERTY_ID,
    )

def slow_run_query(query):
    sparql = SPARQLWrapper('https://query.wikidata.org/sparql')
    sparql.setReturnFormat(JSON)
    sparql.setQuery(query)
    return sparql.query().convert()


def cached_run_query(query, purge_cache=False):
    normalized_query = re.sub(r'\s+', ' ', query).strip()
    key = 'query:{}'.format(normalized_query)
    cached = redis_get(redis_api, key)
    if cached is None or purge_cache:
        result = slow_run_query(normalized_query)
        redis_set(redis_api, key, json.dumps(result), QUERY_CACHE_EXPIRY)
    else:
        result = json.loads(cached)
    return result


def slow_get_all_series():
    sparql = SPARQLWrapper('https://query.wikidata.org/sparql')
    sparql.setReturnFormat(JSON)
    sparql.setQuery('''
SELECT ?series ?seriesLabel WHERE {
  ?series wdt:P31/wdt:P279* wd:Q5398426
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en" } }
  # ORDER BY ?seriesLabel
''')
    results = sparql.query().convert()
    return sorted(
        (
            (
                id_from_item_url(r['series']['value']),
                r['seriesLabel']['value']
            )
            for r in results['results']['bindings']
            if not re.match('^Q\d+$', r['seriesLabel']['value'])
        ),
        key=lambda t: t[1]
    )


def cached_get_all_series():
    cached = redis_get(redis_api, 'all-series')
    if cached is None:
        result = slow_get_all_series()
        redis_set(redis_api, 'all-series', json.dumps(result), ALL_SERIES_CACHE_EXPIRY)
    else:
        result = json.loads(cached)
    return result


@app.route('/series/')
def all_series():
    return render_template(
        'all-series.html',
        google_analytics_property_id=GOOGLE_ANALYTICS_PROPERTY_ID,
        items_with_labels=cached_get_all_series())


@app.route('/series/<wikidata_item>', methods=['GET', 'POST'])
def random_episode(wikidata_item):
    purge_cache = (request.method == 'POST') and (request.form.get('purge') == 'yes')
    # First check that the item we have actually is an instance of a
    # 'television series' (Q5398426)
    results = cached_run_query(
        'ASK WHERE {{ wd:{0} wdt:P31/wdt:P279* wd:Q5398426 }}'.format(wikidata_item),
        purge_cache)
    if not results['boolean']:
        return "{0} did not seem to be a television series (an 'instance of' (P31) Q5398426 or something which is a 'subclass of' (P279) Q5398426)".format(wikidata_item)
    # Now get all episodes of that show:
    query = '''
SELECT ?episodeLabel ?episode ?series ?seriesLabel ?season ?seasonNumber ?seasonLabel ?episodeNumber ?productionCode ?previousEpisode ?nextEpisode ?episodesInSeason ?totalSeasons WHERE {{
  BIND(wd:{0} as ?series) .
  ?episode wdt:P361 ?season .
  ?episode p:P179 ?episodePartOfSeriesStatement .
  ?episodePartOfSeriesStatement ps:P179 ?seriesValue .
  ?seriesValue wdt:P31/wdt:P279* wd:Q5398426 .
  ?season wdt:P31 wd:Q3464665 .
  ?season p:P179 ?seriesStatement .
  ?seriesStatement ps:P179 ?series .
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
    ORDER BY xsd:integer(?seasonNumber) xsd:integer(?episodeNumber) ?productionCode'''.format(
        wikidata_item
    )
    results = cached_run_query(query, purge_cache)
    episodes = parse_episodes(results['results']['bindings'])
    if not episodes:
        report_items = problem_report_extra_queries(wikidata_item, purge_cache)
        report_items = linkify_report(report_items)
        return render_template(
            'no-episodes.html',
            google_analytics_property_id=GOOGLE_ANALYTICS_PROPERTY_ID,
            report_items=report_items,
            series_item=wikidata_item,
            all_episodes_query=query,
        )
    episodes_table_data = group_and_order_episodes(episodes)
    episode = random.choice(episodes)
    return render_template(
        'random-episode.html',
        google_analytics_property_id=GOOGLE_ANALYTICS_PROPERTY_ID,
        show_random=(request.method == 'POST'),
        episode=episode,
        all_episodes=episodes,
        report_items=linkify_report(problem_report(episodes)),
        episodes_table_data=episodes_table_data,
        series_item=wikidata_item,
        all_episodes_query=query
    )

if __name__ == "__main__":
    app.run()
