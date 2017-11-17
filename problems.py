from itertools import groupby

from episodes import group_and_order_episodes, id_from_item_url
import queries


def report(episodes):
    grouped_episodes_iter, report_items = group_and_order_episodes(episodes)
    # Just make this non-lazy to avoid confusion when items are
    # consumed and you can't get them back:
    grouped = [
        (season_tuple, list(episodes_group))
        for season_tuple, episodes_group in grouped_episodes_iter
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

def report_extra_queries(query_service, series_item):
    report_items = []
    # First check if it has a number of seasons property:
    results = query_service.run_query(
        queries.NUMBER_OF_SEASONS_FMT.format(item=series_item),
        'Checking if {0} has a \'number of seasons\' property'.format(series_item)
    )
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
    results = query_service.run_query(
        queries.SEASONS_WITH_EPISODES_TOTALS_FMT.format(item=series_item),
        'Finding all seasons of {0}'.format(series_item)
    )
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
    results = query_service.run_query(queries.EPISODES_FROM_SEASON_AND_SERIES_FMT.format(
        item=series_item,
        seasons=' '.join(all_seasons)),
        'Finding the episodes directly from season items'
    )
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
