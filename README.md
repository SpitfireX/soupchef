# Soupchef

A Python script for scraping data from a certain big german recipe portal.



## Installation

1. Make sure you're using **Python 3.6** or later and the latest **pipenv**. Installing pipenv is as easy as `pip3 install pipenv`
2. Install dependencies: `cd soupchef`, `pipenv install`

That's it, your're set! Make sure everything's working by running `pipenv run python soupchef.py --help`



## Usage

```
usage: soupchef.py [-h] (--daily | --search | --url | --id | --random | --all | --refresh) [-f]
                   [-o OUTFOLDER] [-n NUM] [-r RECURSION_DEPTH] [-c COMMENT_NUM] [-l RATE_LIMIT]
                   [-p PAGE] [-s {relevance,daily,date,preptime,difficulty,rating}]
                   [--filenames {plain,title}] [--dirnames {flat,category,date}] [--index-only] [-q]
                   [-v] [-vv]
                   [input [input ...]]

Fetches recipes and their metadata from a big German cooking portal.

positional arguments:
  input                 input arguments

mode flags:
  --daily               Downloads the recipe of the day, no further input required. Can be combined
                        with -c and -r.
  --search              Searches for the entered term and fetches the results. Multiple searches
                        need to be separated by spaces. Can be combined with -n, -c, -r and -p.
  --url                 Fetches the entered URLs. Can be combined with -c and -r.
  --id                  Fetches the entered IDs. Can be combined with -c and -r.
  --random              Fetches a number of random recipes. Can be combined with -n, -c and -r.
  --all                 Fetches all recipes. Can be combined with -c and -p.
  --refresh             Fetches all recipes in the index again. Can be combined with -c.

optional arguments:
  -h, --help            show this help message and exit
  -f                    Force fetch all elements, don't skip already existing.
  -o OUTFOLDER          Sets the output folder.
  -n NUM                Sets the number of elements to fetch. For search and all multiples of 30 are
                        sensible values. -1 = all.
  -r RECURSION_DEPTH, --recursion_depth RECURSION_DEPTH
                        Sets the number of recursion steps to take. Recursion works breadth-first on
                        recommended recipes, i.e. the initial list of recipes will be fetched, then
                        their recommended recipes, then the recommended recipes of the recommended
                        recipes, etc.
  -c COMMENT_NUM        Sets the number of comments to load per recipe. -1 = all.
  -l RATE_LIMIT, --rate-limit RATE_LIMIT
                        Sets the rate limit for HTTP(S) requests in seconds. The value must either
                        be a single constant (e.g. "0.8") or a range (e.g. "0.25-4") that is used
                        for randomization.
  -p PAGE, --start-page PAGE
                        Sets the number of the first page to fetch.
  -s {relevance,daily,date,preptime,difficulty,rating}, --sort-mode {relevance,daily,date,preptime,difficulty,rating}
                        Sets the sort mode for the search results.
  --filenames {plain,title}
                        Sets the format for the output file names. Plain: recipe ID. Title: recipe
                        ID and recipe title.
  --dirnames {flat,category,date}
                        Sets the format of the output directory structure. Flat: all files in the
                        base directory. Category: grouped into subdirectories based on the recipe
                        category. Date: grouped into subdirectories based on the creation date.
  --index-only          Don't fetch anything and only add the IDs of all operations to the index.
                        This is useful to build a list of IDs for later consumption.
  -q                    Suppress any console output
  -v                    Show informative console output.
  -vv                   Show debug console output.
```
