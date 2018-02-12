#!/usr/bin/env python

import cgi
import json
from os import environ
import random
import redis
import re

from flask import Flask, redirect, render_template, request
from jinja2 import Markup
from SPARQLWrapper import SPARQLWrapper, JSON, POST, GET
from raven.contrib.flask import Sentry

import problems
import queries
from episodes import Episode, group_and_order_episodes, id_from_item_url

REDIS_PREFIX = environ.get('REDIS_PREFIX', None)
REDIS_URL = environ.get('REDIS_URL', 'redis://localhost')

QUERY_CACHE_EXPIRY = 3 * 60  # 3 minutes
ALL_SERIES_CACHE_EXPIRY = 24 * 60 * 60  # 1 day

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
Sentry(app)

@app.before_request
def before_request():
    if 'ON_HEROKU' in environ and request.url.startswith('http://'):
        new_url = request.url.replace('http://', 'https://', 1)
        return redirect(new_url, code=302)


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


class WikidataQuery(object):

    def __init__(self, query, why=None):
        self.query = query
        self.why = why


class WikidataQueryService(object):

    def __init__(self, purge_cache=False):
        self.queries = []
        self.purge_cache = purge_cache

    def _uncached_run_query(self, query, method=GET):
        sparql = SPARQLWrapper('https://query.wikidata.org/sparql')
        sparql.setReturnFormat(JSON)
        sparql.setMethod(method)
        sparql.setQuery(query)
        return sparql.query().convert()

    def run_query(self, query, why=None):
        self.queries.append(WikidataQuery(query, why))
        normalized_query = re.sub(r'\s+', ' ', query).strip()
        key = 'query:{}'.format(normalized_query)
        cached = redis_get(redis_api, key)
        if cached is None or self.purge_cache:
            method = POST if self.purge_cache else GET
            result = self._uncached_run_query(normalized_query, method)
            redis_set(redis_api, key, json.dumps(result), QUERY_CACHE_EXPIRY)
        else:
            result = json.loads(cached)
        return result


def parse_episodes(result_bindings):
    all_episodes = [Episode(b) for b in result_bindings]
    item_id_to_episode = {}
    for episode in all_episodes:
        item_id_to_episode[episode.item] = episode
    problems = []
    for episode in all_episodes:
        if episode.previous_episode_item:
            if episode.previous_episode_item in item_id_to_episode:
                episode.previous_episode = item_id_to_episode[episode.previous_episode_item]
            else:
                fmt = '{0} follows {1}, but {1} was not found by the query'
                problems.append(fmt.format(episode.label_with_item, episode.previous_episode_item))
        if episode.next_episode_item:
            if episode.next_episode_item in item_id_to_episode:
                episode.next_episode = item_id_to_episode[episode.next_episode_item]
            else:
                fmt = '{0} followed by {1} but {1} was not found by the query'
                problems.append(fmt.format(episode.label_with_item, episode.next_episode_item))
    return all_episodes


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
                 ('Q11622', 'Firefly'),
                 ('Q22908690', 'The Good Place'),
                 ('Q13417244', 'Brooklyn Nine-Nine'),
                 ('Q11598', 'Arrested Development'),
             ]),
            ('Data that could be improved',
             [
                 ('Q2085', 'Twin Peaks'),
             ]),
            ('Low quality data - lots to do',
             [
                 ('Q5902', 'Red Dwarf'),
             ]),
        ],
        title='Home',
    )


@app.route('/about')
def about():
    return render_template(
        'about.html',
        google_analytics_property_id=GOOGLE_ANALYTICS_PROPERTY_ID,
        title='About this site',
    )


@app.route('/search', methods=['POST'])
def search():
    if 'q' not in request.form:
        raise Exception("Missing the search parameter")
    query_service = WikidataQueryService()
    escaped_query = re.sub(r'\\', r'\\\\', re.escape(request.form['q']))
    results = query_service.run_query(
        queries.NAME_SUBSTRING_SEARCH.format(re_quoted_substring=escaped_query),
        'Find TV series matching a substring'
    )
    items_with_labels = [
        (id_from_item_url(r['series']['value']), r['nameWithoutLang']['value'])
        for r in results['results']['bindings']
    ]
    return render_template(
        'search-results.html',
        query=request.form['q'],
        google_analytics_property_id=GOOGLE_ANALYTICS_PROPERTY_ID,
        items_with_labels=items_with_labels,
        queries_used=query_service.queries,
        title='Search results',
    )


def slow_get_all_series():
    sparql = SPARQLWrapper('https://query.wikidata.org/sparql')
    sparql.setReturnFormat(JSON)
    sparql.setQuery(queries.ALL_TV_SERIES)
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


def cached_get_all_series(purge_cache=False):
    cached = redis_get(redis_api, 'all-series')
    if (cached is None) or purge_cache:
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
        items_with_labels=cached_get_all_series(),
        title='List of all television series',
    )


def get_episodes_multiseason(query_service, wikidata_item):
    query = queries.MULTI_SEASON_QUERY_FMT.format(item=wikidata_item)
    results = query_service.run_query(
        query,
        'Getting episodes of {0} assuming multi-season modelling'.format(wikidata_item)
    )
    return parse_episodes(results['results']['bindings'])


def get_episodes_singleseason(query_service, wikidata_item):
    query = queries.SINGLE_SEASON_QUERY_FMT.format(item=wikidata_item)
    results = query_service.run_query(
        query,
        'Getting episodes of {0} assuming single-season modelling'.format(wikidata_item)
    )
    return parse_episodes(results['results']['bindings'])


@app.route('/series/<wikidata_item>', methods=['GET', 'POST'])
def random_episode(wikidata_item):
    purge_cache = (request.method == 'POST') and (request.form.get('purge') == 'yes')
    query_service = WikidataQueryService(purge_cache)
    # First check that the item we have actually is an instance of a
    # 'television series' (Q5398426)
    results = query_service.run_query(
        queries.IS_ITEM_A_TV_SERIES_FMT.format(item=wikidata_item),
        'Checking that {0} is really a television series'.format(wikidata_item)
    )
    if not results['boolean']:
        return '''{0} did not seem to be a television series (an 'instance of'
                  (P31) Q5398426 or something which is a 'subclass of' (P279)
                  Q5398426)'''.format(wikidata_item)
    # Now get all episodes of that show, assuming it has the
    # multi-season structure:
    uses_single_season_modelling = False
    episodes = get_episodes_multiseason(query_service, wikidata_item)
    if not episodes:
        episodes = get_episodes_singleseason(query_service, wikidata_item)
        uses_single_season_modelling = True
        if not episodes:
            report_items = problems.report_extra_queries(query_service, wikidata_item)
            report_items = linkify_report(report_items)
            # Get the name of the series so that we can make the page more readable:
            results = query_service.run_query(
                queries.LABEL_FOR_ITEM_FMT.format(item=wikidata_item),
                'Getting the Wikidata label (i.e. name) of {0} for a better error message'.format(wikidata_item))
            series_name = results['results']['bindings'][0]['seriesLabel']['value']
            return render_template(
                'no-episodes.html',
                google_analytics_property_id=GOOGLE_ANALYTICS_PROPERTY_ID,
                report_items=report_items,
                series_item=wikidata_item,
                series_name=series_name,
                queries_used=query_service.queries,
                title='No episodes found of {0}'.format(series_name),
            )
    episodes_table_data, _ = group_and_order_episodes(episodes)
    episode = random.choice(episodes)
    return render_template(
        'random-episode.html',
        google_analytics_property_id=GOOGLE_ANALYTICS_PROPERTY_ID,
        show_random=(request.method == 'POST'),
        episode=episode,
        all_episodes=episodes,
        uses_single_season_modelling=uses_single_season_modelling,
        report_items=linkify_report(problems.report(episodes)),
        episodes_table_data=episodes_table_data,
        series_item=wikidata_item,
        queries_used=query_service.queries,
        title=episodes[0].series_name,
    )


if __name__ == "__main__":
    app.run()
