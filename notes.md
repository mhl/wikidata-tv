Some episodes have multiple episode numbers, e.g. :

https://en.wikipedia.org/wiki/The_Truth_(The_X-Files) says it's
201st and 202nd

in Wikidata someone's given this single item two series ordinals
for 201 and 202

  https://www.wikidata.org/wiki/Q7770602

This comes up often - two part episodes when broadcast that are
really one episode. Maybe ask the wikiproject...

## Things to do

* Host on AWS:
    * Use zappa
    * Create an Elastic IP
    * Point random.tv.longair.net at that IP
    * Somehow make sure the API gateway responds to that IP?
    * Use DynamoDB or (or Redis on EC2?) as a cache for SPARQL
      results
* *or* host on decaf
* *or* host on asti
* Add a check on episode number and production codes not being
  repeated
* Show the series name on the "no episodes" page if possible
* Improve the presentation of the series page
* Show the series name even if you can't find any episodes
* Add a search box
* Link to SPARQL queries for each problem report

## Useful resources

* https://www.wikidata.org/wiki/Special:MyLanguage/Wikidata:WikiProject_Movies
* https://www.wikidata.org/wiki/Wikidata:WikiProject_Movies/Tools#Television_season_cleanup
