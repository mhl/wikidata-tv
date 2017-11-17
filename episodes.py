from itertools import groupby
import re


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
        if 'season' in binding:
            self.season_item = id_from_item_url(binding['season']['value'])
            self.season_number = int_if_present(binding, 'seasonNumber')
            self.season_label = binding['seasonLabel']['value']
        else:
            self.season_item = None
            self.season_number = 1
            self.season_label = None
        self.episode_number = int_if_present(binding, 'episodeNumber')
        self.production_code = str_if_present(binding,'productionCode')
        self.previous_episode_item = id_if_present(binding, 'previousEpisode')
        self.previous_episode = None
        self.next_episode_item = id_if_present(binding, 'nextEpisode')
        self.next_episode = None
        self.episodes_in_season = int_if_present(binding, 'episodesInSeason')
        self.total_seasons = int_if_present(binding, 'totalSeasons')

    def __eq__(self, other):
        return self.item == other.item

    def __ne__(self, other):
        return not self.__eq__(other)

    @property
    def label_with_item(self):
        if self.item == self.name:
            return self.item
        else:
            return '{0} ({1})'.format(self.name, self.item)


def group_and_order_episodes(episodes):
    id_to_episode = {}
    first_episodes = []
    last_episodes = []
    for episode in episodes:
        id_to_episode[episode.item] = episode
    # Check that the previous and next episodes are consistent:
    unlinked_episodes = []
    problems = []
    for episode in episodes:
        if not episode.previous_episode_item and not episode.next_episode_item:
            fmt = 'Episode {item_id} has no previous or next episode'
            problems.append(fmt.format(item_id=episode.label_with_item))
            unlinked_episodes.append(episode)
        if episode.previous_episode:
            if episode.previous_episode.next_episode != episode:
                fmt = '{0} follows {1}, but {1} followed by {2}'
                problems.append(fmt.format(
                    episode.label_with_item,
                    episode.previous_episode.label_with_item,
                    episode.previous_episode.next_episode.label_with_item))
        if episode.next_episode:
            if episode.next_episode.previous_episode:
                if episode.next_episode.previous_episode != episode:
                    fmt = '{0} followed by {1}, but {1} follows {2}'
                    problems.append(fmt.format(
                        episode.label_with_item,
                        episode.next_episode.label_with_item,
                        episode.next_episode.previous_episode.label_with_item))
            else:
                fmt = '{0} followed by {1}, but {1} follows nothing'
                problems.append(fmt.format(
                    episode.label_with_item,
                    episode.next_episode.label_with_item))
        if episode.next_episode and not episode.previous_episode:
            first_episodes.append(episode)
        if episode.previous_episode and not episode.next_episode:
            last_episodes.append(episode)
    first_or_last_problems = []
    if len(first_episodes) == 0:
        first_or_last_problems.append('There was no first episode found (in the sense that it has no \'follows\' but does have a \'followed by\'')
    elif len(first_episodes) > 1:
        fmt = 'More than one episode had a \'followed by\' but no \'follows\': {0}'
        first_or_last_problems.append(fmt.format(', '.join(e.label_with_item for e in first_episodes)))
    if len(last_episodes) == 0:
        first_or_last_problems.append('There was no last episode found (in the sense that it has no \'followed by\' but does have a \'follows\'')
    elif len(last_episodes) > 1:
        fmt = 'More than one episode had a \'follows\' but no \'followed by\': {0}'
        first_or_last_problems.append(fmt.format(', '.join(e.label_with_item for e in last_episodes)))
    # If there are no unlinked episodes, 1 first episode and no
    # 'follows' / 'followed by' consistency problems, then we can
    # order by the 'follows' / 'followed by' relationships:
    if len(first_episodes) == 1 and len(unlinked_episodes) == 0 \
       and len(problems) == 0:
        episodes = []
        current_episode = next(iter(first_episodes))
        while current_episode:
            episodes.append(current_episode)
            current_episode = current_episode.next_episode
    report_items = [(False, problem) for problem in first_or_last_problems + problems]
    return groupby(episodes, lambda e: (e.season_item, e.season_number, e.season_label)), report_items
