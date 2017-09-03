## Things to do

* Host on AWS:
    * Use zappa
    * Create an Elastic IP
    * Point random.tv.longair.net at that IP
    * Somehow make sure the API gateway responds to that IP?
    * Use DynamoDB or (or Redis on EC2?) as a cache for SPARQL
      results
* Add a check on episode number and production codes not being
  repeated
* Improve the presentation of the series page
* Show the series name even if you can't find any episodes
* Link to SPARQL queries for each problem report
* Episode numbers
    * Find out about the intended use of episode number
        * Done here: https://www.wikidata.org/wiki/Property_talk:P1545#Differences_in_usage_for_television_episodes
    * Add a check for episode number being present

## Useful resources

* https://www.wikidata.org/wiki/Special:MyLanguage/Wikidata:WikiProject_Movies
* https://www.wikidata.org/wiki/Wikidata:WikiProject_Movies/Tools#Television_season_cleanup
